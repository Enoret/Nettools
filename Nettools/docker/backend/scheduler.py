"""
NetTools - Background Task Scheduler

Speed tests and network scans are run through `perform_speed_test` and
`perform_network_scan`, both from the scheduler and from the API, so that a
single lock per task prevents manual and scheduled runs from overlapping.
"""

import logging
import threading
import time
from datetime import timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import database as db
from speedtest_service import run_speed_test
from network_service import scan_network, resolve_ranges, infer_device_type
from oui_service import resolve_vendor
import unifi_service
import hint_service
from port_scan_service import scan_ports

try:
    from telegram_service import (send_new_device_alert, send_speed_test_result,
                                  send_speed_test_failure, send_port_changes_alert)
except ImportError:
    send_new_device_alert = send_speed_test_result = send_speed_test_failure = send_port_changes_alert = None

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_scan_lock = threading.Lock()
_test_lock = threading.Lock()

# Port scans: at most one per device and MAX_PARALLEL_PORT_SCANS overall
MAX_PARALLEL_PORT_SCANS = 2
_port_scan_guard = threading.Lock()
_port_scans_running = set()


class TaskBusyError(Exception):
    """Raised when a task is requested while the same task is already running."""


# ==========================================
#  Shared task runners (used by API + scheduler)
# ==========================================

def perform_speed_test(server_id: str = None) -> dict:
    """Run a speed test and save it. Raises TaskBusyError if one is running."""
    if not _test_lock.acquire(blocking=False):
        raise TaskBusyError("Ya hay un test en curso")
    try:
        result = run_speed_test(server_id)
        return db.save_speed_test(result)
    finally:
        _test_lock.release()


def perform_network_scan() -> dict:
    """Scan the network, update devices, save a snapshot and notify new devices.

    Raises TaskBusyError if a scan is already running.
    """
    if not _scan_lock.acquire(blocking=False):
        raise TaskBusyError("Ya hay un escaneo en curso")
    try:
        settings = db.get_settings()
        ranges = resolve_ranges(settings)
        logger.info("Running network scan on " + (", ".join(r['cidr'] for r in ranges) or "nothing"))

        devices = scan_network(ranges)
        unifi = _merge_unifi(settings, devices)
        if not devices and (ranges or settings.get('unifi_enabled')):
            # A scan that finds nothing is almost certainly a failure: don't
            # mark the whole network offline because of it.
            logger.warning("Network scan returned no devices; keeping previous online state")
            return {'found': 0, 'new_devices': 0, 'updated_devices': 0,
                    'ranges': [r['cidr'] for r in ranges], 'unifi': unifi}

        db.mark_all_offline()
        new_devices = []
        for device_data in devices:
            if device_data.get('mac_address'):
                saved = db.upsert_device_by_mac(device_data)
            else:
                saved = db.upsert_device_by_ip(device_data)
            if saved.get('_created'):
                new_devices.append(device_data)

        db.save_device_snapshot()
        try:
            db.refresh_hints(hint_service.guess)
        except Exception as e:
            logger.warning(f"Device hints failed: {e}")
        logger.info(f"Network scan completed: {len(devices)} devices found, {len(new_devices)} new")

        _notify_new_devices(settings, new_devices)

        return {
            'found': len(devices),
            'new_devices': len(new_devices),
            'updated_devices': len(devices) - len(new_devices),
            'ranges': [r['cidr'] for r in ranges],
            'unifi': unifi,
        }
    finally:
        _scan_lock.release()


def _merge_unifi(settings: dict, devices: list):
    """Add/enrich devices with the UniFi client list. Never fails the scan."""
    if not settings.get('unifi_enabled'):
        return None
    try:
        clients = unifi_service.fetch_clients(settings)
        stats = unifi_service.merge_clients(devices, clients, resolve_vendor, infer_device_type)
        logger.info(f"UniFi: {len(clients)} clients; {stats}")
        return {'clients': len(clients), **stats}
    except Exception as e:
        logger.error(f"UniFi client list failed: {e}")
        return {'error': str(e)}


