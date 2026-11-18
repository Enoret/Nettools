"""
NetTools - Internet outage monitor

Every `connectivity_interval` seconds the router (default gateway) and a few
Internet hosts are pinged (falling back to a TCP connection to port 443 /
53, for networks that block ICMP). An outage starts after
`connectivity_threshold` consecutive failed checks and ends with the first
good one:

  * kind 'internet': the router answers but Internet does not
  * kind 'gateway' : the router itself does not answer (LAN / router down)

Each check is stored (for the availability timeline) and each outage is an
event with start / end / duration.
"""

import logging
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

from network_service import ping_host, get_default_gateway

logger = logging.getLogger(__name__)

DEFAULT_TARGETS = '1.1.1.1,8.8.8.8'
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=4)

# in-memory state (consecutive failures per kind)
_state = {'fail_internet': 0, 'fail_gateway': 0}


def _tcp_ok(host: str, timeout: float = 2.0) -> bool:
    for port in (443, 53):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def probe(host: str) -> dict:
    """{'ok': bool, 'latency': ms or None} - ICMP first, TCP as fallback."""
    r = ping_host(host, timeout=2)
    if r.get('is_reachable'):
        return {'ok': True, 'latency': r.get('latency')}
    return {'ok': _tcp_ok(host), 'latency': None}


def parse_targets(value: str) -> list:
    targets = [t.strip() for t in (value or DEFAULT_TARGETS).replace(';', ',').split(',') if t.strip()]
    return targets[:5] or DEFAULT_TARGETS.split(',')


def check(settings: dict) -> dict:
    """One connectivity check (does not touch the database)."""
    gateway = get_default_gateway()
    targets = parse_targets(settings.get('connectivity_targets'))
    futures = {t: _pool.submit(probe, t) for t in targets}
    gw_future = _pool.submit(probe, gateway) if gateway else None

    results = {t: f.result() for t, f in futures.items()}
    internet_ok = any(r['ok'] for r in results.values())
    latencies = [r['latency'] for r in results.values() if r['ok'] and r['latency'] is not None]
    gateway_ok = gw_future.result()['ok'] if gw_future else None
    return {
        'gateway': gateway,
        'gateway_ok': gateway_ok,
        'internet_ok': internet_ok,
        'latency': round(min(latencies), 1) if latencies else None,
        'targets': {t: r['ok'] for t, r in results.items()},
    }


def run_check(db, notify) -> dict:
    """Check, store the sample and open/close outage events.
    `notify(kind, event_dict, phase)` is called with phase 'start' / 'end'."""
    if not _lock.acquire(blocking=False):
        return {}
    try:
        settings = db.get_settings()
        res = check(settings)
        try:
            threshold = max(1, int(settings.get('connectivity_threshold', 2) or 2))
        except ValueError:
            threshold = 2
        db.save_connectivity_check(res['gateway_ok'], res['internet_ok'], res['latency'])

        # kind of failure in this check
        if res['internet_ok']:
            kind = None
        elif res['gateway_ok'] is False:
            kind = 'gateway'
        else:
            kind = 'internet'

        open_event = db.get_open_outage()
        if kind is None:
            _state['fail_internet'] = _state['fail_gateway'] = 0
            if open_event:
                ev = db.close_outage(open_event['id'])
                logger.warning(f"Connectivity restored after {ev['duration']}s ({ev['kind']})")
                notify(ev['kind'], ev, 'end')
        else:
            key = f'fail_{kind}'
            _state[key] += 1
            if open_event:
                db.touch_outage(open_event['id'])
            elif _state[key] >= threshold:
                ev = db.open_outage(kind, threshold, int(settings.get('connectivity_interval', 60) or 60))
                logger.warning(f"Outage detected: {kind} ({_state[key]} failed checks)")
                notify(kind, ev, 'start')
        res['outage'] = kind if (kind and (open_event or _state.get(f'fail_{kind}', 0) >= threshold)) else None
        return res
    finally:
        _lock.release()
