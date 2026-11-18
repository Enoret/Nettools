"""
NetTools - Network Scanning Service

Scans one or more IPv4 ranges:
  - ranges on a subnet the server has an interface in -> arp-scan on that
    interface (MAC + vendor), falling back to nmap -sn (also gets MACs via ARP)
  - other (routed) ranges, e.g. VLANs reachable through the router ->
    nmap -sn ping scan; MAC addresses are not visible across routers, so those
    devices are identified by IP.
"""

import ipaddress
import json
import subprocess
import re
import logging
import platform
from typing import Optional

from oui_service import resolve_vendor, normalize_mac

logger = logging.getLogger(__name__)

# Interfaces that never represent a LAN to scan (Docker/k8s bridges, VPNs...)
EXCLUDED_IFACE_PREFIXES = (
    'lo', 'docker', 'br-', 'veth', 'virbr', 'cni', 'flannel', 'cali', 'vxlan',
    'kube', 'tun', 'tap', 'wg', 'tailscale', 'zt', 'podman',
)
MAX_RANGE_HOSTS = 1024   # /22: keeps a manual scan within the 180s proxy timeout
MAX_EXTRA_RANGES = 8


# ==========================================
#  Ranges
# ==========================================

def get_local_networks() -> list:
    """IPv4 subnets the server is directly attached to (LAN interfaces only).

    Returns [{'interface': 'eth0', 'ip': '192.168.1.10', 'cidr': '192.168.1.0/24'}, ...]
    """
    networks = []
    try:
        out = subprocess.run(['ip', '-j', '-4', 'addr', 'show'],
                             capture_output=True, text=True, timeout=5).stdout
        for iface in json.loads(out or '[]'):
            name = iface.get('ifname', '')
            if not name or name.startswith(EXCLUDED_IFACE_PREFIXES):
                continue
            if 'UP' not in iface.get('flags', []):
                continue
            for addr in iface.get('addr_info', []):
                if addr.get('family') != 'inet' or addr.get('prefixlen', 32) >= 31:
                    continue
                net = ipaddress.ip_network(f"{addr['local']}/{addr['prefixlen']}", strict=False)
                if net.is_loopback or net.is_link_local:
                    continue
                networks.append({'interface': name, 'ip': addr['local'], 'cidr': str(net)})
    except Exception as e:
        logger.warning(f"Could not detect local networks: {e}")
    return networks


def get_default_gateway() -> Optional[str]:
    try:
        out = subprocess.run(['ip', '-j', '-4', 'route', 'show', 'default'],
                             capture_output=True, text=True, timeout=5).stdout
        routes = json.loads(out or '[]')
        return routes[0].get('gateway') if routes else None
    except Exception:
        return None


def parse_cidr(text: str) -> str:
    """Validate and normalize an IPv4 range ('192.168.20.7/24' -> '192.168.20.0/24').
    Raises ValueError with a user-facing message."""
    text = (text or '').strip()
    if not text:
        raise ValueError("Rango vacio")
    if '/' not in text:
        raise ValueError(f"Falta la mascara en '{text}' (ejemplo: 192.168.20.0/24)")
    try:
        net = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ValueError(f"Rango no valido: '{text}' (ejemplo: 192.168.20.0/24)")
    if net.version != 4:
        raise ValueError(f"Solo se admiten rangos IPv4: '{text}'")
    if net.num_addresses > MAX_RANGE_HOSTS:
        raise ValueError(f"El rango {net} es demasiado grande (maximo /22, {MAX_RANGE_HOSTS} direcciones)")
    if net.is_loopback or net.is_multicast:
        raise ValueError(f"Rango no valido para escanear: {net}")
    return str(net)


def parse_range_list(value) -> list:
    """'a, b\nc' or ['a','b'] -> normalized, de-duplicated list. Raises ValueError."""
    items = value if isinstance(value, list) else re.split(r'[,\s]+', value or '')
    result = []
    for item in items:
        if not str(item).strip():
            continue
        cidr = parse_cidr(str(item))
        if cidr not in result:
            result.append(cidr)
    if len(result) > MAX_EXTRA_RANGES:
        raise ValueError(f"Maximo {MAX_EXTRA_RANGES} redes adicionales")
    return result