def _telegram_target(settings: dict):
    """(bot_token, chat_id) if Telegram is enabled and configured, else None."""
    if not settings.get('telegram_enabled'):
        return None
    token, chat = settings.get('telegram_bot_token', ''), settings.get('telegram_chat_id', '')
    return (token, chat) if token and chat else None


def _panel(type_: str, data: dict, level: str = 'info'):
    """Store a notification for the bell panel (never breaks the caller)."""
    try:
        db.add_notification(type_, data, level)
    except Exception as e:
        logger.error(f"Could not store notification: {e}")


def _notify_new_devices(settings: dict, new_devices: list):
    if not new_devices:
        return
    if not settings.get('notify_new_devices', True):
        return
    _panel('new_devices', {'devices': [
        {k: d.get(k) for k in ('hostname', 'ip_address', 'mac_address', 'brand', 'device_type')}
        for d in new_devices[:50]], 'count': len(new_devices)})
    if send_new_device_alert is None or not _telegram_target(settings):
        return
    bot_token = settings.get('telegram_bot_token', '')
    chat_id = settings.get('telegram_chat_id', '')
    if bot_token and chat_id:
        try:
            send_new_device_alert(bot_token, chat_id, new_devices, db.server_language(settings))
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")


def perform_port_scan(device_id: int, profile: str = 'quick') -> dict:
    """Scan the ports of a device and merge the result into the DB.

    Raises TaskBusyError if this device is already being scanned or too many
    port scans are running, ValueError for a missing/invalid device or IP.
    """
    device = db.get_device(device_id)
    if not device:
        raise LookupError("Dispositivo no encontrado")
    if not device.get('ip_address'):
        raise ValueError("El dispositivo no tiene direccion IP")

    with _port_scan_guard:
        if device_id in _port_scans_running:
            raise TaskBusyError("Ya hay un escaneo de puertos en curso para este dispositivo")
        if len(_port_scans_running) >= MAX_PARALLEL_PORT_SCANS:
            raise TaskBusyError("Hay demasiados escaneos de puertos en curso, espera un momento")
        _port_scans_running.add(device_id)

    try:
        scan = scan_ports(device['ip_address'], profile)
        diff = db.save_port_scan(device_id, scan)
        try:
            db.refresh_hints(hint_service.guess)  # open ports improve the hint
        except Exception as e:
            logger.warning(f"Device hints failed: {e}")
        return {
            'device_id': device_id,
            'ip': scan['ip'],
            'profile': profile,
            'host_up': scan['host_up'],
            'duration': scan['duration'],
            'scanned_count': len(scan['scanned_ports']),
            **diff,
            'ports': db.get_device_ports(device_id),
        }
    finally:
        with _port_scan_guard:
            _port_scans_running.discard(device_id)


# ---------- Bulk port scan (all online devices) ----------

_bulk_lock = threading.Lock()
_bulk_state = {'running': False, 'total': 0, 'done': 0, 'current': None,
               'started_at': None, 'finished_at': None, 'summary': None}


def bulk_port_scan_status() -> dict:
    return dict(_bulk_state)


