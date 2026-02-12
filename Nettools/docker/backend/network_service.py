"""
NetTools - Network Scanning Service
"""

import subprocess
import re
import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)


def scan_network(network_range: str = '192.168.1.0/24') -> list:
    """
    Scan the local network for devices using arp-scan or nmap.
    Returns list of discovered devices.
    """
    devices = []

    # Try arp-scan first (faster, more reliable for local network)
    try:
        devices = _scan_with_arp(network_range)
        if devices:
            logger.info(f"arp-scan found {len(devices)} devices")
            return devices
    except Exception as e:
        logger.warning(f"arp-scan failed: {e}")

    # Fallback to nmap
    try:
        devices = _scan_with_nmap(network_range)
        logger.info(f"nmap found {len(devices)} devices")
        return devices
    except Exception as e:
        logger.warning(f"nmap failed: {e}")

    # Fallback to arp table
    try:
        devices = _scan_arp_table()
        logger.info(f"ARP table has {len(devices)} entries")
        return devices
    except Exception as e:
        logger.warning(f"ARP table scan failed: {e}")

    return devices


def _scan_with_arp(network_range: str) -> list:
    """Scan using arp-scan."""
    result = subprocess.run(
        ['arp-scan', '--localnet', '--retry=2', '--timeout=1000', f'--interface=eth0'],
        capture_output=True,
        text=True,
        timeout=60
    )

    devices = []
    for line in result.stdout.split('\n'):
        # Match lines with IP, MAC, and vendor
        match = re.match(r'^(\d+\.\d+\.\d+\.\d+)\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})\s+(.*)$', line.strip())
        if match:
            brand = match.group(3).strip() if match.group(3).strip() != '(Unknown)' else ''
            mac = match.group(2).upper()
            devices.append({
                'ip_address': match.group(1),
                'mac_address': mac,
                'hostname': '',
                'brand': brand,
                'device_type': infer_device_type(brand=brand, mac=mac),
            })

    return devices


def _scan_with_nmap(network_range: str) -> list:
    """Scan using nmap."""
    result = subprocess.run(
        ['nmap', '-sn', '-PR', network_range, '--max-retries', '1', '--host-timeout', '5s'],
        capture_output=True,
        text=True,
        timeout=120
    )

    devices = []
    current = {}

    for line in result.stdout.split('\n'):
        # Match host line
        host_match = re.search(r'Nmap scan report for (?:(\S+) \()?(\d+\.\d+\.\d+\.\d+)\)?', line)
        if host_match:
            if current.get('ip_address'):
                devices.append(current)
            hostname = host_match.group(1) or ''
            current = {
                'ip_address': host_match.group(2),
                'mac_address': '',
                'hostname': hostname,
                'brand': '',
                'device_type': 'other',
            }

        # Match MAC line
        mac_match = re.search(r'MAC Address: ((?:[0-9A-F]{2}:){5}[0-9A-F]{2})\s*\(?(.*?)\)?$', line)
        if mac_match and current:
            current['mac_address'] = mac_match.group(1)
            current['brand'] = mac_match.group(2).strip() if mac_match.group(2) else ''
            current['device_type'] = infer_device_type(
                brand=current['brand'],
                hostname=current.get('hostname', ''),
                mac=current['mac_address']
            )

    if current.get('ip_address'):
        devices.append(current)

    return devices


def _scan_arp_table() -> list:
    """Read the system ARP table as a fallback."""
    result = subprocess.run(
        ['arp', '-a'],
        capture_output=True,
        text=True,
        timeout=10
    )

    devices = []
    for line in result.stdout.split('\n'):
        # Linux format: hostname (IP) at MAC [ether] on interface
        match = re.search(r'(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})', line)
        if match:
            hostname = match.group(1) if match.group(1) != '?' else ''
            mac = match.group(3).upper()
            devices.append({
                'ip_address': match.group(2),
                'mac_address': mac,
                'hostname': hostname,
                'brand': '',
                'device_type': infer_device_type(hostname=hostname, mac=mac),
            })

    return devices


