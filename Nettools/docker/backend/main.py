"""
NetTools - FastAPI Backend
Main application entry point
"""

import json
import base64
import hashlib
import secrets
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from typing import Optional, List
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

import database as db
from oui_service import resolve_vendor, normalize_mac
from models import (
    DeviceCreate, DeviceUpdate, PingRequest, PingBatchRequest,
    PingResult, SettingsUpdate, ScanResult, InventoryItem, DeviceBulk
)
from speedtest_service import get_servers
from network_service import ping_host, get_local_networks, get_default_gateway, resolve_ranges, describe_range, parse_cidr, parse_range_list
from traceroute_service import run_traceroute
import unifi_service
import logo_service
import hint_service
from nslookup_service import run_nslookup, reverse_lookup
from scheduler import (
    start_scheduler, stop_scheduler, update_schedule,
    is_scan_in_progress, is_test_in_progress,
    perform_speed_test, perform_network_scan, TaskBusyError,
    perform_port_scan, is_port_scan_in_progress,
    start_bulk_port_scan_now, bulk_port_scan_status,
)

try:
    from telegram_service import test_connection as telegram_test_connection
except ImportError:
    telegram_test_connection = None

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=8)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting NetTools Backend...")
    db.init_db()
    try:
        filled = db.backfill_vendors(lambda mac: resolve_vendor(mac))
        released = db.fix_ip_conflicts()
        hints = db.refresh_hints(hint_service.guess)
        db.close_stale_outages()
        if filled or released or hints:
            logger.info(f"Startup maintenance: {filled} vendors updated, {released} stale IPs released, "
                        f"{hints} device hints updated")
    except Exception as e:
        logger.error(f"Startup maintenance failed: {e}")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("NetTools Backend stopped")


app = FastAPI(
    title="NetTools API",
    description="API para monitoreo de red y tests de velocidad",
    version="1.3.1",
    lifespan=lifespan,
)

# CORS
# No CORS middleware: the UI is always served from the same origin (nginx),
# and allowing any origin with credentials would expose the session cookie.

import auth_service

PUBLIC_API = ('/api/health', '/api/auth/status', '/api/auth/login', '/api/auth/logout',
              '/api/auth/oidc/start', '/api/auth/oidc/callback')


@app.middleware("http")
async def require_login(request: Request, call_next):
    """When the login is enabled every /api call needs a valid session."""
    path = request.url.path
    if path.startswith('/api/') and path not in PUBLIC_API:
        settings = db.get_settings()
        if auth_service.is_enabled(settings):
            session = db.get_session(request.cookies.get(auth_service.COOKIE))
            if not session:
                return JSONResponse({'detail': 'No autenticado', 'auth_required': True}, status_code=401)
            request.state.user = session
    return await call_next(request)


def _client_ip(request: Request) -> str:
    return (request.headers.get('x-real-ip') or (request.client.host if request.client else '') or '?')


def _is_https(request: Request) -> bool:
    return request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'


def _redirect_uri(request: Request, settings: dict) -> str:
    configured = (settings.get('auth_oidc_redirect_uri') or '').strip()
    if configured:
        return configured
    proto = request.headers.get('x-forwarded-proto', request.url.scheme)
    host = request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc
    return f"{proto}://{host}/api/auth/oidc/callback"


def _safe_next(next_url: str) -> str:
    # only local paths / hashes (no open redirect)
    if not next_url or not next_url.startswith(('/', '#')) or next_url.startswith('//'):
        return '/'
    return next_url if next_url.startswith('/') else '/' + next_url


def _login_response(request: Request, user: dict, settings: dict, redirect: str = None):
    token = secrets.token_urlsafe(32)
    try:
        days = int(settings.get('auth_session_days', 7) or 7)
    except ValueError:
        days = 7
    db.create_session(token, user['username'], user['method'], days,
                      user.get('name'), user.get('avatar'))
    resp = RedirectResponse(redirect, status_code=303) if redirect else JSONResponse(
        {'ok': True, 'user': user['username'], 'method': user['method']})
    resp.set_cookie(auth_service.COOKIE, token, max_age=days * 86400, httponly=True,
                    samesite='lax', secure=_is_https(request), path='/')
    logger.info(f"Login: {user['username']} ({user['method']}) from {_client_ip(request)}")
    return resp