def describe_range(cidr: str, local_networks: list = None, source: str = 'manual') -> dict:
    """How a range will be scanned: ARP on a local interface, or routed ping scan."""
    local_networks = get_local_networks() if local_networks is None else local_networks
    net = ipaddress.ip_network(cidr)
    iface = None
    for ln in local_networks:
        if net.subnet_of(ipaddress.ip_network(ln['cidr'])) or ipaddress.ip_network(ln['cidr']).subnet_of(net):
            iface = ln['interface']
            break
    return {
        'cidr': cidr,
        'source': source,
        'method': 'arp' if iface else 'routed',
        'interface': iface,
        'hosts': max(net.num_addresses - 2, 1),
    }


def resolve_ranges(settings: dict) -> list:
    """Ranges to scan for the current settings: the server's own subnets (if
    enabled) plus the extra ranges configured by the user."""
    local = get_local_networks()
    ranges = []
    if settings.get('scan_local_networks', True):
        for ln in local:
            if not any(r['cidr'] == ln['cidr'] for r in ranges):
                ranges.append(describe_range(ln['cidr'], local, source='auto'))
    try:
        extra = parse_range_list(settings.get('network_ranges', ''))
    except ValueError as e:
        logger.warning(f"Ignoring invalid network_ranges setting: {e}")
        extra = []
    for cidr in extra:
        if not any(r['cidr'] == cidr for r in ranges):
            ranges.append(describe_range(cidr, local, source='manual'))
    return ranges


# ==========================================
#  Scanning
# ==========================================

def scan_network(ranges: list) -> list:
    """Scan every range (see resolve_ranges) and return the discovered devices,
    de-duplicated by MAC (or by IP for devices without a visible MAC)."""
    found = {}
    for r in ranges:
        try:
            devices = _scan_range(r)
            logger.info(f"{r['cidr']} ({r['method']}{' ' + r['interface'] if r['interface'] else ''}): "
                        f"{len(devices)} devices")
        except Exception as e:
            logger.warning(f"Scan of {r['cidr']} failed: {e}")
            continue
        for d in devices:
            key = d.get('mac_address') or f"ip:{d['ip_address']}"
            found.setdefault(key, d)

    if not ranges:
        logger.warning("No networks to scan (no LAN interface detected and no ranges configured)")
    return list(found.values())


def _scan_range(r: dict) -> list:
    if r['method'] == 'arp':
        try:
            devices = _scan_with_arp(r['cidr'], r['interface'])
            if devices:
                return devices
        except Exception as e:
            logger.warning(f"arp-scan on {r['cidr']} failed: {e}, falling back to nmap")
        return _scan_with_nmap(r['cidr'])
    # Routed network: no ARP across routers, MACs are not visible
    devices = _scan_with_nmap(r['cidr'])
    for d in devices:
        d['mac_address'] = ''
        d['brand'] = ''
        d['device_type'] = infer_device_type(hostname=d.get('hostname', ''))
    return devices


def _scan_with_arp(cidr: str, interface: str) -> list:
    """Scan a directly attached subnet using arp-scan."""
    result = subprocess.run(
        ['arp-scan', f'--interface={interface}', '--retry=2', '--timeout=1000', cidr],
        capture_output=True,
        text=True,
        timeout=90
    )

    devices = []
    for line in result.stdout.split('\n'):
        # Match lines with IP, MAC, and vendor
        match = re.match(r'^(\d+\.\d+\.\d+\.\d+)\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})\s+(.*)$', line.strip())
        if match:
            mac = normalize_mac(match.group(2))
            brand = resolve_vendor(mac, match.group(3))
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
        ['nmap', '-sn', '-T4', network_range, '--max-retries', '1', '--host-timeout', '5s'],
        capture_output=True,
        text=True,
        timeout=170
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
            current['mac_address'] = normalize_mac(mac_match.group(1))
            current['brand'] = resolve_vendor(current['mac_address'], mac_match.group(2) or '')
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
            mac = normalize_mac(match.group(3))
            brand = resolve_vendor(mac)
            devices.append({
                'ip_address': match.group(2),
                'mac_address': mac,
                'hostname': hostname,
                'brand': brand,
                'device_type': infer_device_type(brand=brand, hostname=hostname, mac=mac),
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
