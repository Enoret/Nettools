"""
NetTools - Wake-on-LAN

Sends the magic packet (6 x 0xFF + 16 x MAC) by UDP broadcast to ports 9 and
7, on the global broadcast address and on the broadcast address of every
local network of the server (the container uses host networking).
"""

import ipaddress
import logging
import socket

from oui_service import normalize_mac
from network_service import get_local_networks

logger = logging.getLogger(__name__)


def magic_packet(mac: str) -> bytes:
    norm = normalize_mac(mac)
    if not norm:
        raise ValueError(f"MAC no valida: {mac}")
    return b'\xff' * 6 + bytes.fromhex(norm.replace(':', '')) * 16


def broadcast_addresses(device_ip: str = None) -> list:
    addrs = ['255.255.255.255']
    try:
        for n in get_local_networks():
            addrs.append(str(ipaddress.ip_network(n['cidr'], strict=False).broadcast_address))
    except Exception as e:
        logger.debug(f"WoL: could not read local networks: {e}")
    if device_ip:
        try:
            addrs.append(str(ipaddress.ip_network(f"{device_ip}/24", strict=False).broadcast_address))
        except ValueError:
            pass
    seen, out = set(), []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def wake(mac: str, device_ip: str = None) -> dict:
    packet = magic_packet(mac)
    targets = broadcast_addresses(device_ip)
    sent = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for addr in targets:
            for port in (9, 7):
                try:
                    s.sendto(packet, (addr, port))
                    sent.append(f"{addr}:{port}")
                except OSError as e:
                    logger.debug(f"WoL to {addr}:{port} failed: {e}")
    if not sent:
        raise Exception("No se pudo enviar el paquete Wake-on-LAN")
    logger.info(f"Wake-on-LAN for {normalize_mac(mac)} sent to {', '.join(sent)}")
    return {'mac': normalize_mac(mac), 'sent_to': sent}