# ==========================================
#  AUTH (login)
# ==========================================

class LoginRequest(BaseModel):
    username: str = ''
    password: str = ''


@app.get("/api/auth/status")
async def auth_status(request: Request):
    settings = db.get_settings()
    enabled = auth_service.is_enabled(settings)
    session = db.get_session(request.cookies.get(auth_service.COOKIE)) if enabled else None
    return {
        'enabled': enabled,
        'authenticated': (not enabled) or bool(session),
        'user': session['username'] if session else None,
        'name': (session.get('display_name') or session['username']) if session else None,
        # the picture is served by /api/auth/avatar (cacheable), not inline
        'avatar': (session['avatar'] if session['avatar'].startswith('https://')
                   else f"/api/auth/avatar?v={hashlib.sha1(session['avatar'].encode()).hexdigest()[:10]}")
                  if session and session.get('avatar') else None,
        'method': session['method'] if session else None,
        'methods': auth_service.methods(settings),
        'disabled_by_env': auth_service.auth_disabled_by_env(),
    }


@app.get("/api/auth/avatar")
async def auth_avatar(request: Request):
    """Profile picture of the signed-in user (from LDAP jpegPhoto)."""
    session = db.get_session(request.cookies.get(auth_service.COOKIE))
    avatar = (session or {}).get('avatar') or ''
    if not avatar.startswith('data:image/'):
        raise HTTPException(status_code=404, detail="Sin avatar")
    header, b64 = avatar.split(',', 1)
    mime = header[5:].split(';')[0]
    from fastapi.responses import Response
    return Response(base64.b64decode(b64), media_type=mime,
                    headers={'Cache-Control': 'private, max-age=86400'})


@app.post("/api/auth/login")
async def auth_login(data: LoginRequest, request: Request):
    settings = db.get_settings()
    ip = _client_ip(request)
    if auth_service.too_many_failures(ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos fallidos. Espera unos minutos.")
    user = auth_service.check_local(settings, data.username, data.password)
    if not user and auth_service.methods(settings)['ldap']:
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(executor, auth_service.check_ldap, settings, data.username, data.password)
    if not user:
        auth_service.record_failure(ip)
        logger.warning(f"Failed login for '{data.username}' from {ip}")
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos")
    auth_service.clear_failures(ip)
    return _login_response(request, user, settings)


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    db.delete_session(request.cookies.get(auth_service.COOKIE))
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(auth_service.COOKIE, path='/')
    return resp


@app.get("/api/auth/oidc/start")
async def auth_oidc_start(request: Request, next: str = '/'):
    settings = db.get_settings()
    if not auth_service.methods(settings)['oidc']:
        return RedirectResponse('/login.html?error=oidc_disabled', status_code=303)
    redirect_uri = _redirect_uri(request, settings)
    try:
        loop = asyncio.get_event_loop()
        url, state, verifier, nonce = await loop.run_in_executor(
            executor, auth_service.oidc_start, settings, redirect_uri)
    except auth_service.AuthError as e:
        logger.error(f"OIDC start failed: {e}")
        return RedirectResponse('/login.html?error=oidc_unavailable', status_code=303)
    db.save_oidc_state(state, verifier, nonce, _safe_next(next), redirect_uri)
    return RedirectResponse(url, status_code=303)


@app.get("/api/auth/oidc/callback")
async def auth_oidc_callback(request: Request, code: str = '', state: str = '', error: str = ''):
    settings = db.get_settings()
    if error:
        logger.warning(f"OIDC provider returned error: {error}")
        return RedirectResponse('/login.html?error=oidc_denied', status_code=303)
    saved = db.pop_oidc_state(state)
    if not saved or not code:
        return RedirectResponse('/login.html?error=oidc_state', status_code=303)
    try:
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(executor, auth_service.oidc_finish, settings, code,
                                          saved['redirect_uri'], saved['verifier'], saved['nonce'])
    except auth_service.AuthError as e:
        logger.warning(f"OIDC login rejected: {e}")
        kind = 'oidc_group' if 'grupo' in str(e) else 'oidc_failed'
        return RedirectResponse(f'/login.html?error={kind}', status_code=303)
    return _login_response(request, user, settings, redirect=saved['next'] or '/')


class LdapTestRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/test/ldap")
async def auth_test_ldap(data: LdapTestRequest):
    """Try an LDAP login with the saved settings (does not create a session)."""
    settings = db.get_settings()
    loop = asyncio.get_event_loop()
    try:
        user = await loop.run_in_executor(executor, lambda: auth_service.check_ldap(
            {**settings, 'auth_ldap_enabled': True}, data.username, data.password, True))
    except auth_service.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True, 'username': user['username'], 'groups': user.get('groups', [])}


