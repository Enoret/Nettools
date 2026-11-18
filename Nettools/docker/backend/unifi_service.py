"""
NetTools - UniFi Network integration

Reads the client list from a UniFi console/controller. The router sees every
client of every VLAN with its MAC, IP, name and network, which a scan from
NetTools cannot see across routed VLANs.

Supported authentication:
  * API key (UniFi OS consoles: UDM, UCG, UDR, Cloud Key Gen2+ with
    UniFi Network 9.x+). Created in UniFi: Settings > Control Plane >
    Integrations. Tries the classic API first (richer data: network/VLAN,
    DHCP hostname) and falls back to the official Integration API.
  * Local username/password (UniFi OS consoles and legacy controllers).
"""

import logging
import time
from urllib.parse import urlparse

import requests
import urllib3

from oui_service import normalize_mac

logger = logging.getLogger(__name__)

TIMEOUT = 10


class UnifiError(Exception):
    pass


def _base_url(url: str) -> str:
    url = (url or '').strip().rstrip('/')
    if not url:
        raise UnifiError("Falta la direccion de la consola UniFi")
    if '://' not in url:
        url = 'https://' + url
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname:
        raise UnifiError(f"Direccion UniFi no valida: {url}")
    return f"{p.scheme}://{p.netloc}"


class UnifiClient:
    def __init__(self, url, api_key='', username='', password='', site='default', verify_ssl=False):
        self.base = _base_url(url)
        self.api_key = (api_key or '').strip()
        self.username = (username or '').strip()
        self.password = password or ''
        self.site = (site or 'default').strip() or 'default'
        self.verify = bool(verify_ssl)
        if not self.api_key and not (self.username and self.password):
            raise UnifiError("Configura una API key o un usuario y contrasena de UniFi")
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.s = requests.Session()
        self.s.verify = self.verify
        self.s.headers['Accept'] = 'application/json'
        self.prefix = '/proxy/network'  # UniFi OS; '' for legacy controllers
        self.method = None

    # ---------- HTTP ----------
    def _get(self, path, **kw):
        try:
            return self.s.get(self.base + path, timeout=TIMEOUT, **kw)
        except requests.exceptions.SSLError:
            raise UnifiError("Error de certificado SSL (desactiva 'Verificar certificado' si es autofirmado)")
        except requests.exceptions.ConnectionError:
            raise UnifiError(f"No se puede conectar con {self.base}")
        except requests.exceptions.Timeout:
            raise UnifiError(f"Tiempo de espera agotado conectando con {self.base}")

    def _post(self, path, **kw):
        try:
            return self.s.post(self.base + path, timeout=TIMEOUT, **kw)
        except requests.exceptions.SSLError:
            raise UnifiError("Error de certificado SSL (desactiva 'Verificar certificado' si es autofirmado)")
        except requests.exceptions.ConnectionError:
            raise UnifiError(f"No se puede conectar con {self.base}")
        except requests.exceptions.Timeout:
            raise UnifiError(f"Tiempo de espera agotado conectando con {self.base}")

    @staticmethod
    def _json_data(resp):
        try:
            body = resp.json()
        except ValueError:
            return None
        if isinstance(body, dict) and isinstance(body.get('data'), list):
            return body['data']
        return None

    # ---------- Auth ----------
    def _login(self):
        creds = {'username': self.username, 'password': self.password}
        # UniFi OS console
        r = self._post('/api/auth/login', json={**creds, 'remember': False})
        if r.status_code == 200:
            token = r.headers.get('X-CSRF-Token') or r.headers.get('x-csrf-token')
            if token:
                self.s.headers['X-CSRF-Token'] = token
            self.prefix = '/proxy/network'
            return
        if r.status_code in (401, 403):
            raise UnifiError("Usuario o contrasena de UniFi incorrectos (usa una cuenta local, sin 2FA)")
        if r.status_code == 429:
            raise UnifiError("Demasiados intentos de login en UniFi, espera unos minutos")
        # Legacy controller (Cloud Key Gen1 / self-hosted, port 8443)
        r = self._post('/api/login', json=creds)
        if r.status_code == 200:
            self.prefix = ''
            return
        if r.status_code in (400, 401, 403):
            raise UnifiError("Usuario o contrasena de UniFi incorrectos")
        raise UnifiError(f"Login UniFi fallido (HTTP {r.status_code})")

    # ---------- Data ----------
    def get_clients(self) -> list:
        """Connected clients, normalized (see _normalize_classic)."""
        if self.api_key:
            self.s.headers['X-API-KEY'] = self.api_key
            data = self._classic('stat/sta')
            if data is not None:
                self.method = 'api-key'
                return self._with_networks([_normalize_classic(c) for c in data])
            data = self._integration_clients()
            self.method = 'integration-api'
            return data

        self._login()
        data = self._classic('stat/sta')
        if data is None:
            raise UnifiError(f"La consola no devolvio clientes para el sitio '{self.site}'")
        self.method = 'login'
        return self._with_networks([_normalize_classic(c) for c in data])

    def _classic(self, endpoint):
        r = self._get(f"{self.prefix}/api/s/{self.site}/{endpoint}")
        if r.status_code == 200:
            return self._json_data(r)
        if r.status_code in (401, 403) and not self.api_key:
            raise UnifiError("Sin permiso para leer los clientes de UniFi")
        if r.status_code == 400 and 'NoSiteContext' in r.text:
            raise UnifiError(f"El sitio '{self.site}' no existe en UniFi")
        return None

    def _with_networks(self, clients: list) -> list:
        """Fill network name / VLAN from the network list when missing."""
        if all(c['network'] for c in clients):
            return clients
        try:
            nets = self._classic('rest/networkconf') or []
        except UnifiError:
            nets = []
        by_id = {n.get('_id'): n for n in nets}
        for c in clients:
            n = by_id.get(c.pop('_network_id', None))
            if n and not c['network']:
                c['network'] = n.get('name') or ''
            if n and not c['vlan'] and n.get('vlan'):
                c['vlan'] = str(n.get('vlan'))
        for c in clients:
            c.pop('_network_id', None)
        return clients

    def _integration_clients(self) -> list:
        api = '/proxy/network/integration/v1'
        r = self._get(f"{api}/sites", params={'limit': 200})
        if r.status_code in (401, 403):
            raise UnifiError("API key de UniFi no valida")
        if r.status_code != 200:
            raise UnifiError(f"La consola no admite la API de UniFi (HTTP {r.status_code}). "
                             "Necesitas UniFi Network 9.0 o superior, o usa usuario y contrasena.")
        sites = self._json_data(r) or []
        site = next((s for s in sites if s.get('internalReference') == self.site
                     or (s.get('name') or '').lower() == self.site.lower()), None)
        if site is None:
            if len(sites) == 1 or (sites and self.site == 'default'):
                site = sites[0]
            else:
                raise UnifiError(f"El sitio '{self.site}' no existe en UniFi")

        clients, offset = [], 0
        while True:
            r = self._get(f"{api}/sites/{site['id']}/clients", params={'offset': offset, 'limit': 200})
            if r.status_code != 200:
                raise UnifiError(f"Error leyendo clientes de UniFi (HTTP {r.status_code})")
            body = r.json()
            page = body.get('data') or []
            for c in page:
                mac = normalize_mac(c.get('macAddress') or '')
                if not mac:
                    continue
                clients.append({
                    'mac_address': mac,
                    'ip_address': c.get('ipAddress') or '',
                    'name': (c.get('name') or '').strip(),
                    'hostname': '',
                    'network': '',
                    'vlan': '',
                    'is_wired': (c.get('type') or '').upper() == 'WIRED',
                })
            offset += len(page)
            if not page or offset >= int(body.get('totalCount') or 0):
                break
        return clients


