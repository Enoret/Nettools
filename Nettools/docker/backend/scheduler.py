"""
NetTools - Background Task Scheduler
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import database as db
from speedtest_service import run_speed_test
from network_service import scan_network

try:
    from telegram_service import send_new_device_alert
except ImportError:
    send_new_device_alert = None

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_scan_in_progress = False
_test_in_progress = False


def start_scheduler():
    """Start the background scheduler with configured intervals."""
    settings = db.get_settings()

    # Speed test job
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

    # Network scan job
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

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def update_schedule():
    """Update scheduler with new settings."""
    settings = db.get_settings()

    # Update speed test
    try:
        scheduler.remove_job('speed_test')
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
        logger.info(f"Speed test rescheduled every {freq} minutes")

    # Update network scan
    try:
        scheduler.remove_job('network_scan')
    except Exception:
        pass

    if settings.get('auto_network_scan', True):
        freq = int(settings.get('network_scan_frequency', 15))
        scheduler.add_job(
            scheduled_network_scan,
            trigger=IntervalTrigger(minutes=freq),
            id='network_scan',
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Network scan rescheduled every {freq} minutes")


def scheduled_speed_test():
    """Run a scheduled speed test."""
    global _test_in_progress
    if _test_in_progress:
        logger.warning("Speed test already in progress, skipping")
        return

    try:
        _test_in_progress = True
        logger.info("Running scheduled speed test...")
        result = run_speed_test()
        db.save_speed_test(result)
        logger.info("Scheduled speed test completed successfully")
    except Exception as e:
        logger.error(f"Scheduled speed test failed: {e}")
    finally:
        _test_in_progress = False


def scheduled_network_scan():
    """Run a scheduled network scan."""
    global _scan_in_progress
    if _scan_in_progress:
        logger.warning("Network scan already in progress, skipping")
        return

    try:
        _scan_in_progress = True
        settings = db.get_settings()
        network_range = settings.get('network_range', '192.168.1.0/24')

        logger.info(f"Running scheduled network scan on {network_range}...")

        # Collect existing MAC addresses before the scan
        existing_macs = db.get_all_mac_addresses()

        db.mark_all_offline()
        devices = scan_network(network_range)

        new_devices = []
        for device_data in devices:
            db.upsert_device_by_mac(device_data)
            mac = device_data.get('mac_address', '')
            if mac and mac not in existing_macs:
                new_devices.append(device_data)

        # Save historical snapshot
        db.save_device_snapshot()
        logger.info(f"Scheduled network scan completed: {len(devices)} devices found, {len(new_devices)} new")

        # Send Telegram notification for new devices
        if new_devices and send_new_device_alert and settings.get('telegram_enabled', False):
            bot_token = settings.get('telegram_bot_token', '')
            chat_id = settings.get('telegram_chat_id', '')
            if bot_token and chat_id:
                send_new_device_alert(bot_token, chat_id, new_devices)
    except Exception as e:
        logger.error(f"Scheduled network scan failed: {e}")
    finally:
        _scan_in_progress = False


def is_scan_in_progress() -> bool:
    return _scan_in_progress


def is_test_in_progress() -> bool:
    return _test_in_progress