@app.post("/api/auth/test/oidc")
async def auth_test_oidc(request: Request):
    settings = db.get_settings()
    loop = asyncio.get_event_loop()
    try:
        d = await loop.run_in_executor(executor, auth_service.discovery, settings)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True, 'issuer': d.get('issuer'), 'redirect_uri': _redirect_uri(request, settings),
            'scopes_supported': d.get('scopes_supported')}


# --- Health ---
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "NetTools"}


# ==========================================
#  SPEED TEST ENDPOINTS
# ==========================================

class SpeedTestRunRequest(BaseModel):
    server_id: Optional[str] = None


@app.post("/api/speedtest/run")
async def run_speedtest(data: SpeedTestRunRequest = SpeedTestRunRequest()):
    """Run a new speed test, optionally against a specific server."""
    if is_test_in_progress():
        raise HTTPException(status_code=409, detail="Ya hay un test en curso")

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(executor, perform_speed_test, data.server_id)
    except TaskBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/speedtest/servers")
async def get_speedtest_servers():
    """Get list of available speedtest servers sorted by distance."""
    loop = asyncio.get_event_loop()
    try:
        servers = await loop.run_in_executor(executor, get_servers)
        return servers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/speedtest/results")
async def get_speedtest_results(
    range: str = Query('24h', description="Time range: 1h, 6h, 24h, 7d, 30d, 90d, 365d, all"),
    limit: int = Query(500, ge=1, le=10000),
):
    """Get speed test history."""
    return db.get_speed_tests(range_filter=range, limit=limit)


@app.get("/api/speedtest/latest")
async def get_latest_speedtest():
    """Get the most recent speed test result."""
    result = db.get_latest_speed_test()
    if not result:
        raise HTTPException(status_code=404, detail="No hay tests registrados")
    return result


@app.get("/api/speedtest/stats")
async def get_speedtest_stats():
    """Get speed test statistics."""
    return db.get_speed_test_stats()


@app.get("/api/speedtest/status")
async def get_speedtest_status():
    """Check if a speed test is currently running."""
    return {"in_progress": is_test_in_progress()}


@app.delete("/api/speedtest/results/{test_id}")
async def delete_speedtest(test_id: int):
    """Delete a specific speed test result."""
    # Simple delete without checking existence for simplicity
    conn = db.get_db()
    conn.execute("DELETE FROM speed_tests WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.delete("/api/speedtest/results")
async def clear_all_speedtests():
    """Delete all speed test results."""
    db.clear_speed_tests()
    return {"status": "cleared"}


# ==========================================
#  DEVICE ENDPOINTS
# ==========================================

@app.get("/api/devices")
async def get_devices(
    status: Optional[str] = Query(None, description="Filter by status: new, saved, manual"),
):
    """Get all network devices."""
    return db.get_devices(status_filter=status)


@app.get("/api/devices/history")
async def get_device_history(
    range: str = Query('24h', description="Time range: 1h, 6h, 24h, 7d, 30d, 90d, 365d, all"),
    limit: int = Query(500, ge=1, le=10000),
):
    """Get device count history (snapshots over time)."""
    return db.get_device_snapshots(range_filter=range, limit=limit)


# NOTE: routes with fixed paths (/history, /scan/...) must be declared
# before /{device_id}, otherwise FastAPI matches them as a device id.
@app.get("/api/devices/{device_id}")
async def get_device(device_id: int):
    """Get a specific device."""
    device = db.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


class PortScanRequest(BaseModel):
    profile: Optional[str] = 'quick'


@app.get("/api/devices/{device_id}/ports")
async def get_device_ports(device_id: int):
    """Get the known open ports of a device."""
    device = db.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return {
        'device_id': device_id,
        'last_port_scan': device.get('last_port_scan'),
        'in_progress': is_port_scan_in_progress(device_id),
        'ports': db.get_device_ports(device_id),
    }


# ==========================================
#  INTERNET MONITOR
# ==========================================

@app.get("/api/connectivity")
async def connectivity(range: str = Query('24h', pattern='^(24h|7d|30d)$')):
    """Availability summary, timeline and outages."""
    return db.get_connectivity(range)


@app.post("/api/connectivity/check")
async def connectivity_check_now():
    """Run a check now (without storing it) - used by the settings test button."""
    import connectivity_service
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, connectivity_service.check, db.get_settings())