def _normalize_classic(c: dict) -> dict:
    ip = c.get('ip') or ''
    if not ip and c.get('use_fixedip'):
        ip = c.get('fixed_ip') or ''
    return {
        'mac_address': normalize_mac(c.get('mac') or ''),
        'ip_address': ip,
        'name': (c.get('name') or '').strip(),          # alias set in UniFi
        'hostname': (c.get('hostname') or '').strip(),  # DHCP hostname
        'network': c.get('network') or c.get('last_connection_network_name') or '',
        'vlan': str(c.get('vlan')) if c.get('vlan') not in (None, '', 0) else '',
        'is_wired': bool(c.get('is_wired')),
        '_network_id': c.get('network_id'),
    }


def client_from_settings(settings: dict) -> UnifiClient:
    use_key = (settings.get('unifi_auth') or 'api_key') == 'api_key'
    return UnifiClient(
        settings.get('unifi_url', ''),
        api_key=settings.get('unifi_api_key', '') if use_key else '',
        username='' if use_key else settings.get('unifi_username', ''),
        password='' if use_key else settings.get('unifi_password', ''),
        site=settings.get('unifi_site', 'default'),
        verify_ssl=bool(settings.get('unifi_verify_ssl', False)),
    )


def fetch_clients(settings: dict) -> list:
    """Connected clients with a valid MAC (raises UnifiError)."""
    client = client_from_settings(settings)
    return [c for c in client.get_clients() if c['mac_address']]