def perform_bulk_port_scan(profile: str = None, scope: str = None) -> dict:
    """Scan the ports of every online device, one at a time (leaving a slot
    free for manual scans). Notifies new/closed ports by Telegram."""
    if not _bulk_lock.acquire(blocking=False):
        raise TaskBusyError("Ya hay un escaneo de puertos de toda la red en curso")
    try:
        settings = db.get_settings()
        profile = profile or settings.get('port_scan_profile') or 'quick'
        scope = scope or settings.get('port_scan_scope') or 'online'
        targets = db.get_port_scan_targets(scope)
        _bulk_state.update(running=True, total=len(targets), done=0, current=None,
                           started_at=db.now_local(), finished_at=None, summary=None)
        logger.info(f"Bulk port scan ({profile}, {scope}): {len(targets)} devices")

        changes, errors, open_total = [], 0, 0
        for dev in targets:
            label = dev['custom_name'] or dev['hostname'] or dev['ip_address']
            _bulk_state['current'] = label
            result = None
            for _attempt in range(30):  # wait for a free slot (manual scans)
                try:
                    result = perform_port_scan(dev['id'], profile)
                    break
                except TaskBusyError:
                    time.sleep(5)
                except Exception as e:
                    logger.warning(f"Port scan of {label} ({dev['ip_address']}) failed: {e}")
                    errors += 1
                    break
            _bulk_state['done'] += 1
            if not result:
                continue
            open_total += len(result['ports'])
            if not result['first_scan'] and (result['new_ports'] or result['closed_ports']):
                changes.append({'name': label, 'ip': dev['ip_address'],
                                'new_ports': result['new_ports'],
                                'closed_ports': result['closed_ports']})

        summary = {'profile': profile, 'scope': scope, 'devices': len(targets),
                   'errors': errors, 'open_ports': open_total, 'changed_devices': len(changes)}
        _bulk_state.update(finished_at=db.now_local(), summary=summary)
        logger.info(f"Bulk port scan done: {summary}")
        _notify_port_changes(changes)
        return summary
    finally:
        _bulk_state.update(running=False, current=None)
        _bulk_lock.release()


def _notify_port_changes(changes: list):
    if not changes:
        return
    settings = db.get_settings()
    if not settings.get('notify_new_ports', True):
        return
    _panel('port_changes', {'changes': [
        {'name': c['name'], 'ip': c['ip'],
         'new_ports': [{'port': p['port'], 'service': p.get('service') or ''} for p in c['new_ports']],
         'closed_ports': [{'port': p['port'], 'service': p.get('service') or ''} for p in c['closed_ports']]}
        for c in changes]}, 'warning')
    target = _telegram_target(settings)
    if send_port_changes_alert is not None and target:
        token, chat = target
        try:
            send_port_changes_alert(token, chat, changes, db.server_language(settings))
        except Exception as e:
            logger.error(f"Port changes Telegram notification failed: {e}")


def start_bulk_port_scan_now():
    """Run the bulk port scan in the scheduler thread pool (non-blocking)."""
    if _bulk_lock.locked():
        raise TaskBusyError("Ya hay un escaneo de puertos de toda la red en curso")
    _bulk_state.update(running=True, total=0, done=0, current=None, summary=None)
    scheduler.add_job(scheduled_port_scan, id='port_scan_now', replace_existing=True)


def is_port_scan_in_progress(device_id: int) -> bool:
    return device_id in _port_scans_running


def is_scan_in_progress() -> bool:
    return _scan_lock.locked()


def is_test_in_progress() -> bool:
    return _test_lock.locked()


# ==========================================
#  Scheduled jobs
# ==========================================

def _notify_speed_test(result: dict):
    settings = db.get_settings()
    if not settings.get('notify_speed_tests'):
        return
    try:
        threshold = float(settings.get('speed_test_alert_threshold', 0) or 0)
    except ValueError:
        threshold = 0
    dl, ul = result.get('download_speed') or 0, result.get('upload_speed') or 0
    if threshold and dl >= threshold and ul >= threshold:
        return  # only notify when below the threshold
    slow = bool(threshold and (dl < threshold or ul < threshold))
    _panel('speed_test', {'download': dl, 'upload': ul, 'ping': result.get('ping'),
                          'jitter': result.get('jitter'), 'threshold': threshold, 'slow': slow,
                          'server': result.get('server_location') or result.get('server_name')},
           'warning' if slow else 'info')
    target = _telegram_target(settings)
    if send_speed_test_result is None or not target:
        return
    try:
        averages = db.get_speed_test_averages(7, exclude_id=result.get('id'))
        send_speed_test_result(*target, result, averages, threshold, db.server_language(settings))
    except Exception as e:
        logger.error(f"Speed test Telegram notification failed: {e}")