# ==========================================
#  NOTIFICATIONS (bell panel)
# ==========================================

@app.get("/api/notifications")
async def list_notifications(limit: int = Query(50, ge=1, le=200)):
    return db.get_notifications(limit)


@app.post("/api/notifications/read-all")
async def read_all_notifications():
    return {"updated": db.mark_notifications_read()}


@app.post("/api/notifications/{notification_id}/read")
async def read_notification(notification_id: int):
    return {"updated": db.mark_notifications_read(notification_id)}


@app.post("/api/ports/scan-all")
async def scan_all_ports():
    """Start a port scan of every online device in the background."""
    try:
        start_bulk_port_scan_now()
    except TaskBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {'started': True}


@app.get("/api/ports/scan-all/status")
async def scan_all_ports_status():
    return bulk_port_scan_status()


@app.post("/api/devices/{device_id}/ports/scan")
async def scan_device_ports(device_id: int, data: PortScanRequest = PortScanRequest()):
    """Scan the TCP ports of a device (profile: quick | full)."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            executor, perform_port_scan, device_id, data.profile or 'quick'
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TaskBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices")
async def create_device(data: DeviceCreate):
    """Create a new device manually."""
    payload = data.model_dump(exclude_none=True)
    _normalize_mac_field(payload)
    if payload.get('mac_address') and not payload.get('brand'):
        payload['brand'] = resolve_vendor(payload['mac_address'])
    return db.create_device(payload)


def _normalize_mac_field(payload: dict):
    """Store MACs as AA:BB:CC:DD:EE:FF so scans can match manual entries."""
    mac = payload.get('mac_address')
    if mac:
        normalized = normalize_mac(mac)
        if not normalized:
            raise HTTPException(status_code=400, detail=f"MAC no valida: {mac}")
        payload['mac_address'] = normalized


@app.put("/api/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    """Update a device."""
    existing = db.get_device(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    update_data = data.model_dump(exclude_none=True)
    _normalize_mac_field(update_data)
    # When user edits a 'new' device, mark it as 'saved'
    if existing['status'] == 'new' and 'status' not in update_data:
        update_data['status'] = 'saved'

    return db.update_device(device_id, update_data)


class MergeRequest(BaseModel):
    source_id: int


@app.post("/api/devices/{device_id}/wol")
async def wake_device(device_id: int):
    """Send a Wake-on-LAN magic packet to a device."""
    import wol_service
    device = db.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    if not device.get('mac_address'):
        raise HTTPException(status_code=400, detail="El dispositivo no tiene MAC: no se puede encender por red")
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor, wol_service.wake, device['mac_address'], device.get('ip_address') or device.get('last_ip'))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/api/devices/{device_id}/merge")
async def merge_device(device_id: int, data: MergeRequest):
    """Merge device `source_id` into `device_id` (the target keeps its name and
    details and adopts the source's MAC/IP; the source is deleted)."""
    try:
        return db.merge_devices(device_id, data.source_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


DEVICE_TYPES = {'other', 'router', 'switch', 'ap', 'server', 'desktop', 'laptop', 'phone', 'tablet',
                'printer', 'camera', 'iot', 'nas', 'tv', 'gaming'}


@app.post("/api/devices/bulk")
async def bulk_devices(data: DeviceBulk):
    """Delete or update several devices at once."""
    ids = sorted({int(i) for i in data.ids})
    if not ids:
        raise HTTPException(status_code=400, detail="No hay dispositivos seleccionados")
    if len(ids) > 1000:
        raise HTTPException(status_code=400, detail="Demasiados dispositivos")
    if data.action == 'delete':
        db.sync_inventory()  # saved devices keep their inventory sheet
        return {"deleted": db.bulk_delete_devices(ids)}
    if data.action == 'update':
        if data.status not in (None, 'saved', 'new'):
            raise HTTPException(status_code=400, detail="Estado no valido")
        if data.device_type is not None and data.device_type not in DEVICE_TYPES:
            raise HTTPException(status_code=400, detail="Tipo no valido")
        location = data.location.strip() if data.location is not None else None
        updated = db.bulk_update_devices(ids, data.status, data.device_type, location)
        return {"updated": updated}
    raise HTTPException(status_code=400, detail="Accion no valida")


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int):
    """Delete a device (a saved device keeps its inventory sheet)."""
    db.sync_inventory()
    db.delete_device(device_id)
    return {"status": "deleted"}


@app.delete("/api/devices")
async def clear_all_devices():
    """Delete all devices."""
    db.clear_devices()
    return {"status": "cleared"}


@app.post("/api/devices/scan")
async def scan_devices():
    """Trigger a network scan."""
    if is_scan_in_progress():
        raise HTTPException(status_code=409, detail="Ya hay un escaneo en curso")

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(executor, perform_network_scan)
    except TaskBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/scan/status")
async def scan_status():
    """Check if a network scan is in progress."""
    return {"in_progress": is_scan_in_progress()}


# ==========================================
#  NETWORK RANGES
# ==========================================

@app.get("/api/network/info")
async def network_info():
    """Local networks of the server and the ranges the scan will cover."""
    settings = db.get_settings()
    return {
        'local_networks': get_local_networks(),
        'gateway': get_default_gateway(),
        'ranges': resolve_ranges(settings),
    }


@app.get("/api/network/check")
async def network_check(cidr: str = Query(..., description="IPv4 range, e.g. 192.168.20.0/24")):
    """Validate a range and tell how it would be scanned (arp / routed)."""
    try:
        return describe_range(parse_cidr(cidr))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
#  PING ENDPOINTS
# ==========================================

@app.post("/api/ping")
async def ping_single(data: PingRequest):
    """Ping a single IP address."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, ping_host, data.ip)

    # Try to find device name
    conn = db.get_db()
    device = conn.execute(
        "SELECT custom_name, hostname FROM devices WHERE ip_address = ?",
        (data.ip,)
    ).fetchone()
    conn.close()

    if device:
        result['name'] = device['custom_name'] or device['hostname'] or ''

    # Save ping result
    db.save_ping_result({
        'ip_address': data.ip,
        'latency': result.get('latency'),
        'is_reachable': 1 if result.get('is_reachable') else 0,
    })

    return result


@app.post("/api/ping/batch")
async def ping_batch(data: PingBatchRequest):
    """Ping multiple IP addresses."""
    loop = asyncio.get_event_loop()

    async def ping_one(ip):
        return await loop.run_in_executor(executor, ping_host, ip)

    tasks = [ping_one(ip) for ip in data.ips]
    results = await asyncio.gather(*tasks)
    return results


# ==========================================
#  TRACEROUTE ENDPOINTS
# ==========================================

class TracerouteRequest(BaseModel):
    target: str
    max_hops: Optional[int] = 30


@app.post("/api/traceroute")
async def traceroute(data: TracerouteRequest):
    """Run a traceroute to the specified target."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            lambda: run_traceroute(data.target, max_hops=data.max_hops or 30)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
#  NSLOOKUP / DNS ENDPOINTS
# ==========================================

class NSLookupRequest(BaseModel):
    domain: str
    dns_server: Optional[str] = None
    record_type: Optional[str] = "A"


class ReverseLookupRequest(BaseModel):
    ip: str


@app.post("/api/nslookup")
async def nslookup(data: NSLookupRequest):
    """Run a DNS lookup for the specified domain."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            lambda: run_nslookup(
                data.domain,
                dns_server=data.dns_server,
                record_type=data.record_type or "A"
            )
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nslookup/reverse")
async def nslookup_reverse(data: ReverseLookupRequest):
    """Run a reverse DNS lookup for the specified IP."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            lambda: reverse_lookup(data.ip)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
#  SETTINGS ENDPOINTS
# ==========================================

@app.get("/api/settings")
async def get_settings():
    """Get all settings (secrets are never returned, only '<key>_set')."""
    return db.get_public_settings()


@app.put("/api/settings")
async def update_settings(data: SettingsUpdate):
    """Update settings."""
    settings_data = data.model_dump(exclude_none=True)
    # Secrets: an empty value means "keep the stored one"
    for key in db.SECRET_SETTINGS:
        if key in settings_data and not settings_data[key]:
            del settings_data[key]
    settings_data.pop('auth_local_password_hash', None)
    new_password = settings_data.pop('auth_local_password', None)
    if new_password:
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="La contrasena debe tener al menos 8 caracteres")
        settings_data['auth_local_password_hash'] = auth_service.hash_password(new_password)
    if 'auth_session_days' in settings_data:
        try:
            assert 1 <= int(settings_data['auth_session_days']) <= 90
        except (ValueError, AssertionError):
            raise HTTPException(status_code=400, detail="Duracion de sesion no valida")
    merged = {**db.get_settings(), **settings_data}
    if merged.get('auth_enabled'):
        m = auth_service.methods(merged)
        if not (m['local'] or m['ldap'] or m['oidc']):
            raise HTTPException(status_code=400, detail="Para activar el inicio de sesion configura al menos un metodo: "
                                                        "usuario local con contrasena, LDAP o SSO")
    password_changed = 'auth_local_password_hash' in settings_data
    if 'network_ranges' in settings_data:
        try:
            settings_data['network_ranges'] = ','.join(parse_range_list(settings_data['network_ranges']))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if settings_data.get('unifi_url'):
        try:
            settings_data['unifi_url'] = unifi_service._base_url(settings_data['unifi_url'])
        except unifi_service.UnifiError as e:
            raise HTTPException(status_code=400, detail=str(e))
    for key in ('view_netalert', 'view_inventory'):
        if key in settings_data:
            try:
                cfg = json.loads(settings_data[key])
                assert isinstance(cfg, dict) and isinstance(cfg.get('columns'), list) and len(settings_data[key]) < 4000
            except Exception:
                raise HTTPException(status_code=400, detail="Configuracion de columnas no valida")
    if 'connectivity_targets' in settings_data:
        import re as _re
        targets = [t.strip() for t in settings_data['connectivity_targets'].replace(';', ',').split(',') if t.strip()]
        if not targets or len(targets) > 5 or any(not _re.fullmatch(r'[A-Za-z0-9.\-:]+', t) for t in targets):
            raise HTTPException(status_code=400, detail="Destinos no validos (hasta 5 IPs o dominios separados por comas)")
        settings_data['connectivity_targets'] = ','.join(targets)
    if 'connectivity_interval' in settings_data:
        try:
            assert 15 <= int(settings_data['connectivity_interval']) <= 600
        except (ValueError, AssertionError):
            raise HTTPException(status_code=400, detail="Intervalo no valido")
    if settings_data.get('language') not in (None, 'auto', 'es', 'en'):
        raise HTTPException(status_code=400, detail="Idioma no valido")
    if settings_data.get('ui_language') not in (None, 'es', 'en'):
        raise HTTPException(status_code=400, detail="Idioma no valido")
    if settings_data.get('port_scan_profile') not in (None, 'quick', 'full'):
        raise HTTPException(status_code=400, detail="Perfil de escaneo no valido")
    if settings_data.get('port_scan_scope') not in (None, 'online', 'saved'):
        raise HTTPException(status_code=400, detail="Alcance de escaneo no valido")
    if settings_data.get('unifi_auth') not in (None, 'api_key', 'login'):
        raise HTTPException(status_code=400, detail="unifi_auth debe ser 'api_key' o 'login'")
    old_lang = db.server_language()
    db.update_settings(settings_data)
    if db.server_language() != old_lang:
        # device hints are stored as text: regenerate them in the new language
        db.refresh_hints(hint_service.guess)

    if password_changed:
        db.delete_all_sessions()  # log everybody out after a password change

    # Update scheduler with new settings
    update_schedule()

    return db.get_public_settings()


