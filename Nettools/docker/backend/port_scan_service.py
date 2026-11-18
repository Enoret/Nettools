"""
NetTools - Port Scan Service
Scans TCP ports of a single host with nmap and parses the XML output.
"""

import ipaddress
import logging
import os
import subprocess
import time
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# name -> (nmap args, subprocess timeout in seconds)
# Timeouts stay below nginx's proxy_read_timeout (180s).
PROFILES = {
    'quick': (['--top-ports', '100', '--host-timeout', '60s'], 75),
    'full': (['--top-ports', '1000', '-sV', '--version-light', '--host-timeout', '150s'], 170),
}


def validate_ip(ip: str) -> str:
    """Return the normalized IP or raise ValueError (never pass raw input to nmap)."""
    try:
        return str(ipaddress.ip_address((ip or '').strip()))
    except ValueError:
        raise ValueError(f"IP no valida: {ip}")


def scan_ports(ip: str, profile: str = 'quick') -> dict:
    """
    Scan TCP ports on `ip`.

    Returns:
        {
          'ip': str,
          'profile': str,
          'host_up': bool,
          'duration': float (seconds),
          'scanned_ports': set[int]  # ports nmap actually probed
          'open_ports': [ {port, protocol, service, product, version}, ... ],
        }
    """
    ip = validate_ip(ip)
    if profile not in PROFILES:
        raise ValueError(f"Perfil de escaneo no valido: {profile}")

    extra_args, timeout = PROFILES[profile]
    # SYN scan needs root (the Docker container runs as root); fall back to connect scan
    scan_type = '-sS' if hasattr(os, 'geteuid') and os.geteuid() == 0 else '-sT'
    cmd = ['nmap', '-Pn', scan_type, '-T4', '--open', *extra_args, '-oX', '-', ip]

    logger.info(f"Port scan ({profile}) on {ip}: {' '.join(cmd)}")
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(f"El escaneo de puertos de {ip} ha expirado (timeout)")
    except FileNotFoundError:
        raise Exception("nmap no esta instalado en el servidor")
    duration = round(time.monotonic() - start, 1)

    if result.returncode != 0 or not result.stdout.strip():
        err = (result.stderr or '').strip().splitlines()
        raise Exception(f"nmap fallo: {err[-1] if err else 'sin salida'}")

    parsed = parse_nmap_xml(result.stdout)
    parsed.update({'ip': ip, 'profile': profile, 'duration': duration})
    logger.info(f"Port scan on {ip} done in {duration}s: {len(parsed['open_ports'])} open ports")
    return parsed


def parse_nmap_xml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)

    scanned = set()
    for info in root.findall('scaninfo'):
        if info.get('protocol') == 'tcp':
            scanned |= _expand_ranges(info.get('services', ''))

    host_up = False
    open_ports = []
    host = root.find('host')
    if host is not None:
        status = host.find('status')
        host_up = status is not None and status.get('state') == 'up'
        for port in host.findall('ports/port'):
            state = port.find('state')
            if state is None or state.get('state') != 'open':
                continue
            svc = port.find('service')
            open_ports.append({
                'port': int(port.get('portid')),
                'protocol': port.get('protocol', 'tcp'),
                'service': (svc.get('name') if svc is not None else '') or '',
                'product': (svc.get('product') if svc is not None else '') or '',
                'version': (svc.get('version') if svc is not None else '') or '',
                'tunnel': (svc.get('tunnel') if svc is not None else '') or '',
            })

    open_ports.sort(key=lambda p: p['port'])
    return {'host_up': host_up, 'scanned_ports': scanned, 'open_ports': open_ports}


def _expand_ranges(spec: str) -> set:
    """'1,3-5,80' -> {1, 3, 4, 5, 80}"""
    ports = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            ports.update(range(int(a), int(b) + 1))
        else:
            ports.add(int(part))
    return ports