def infer_device_type(brand: str = '', hostname: str = '', mac: str = '') -> str:
    """
    Infer the device type from brand/vendor name, hostname, and MAC prefix.
    Returns one of: router, switch, ap, printer, phone, tablet, tv, camera,
    iot, server, desktop, laptop, nas, gaming, other
    """
    brand_lower = (brand or '').lower()
    hostname_lower = (hostname or '').lower()
    combined = f"{brand_lower} {hostname_lower}"

    # Router / Gateway
    router_keywords = ['router', 'gateway', 'mikrotik', 'ubiquiti', 'netgear',
                       'tp-link', 'tplink', 'asus', 'linksys', 'dlink', 'd-link',
                       'cisco', 'zyxel', 'huawei', 'openwrt', 'pfsense', 'fritz']
    if any(k in combined for k in router_keywords):
        # Distinguish APs and switches from routers
        if any(k in combined for k in ['unifi', 'ap', 'access point', 'uap']):
            return 'ap'
        if any(k in combined for k in ['switch', 'gs3', 'gs1']):
            return 'switch'
        return 'router'

    # Access Points
    if any(k in combined for k in ['access point', 'unifi', 'aruba', 'ruckus', 'meraki']):
        return 'ap'

    # Switches
    if any(k in combined for k in ['switch', 'netgear gs', 'prosafe']):
        return 'switch'

    # Printers
    if any(k in combined for k in ['printer', 'print', 'epson', 'canon', 'brother',
                                    'hp inc', 'hewlett', 'lexmark', 'xerox', 'kyocera',
                                    'ricoh', 'sharp', 'konica']):
        return 'printer'

    # Phones (mobile)
    if any(k in combined for k in ['iphone', 'samsung galaxy', 'xiaomi', 'huawei',
                                    'oneplus', 'pixel', 'android', 'oppo', 'vivo',
                                    'realme', 'motorola', 'phone']):
        return 'phone'

    # Tablets
    if any(k in combined for k in ['ipad', 'tablet', 'galaxy tab', 'fire hd',
                                    'surface']):
        return 'tablet'

    # Smart TVs / Streaming
    if any(k in combined for k in ['samsung elec', 'lg elec', 'sony', 'roku',
                                    'fire tv', 'chromecast', 'apple tv', 'nvidia shield',
                                    'tv', 'vizio', 'hisense', 'tcl']):
        return 'tv'

    # Cameras / Security
    if any(k in combined for k in ['camera', 'cam', 'hikvision', 'dahua', 'reolink',
                                    'ring', 'nest', 'arlo', 'wyze', 'ezviz', 'axis']):
        return 'camera'

    # IoT / Smart Home
    if any(k in combined for k in ['espressif', 'esp32', 'esp8266', 'tuya', 'sonoff',
                                    'shelly', 'tasmota', 'zigbee', 'alexa', 'echo',
                                    'google home', 'homepod', 'smartthings', 'hue',
                                    'nest', 'ring', 'iot']):
        return 'iot'

    # NAS / Storage
    if any(k in combined for k in ['synology', 'qnap', 'nas', 'drobo', 'buffalo',
                                    'western digital', 'wd my']):
        return 'nas'

    # Gaming
    if any(k in combined for k in ['playstation', 'xbox', 'nintendo', 'steam deck',
                                    'gaming']):
        return 'gaming'

    # Servers
    if any(k in combined for k in ['server', 'proxmox', 'vmware', 'dell emc',
                                    'supermicro', 'lenovo server']):
        return 'server'

    # Desktops / Laptops
    if any(k in combined for k in ['intel', 'amd', 'dell', 'lenovo', 'hp ',
                                    'acer', 'msi']):
        return 'desktop'

    # Apple devices (when we can't distinguish type)
    if any(k in combined for k in ['apple', 'macbook', 'imac', 'mac mini']):
        return 'desktop'

    # Raspberry Pi / SBCs
    if any(k in combined for k in ['raspberry', 'raspberrypi']):
        return 'server'

    return 'other'


def ping_host(ip: str, timeout: int = 3) -> dict:
    """
    Ping a single host and return result.
    """
    try:
        # Use system ping for reliability
        param = '-c' if platform.system().lower() != 'windows' else '-n'
        result = subprocess.run(
            ['ping', param, '1', '-W', str(timeout), ip],
            capture_output=True,
            text=True,
            timeout=timeout + 2
        )

        if result.returncode == 0:
            # Parse latency from output
            latency = _parse_ping_latency(result.stdout)
            return {
                'ip': ip,
                'is_reachable': True,
                'latency': latency,
            }
        else:
            return {
                'ip': ip,
                'is_reachable': False,
                'latency': None,
            }
    except subprocess.TimeoutExpired:
        return {
            'ip': ip,
            'is_reachable': False,
            'latency': None,
        }
    except Exception as e:
        logger.error(f"Ping error for {ip}: {e}")
        return {
            'ip': ip,
            'is_reachable': False,
            'latency': None,
        }


def _parse_ping_latency(output: str) -> Optional[float]:
    """Parse latency from ping output."""
    # Linux: rtt min/avg/max/mdev = 1.234/5.678/9.012/1.234 ms
    match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
    if match:
        return round(float(match.group(1)), 2)

    # Alternative: time=XX.X ms
    match = re.search(r'time[=<]([\d.]+)\s*ms', output)
    if match:
        return round(float(match.group(1)), 2)

    return None