@app.post("/api/settings/telegram/test")
async def test_telegram():
    """Send a test message to the configured Telegram chat."""
    if telegram_test_connection is None:
        raise HTTPException(status_code=500, detail="Modulo de Telegram no disponible. Reconstruye la imagen Docker.")

    settings = db.get_settings()
    bot_token = settings.get('telegram_bot_token', '')
    chat_id = settings.get('telegram_chat_id', '')

    if not bot_token or not chat_id:
        raise HTTPException(status_code=400, detail="Bot Token y Chat ID son obligatorios. Guarda la configuracion primero.")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, telegram_test_connection, bot_token, chat_id,
                                        db.server_language(settings))

    if result['success']:
        return result
    else:
        raise HTTPException(status_code=400, detail=result['message'])


@app.post("/api/settings/unifi/test")
async def test_unifi(data: SettingsUpdate = None):
    """Test the UniFi connection with the saved settings, overridden by the
    (possibly unsaved) values sent in the body."""
    settings = db.get_settings()
    if data is not None:
        settings.update({k: v for k, v in data.model_dump(exclude_none=True).items()
                         if k.startswith('unifi_') and (v or k not in db.SECRET_SETTINGS)})
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(executor, unifi_service.test_connection, settings)
    except unifi_service.UnifiError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("UniFi test failed")
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")


