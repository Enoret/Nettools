"""
NetTools - FastAPI Backend
Main application entry point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

import database as db
from models import (
    DeviceCreate, DeviceUpdate, PingRequest, PingBatchRequest,
    PingResult, SettingsUpdate, ScanResult
)
from speedtest_service import run_speed_test, get_servers
from network_service import scan_network, ping_host
from traceroute_service import run_traceroute
from nslookup_service import run_nslookup, reverse_lookup
from scheduler import start_scheduler, stop_scheduler, update_schedule, is_scan_in_progress, is_test_in_progress

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
executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting NetTools Backend...")
    db.init_db()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("NetTools Backend stopped")


app = FastAPI(
    title="NetTools API",
    description="API para monitoreo de red y tests de velocidad",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        server_id = data.server_id
        result = await loop.run_in_executor(executor, run_speed_test, server_id)
        saved = db.save_speed_test(result)
        return saved
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


@app.get("/api/devices/{device_id}")
async def get_device(device_id: int):
    """Get a specific device."""
    device = db.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@app.post("/api/devices")
async def create_device(data: DeviceCreate):
    """Create a new device manually."""
    return db.create_device(data.model_dump(exclude_none=True))


@app.put("/api/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    """Update a device."""
    existing = db.get_device(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    update_data = data.model_dump(exclude_none=True)
    # When user edits a 'new' device, mark it as 'saved'
    if existing['status'] == 'new' and 'status' not in update_data:
        update_data['status'] = 'saved'

    return db.update_device(device_id, update_data)


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int):
    """Delete a device."""
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

    settings = db.get_settings()
    network_range = settings.get('network_range', '192.168.1.0/24')

    loop = asyncio.get_event_loop()

    def do_scan():
        db.mark_all_offline()
        devices = scan_network(network_range)
        new_count = 0
        updated_count = 0

        for device_data in devices:
            existing = None
            if device_data.get('mac_address'):
                conn = db.get_db()
                existing = conn.execute(
                    "SELECT id FROM devices WHERE mac_address = ?",
                    (device_data['mac_address'],)
                ).fetchone()
                conn.close()

            result = db.upsert_device_by_mac(device_data)
            if existing:
                updated_count += 1
            else:
                new_count += 1

        # Save historical snapshot
        db.save_device_snapshot()

        return {
            'found': len(devices),
            'new_devices': new_count,
            'updated_devices': updated_count,
        }

    try:
        result = await loop.run_in_executor(executor, do_scan)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/scan/status")
async def scan_status():
    """Check if a network scan is in progress."""
    return {"in_progress": is_scan_in_progress()}


@app.get("/api/devices/history")
async def get_device_history(
    range: str = Query('24h', description="Time range: 1h, 6h, 24h, 7d, 30d, 90d, 365d, all"),
    limit: int = Query(500, ge=1, le=10000),
):
    """Get device count history (snapshots over time)."""
    return db.get_device_snapshots(range_filter=range, limit=limit)


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
    """Get all settings."""
    return db.get_settings()


@app.put("/api/settings")
async def update_settings(data: SettingsUpdate):
    """Update settings."""
    settings_data = data.model_dump(exclude_none=True)
    db.update_settings(settings_data)

    # Update scheduler with new settings
    update_schedule()

    return db.get_settings()


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
    result = await loop.run_in_executor(executor, telegram_test_connection, bot_token, chat_id)

    if result['success']:
        return result
    else:
        raise HTTPException(status_code=400, detail=result['message'])


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
