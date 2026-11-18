"""
NetTools - Pydantic Models
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# --- Speed Test ---
class SpeedTestResult(BaseModel):
    id: Optional[int] = None
    timestamp: Optional[str] = None
    download_speed: float
    upload_speed: float
    ping: float
    jitter: Optional[float] = None
    server_name: Optional[str] = None
    server_id: Optional[str] = None
    server_location: Optional[str] = None
    isp: Optional[str] = None
    external_ip: Optional[str] = None


class SpeedTestStats(BaseModel):
    best_download: Optional[float] = 0
    best_upload: Optional[float] = 0
    best_ping: Optional[float] = 0
    avg_download: Optional[float] = 0
    avg_upload: Optional[float] = 0
    avg_ping: Optional[float] = 0
    total_tests: int = 0


# --- Device ---
class DeviceCreate(BaseModel):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    custom_name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    location: Optional[str] = None
    device_type: Optional[str] = 'other'
    ip_type: Optional[str] = 'dhcp'
    status: Optional[str] = 'manual'


class DeviceUpdate(BaseModel):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    custom_name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    location: Optional[str] = None
    device_type: Optional[str] = None
    ip_type: Optional[str] = None
    status: Optional[str] = None


class DeviceBulk(BaseModel):
    ids: List[int]
    action: str                      # 'delete' | 'update'
    status: Optional[str] = None     # 'saved' (only 'new' devices change) | 'new'
    device_type: Optional[str] = None
    location: Optional[str] = None


class Device(BaseModel):
    id: int
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    custom_name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    location: Optional[str] = None
    device_type: str = 'other'
    ip_type: str = 'dhcp'
    status: str = 'new'
    is_online: bool = False
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


# --- Ping ---
class PingRequest(BaseModel):
    ip: str


class PingBatchRequest(BaseModel):
    ips: List[str]


class PingResult(BaseModel):
    ip: str
    is_reachable: bool
    latency: Optional[float] = None
    name: Optional[str] = None


# --- Settings ---
class SettingsUpdate(BaseModel):
    auto_speed_test: Optional[bool] = None
    speed_test_frequency: Optional[str] = None
    speed_test_retention: Optional[str] = None
    auto_network_scan: Optional[bool] = None
    network_scan_frequency: Optional[str] = None
    network_range: Optional[str] = None  # legacy
    scan_local_networks: Optional[bool] = None
    network_ranges: Optional[str] = None
    notify_new_devices: Optional[bool] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    timezone: Optional[str] = None
    notify_speed_tests: Optional[bool] = None
    speed_test_alert_threshold: Optional[str] = None
    purge_stale_devices: Optional[bool] = None
    stale_device_days: Optional[str] = None
    auto_port_scan: Optional[bool] = None
    port_scan_hour: Optional[str] = None
    port_scan_profile: Optional[str] = None
    port_scan_scope: Optional[str] = None
    notify_new_ports: Optional[bool] = None
    view_netalert: Optional[str] = None    # JSON: {columns: [...], sort: {field, dir}}
    view_inventory: Optional[str] = None
    unifi_enabled: Optional[bool] = None
    unifi_url: Optional[str] = None
    unifi_auth: Optional[str] = None
    unifi_api_key: Optional[str] = None
    unifi_username: Optional[str] = None
    unifi_password: Optional[str] = None
    unifi_site: Optional[str] = None
    unifi_verify_ssl: Optional[bool] = None


# --- Inventory ---
class InventoryItem(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    brand: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    warranty_until: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    asset_status: Optional[str] = None
    asset_kind: Optional[str] = None
    host: Optional[str] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None


# --- Scan ---
class ScanResult(BaseModel):
    found: int
    new_devices: int
    updated_devices: int