# ==========================================
#  INVENTORY
# ==========================================

def _validate_inventory(payload: dict):
    import re
    for k in ('purchase_date', 'warranty_until'):
        v = payload.get(k)
        if v and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
            raise HTTPException(status_code=400, detail=f"Fecha no valida ({k}): usa AAAA-MM-DD")
    if payload.get('asset_kind') not in (None, 'physical', 'vm', 'lxc', 'docker'):
        raise HTTPException(status_code=400, detail="Tipo de activo no valido")
    if payload.get('asset_status') not in (None, 'active', 'retired'):
        raise HTTPException(status_code=400, detail="Estado no valido")
    if payload.get('purchase_price') is not None and payload['purchase_price'] < 0:
        raise HTTPException(status_code=400, detail="El precio no puede ser negativo")
    _normalize_mac_field(payload)


@app.get("/api/inventory")
async def list_inventory():
    """Inventory: saved/manual devices from Net Alert plus items added here."""
    return db.get_inventory()


@app.post("/api/inventory")
async def create_inventory_item(data: InventoryItem):
    payload = data.model_dump(exclude_none=True)
    if not (payload.get('name') or '').strip():
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    _validate_inventory(payload)
    return db.create_inventory_item(payload)


@app.put("/api/inventory/{item_id}")
async def update_inventory_item(item_id: int, data: InventoryItem):
    payload = data.model_dump(exclude_unset=True)
    _validate_inventory({k: v for k, v in payload.items() if v is not None})
    if payload.get('mac_address'):
        payload['mac_address'] = normalize_mac(payload['mac_address'])
    try:
        item = db.update_inventory_item(item_id, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return item


@app.delete("/api/inventory/{item_id}")
async def delete_inventory_item(item_id: int):
    if not db.delete_inventory_item(item_id):
        raise HTTPException(status_code=404, detail="Elemento de inventario no encontrado")
    return {"deleted": True}


# ==========================================
#  MANUFACTURER LOGOS
# ==========================================

class LogoUpload(BaseModel):
    brand: str
    data_url: str


@app.get("/api/logos")
def get_logo(brand: str = Query(...)):
    """Logo of a manufacturer (uploaded, Simple Icons or website icon)."""
    path = logo_service.get_logo(brand)
    if not path:
        raise HTTPException(status_code=404, detail="Sin logo")
    return FileResponse(path, media_type=logo_service.content_type(path), headers={
        'Cache-Control': 'public, max-age=86400',
        # SVGs are only displayed as images: never let them run anything
        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
        'X-Content-Type-Options': 'nosniff',
    })


@app.get("/api/logos/info")
def logo_info(brand: str = Query(...)):
    return {'key': logo_service.brand_key(brand), 'custom': logo_service.has_custom_logo(brand)}


@app.post("/api/logos")
def upload_logo(data: LogoUpload):
    try:
        key = logo_service.save_custom_logo(data.brand, data.data_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'key': key, 'custom': True}


@app.delete("/api/logos")
def delete_logo(brand: str = Query(...)):
    return {'deleted': logo_service.delete_custom_logo(brand)}


# ==========================================
#  EXPORT
# ==========================================

@app.get("/api/export")
async def export_data():
    """Export all data as JSON."""
    return db.get_all_data()


# ==========================================
#  Run
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