def scheduled_speed_test():
    try:
        logger.info("Running scheduled speed test...")
        result = perform_speed_test()
        logger.info("Scheduled speed test completed successfully")
    except TaskBusyError:
        logger.warning("Speed test already in progress, skipping scheduled run")
        return
    except Exception as e:
        logger.error(f"Scheduled speed test failed: {e}")
        settings = db.get_settings()
        if not settings.get('notify_speed_tests'):
            return
        _panel('speed_test_failed', {'error': str(e)[:300]}, 'error')
        target = _telegram_target(settings)
        if target and send_speed_test_failure is not None:
            try:
                send_speed_test_failure(*target, e, db.server_language())
            except Exception as te:
                logger.error(f"Speed test failure notification failed: {te}")
        return
    _notify_speed_test(result)


def scheduled_network_scan():
    try:
        perform_network_scan()
    except TaskBusyError:
        logger.warning("Network scan already in progress, skipping scheduled run")
    except Exception as e:
        logger.error(f"Scheduled network scan failed: {e}")


def scheduled_port_scan():
    try:
        perform_bulk_port_scan()
    except TaskBusyError:
        logger.warning("Bulk port scan already in progress, skipping")
    except Exception as e:
        logger.error(f"Bulk port scan failed: {e}")


def scheduled_cleanup():
    try:
        settings = db.get_settings()
        days = int(settings.get('speed_test_retention', 30) or 0)
        deleted = db.purge_old_data(days)
        if any(deleted.values()):
            logger.info(f"Retention cleanup ({days} days): {deleted}")

        if settings.get('purge_stale_devices', True):
            stale_days = int(settings.get('stale_device_days', 10) or 0)
            removed = db.purge_stale_devices(stale_days)
            if removed:
                logger.info(
                    f"Removed {len(removed)} unsaved devices without IP not seen for {stale_days}+ days: "
                    + ", ".join(f"{d['mac_address']} (last IP {d['last_ip']}, last seen {d['last_seen']})" for d in removed)
                )
    except Exception as e:
        logger.error(f"Retention cleanup failed: {e}")


# ==========================================
#  Scheduler management
# ==========================================

def _configure_jobs():
    settings = db.get_settings()

    for job_id in ('speed_test', 'network_scan', 'port_scan'):
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    if settings.get('auto_speed_test', True):
        freq = int(settings.get('speed_test_frequency', 60))
        scheduler.add_job(
            scheduled_speed_test,
            trigger=IntervalTrigger(minutes=freq),
            id='speed_test',
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Speed test scheduled every {freq} minutes")

    if settings.get('auto_network_scan', True):
        freq = int(settings.get('network_scan_frequency', 15))
        scheduler.add_job(
            scheduled_network_scan,
            trigger=IntervalTrigger(minutes=freq),
            id='network_scan',
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Network scan scheduled every {freq} minutes")

    if settings.get('auto_port_scan', False):
        hour = int(settings.get('port_scan_hour', 3) or 0) % 24
        try:
            tz = timezone(timedelta(hours=int(settings.get('timezone', 1))))
        except (TypeError, ValueError):
            tz = timezone(timedelta(hours=1))
        scheduler.add_job(
            scheduled_port_scan,
            trigger=CronTrigger(hour=hour, minute=0, timezone=tz),
            id='port_scan',
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info(f"Port scan of all devices scheduled daily at {hour:02d}:00")


def start_scheduler():
    """Start the background scheduler with configured intervals."""
    _configure_jobs()
    scheduler.add_job(
        scheduled_cleanup,
        trigger=IntervalTrigger(hours=6),
        id='cleanup',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    # Run one cleanup right away (in the scheduler thread, not blocking startup)
    scheduler.add_job(scheduled_cleanup, id='cleanup_startup', replace_existing=True)
    logger.info("Scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def update_schedule():
    """Update scheduler with new settings (and apply retention immediately)."""
    _configure_jobs()
    scheduler.add_job(scheduled_cleanup, id='cleanup_now', replace_existing=True)