def test_connection(settings: dict) -> dict:
    start = time.monotonic()
    client = client_from_settings(settings)
    clients = [c for c in client.get_clients() if c['mac_address']]
    networks = {}
    for c in clients:
        key = c['network'] or ('Cable' if c['is_wired'] else 'WiFi')
        networks[key] = networks.get(key, 0) + 1
    return {
        'success': True,
        'method': client.method,
        'clients': len(clients),
        'with_ip': sum(1 for c in clients if c['ip_address']),
        'networks': networks,
        'duration': round(time.monotonic() - start, 1),
        'message': f"Conectado ({client.method}): {len(clients)} clientes conectados",
    }


def merge_clients(devices: list, clients: list, resolve_vendor, infer_device_type) -> dict:
    """Merge UniFi clients into the scanned device list (in place).

    - Scanned device with the same MAC: gets the UniFi name and network.
    - Scanned device without MAC (routed VLAN) with the same IP: gets the MAC.
    - Client not found by the scan: added (UniFi says it is connected).
    Returns counters.
    """
    by_mac = {d['mac_address']: d for d in devices if d.get('mac_address')}
    by_ip = {d['ip_address']: d for d in devices if not d.get('mac_address') and d.get('ip_address')}
    stats = {'enriched': 0, 'identified': 0, 'added': 0}

    for c in clients:
        mac = c['mac_address']
        name = c['name'] or c['hostname']
        d = by_mac.get(mac)
        if d is None and c['ip_address'] and c['ip_address'] in by_ip:
            d = by_ip.pop(c['ip_address'])
            d['mac_address'] = mac
            d['brand'] = resolve_vendor(mac)
            by_mac[mac] = d
            stats['identified'] += 1
        elif d is not None:
            stats['enriched'] += 1
        if d is None:
            if not c['ip_address']:
                continue
            brand = resolve_vendor(mac)
            d = {
                'ip_address': c['ip_address'],
                'mac_address': mac,
                'hostname': '',
                'brand': brand,
                'device_type': 'other',
            }
            devices.append(d)
            by_mac[mac] = d
            stats['added'] += 1
        if name:
            d['hostname'] = name
        if not d.get('ip_address') and c['ip_address']:
            d['ip_address'] = c['ip_address']
        d['network_name'] = c['network'] + (f" (VLAN {c['vlan']})" if c['vlan'] else '') if c['network'] else ''
        if not d.get('device_type') or d['device_type'] == 'other':
            d['device_type'] = infer_device_type(brand=d.get('brand', ''), hostname=d.get('hostname', ''), mac=mac)
    return stats
