"""
NetTools - "What could this device be?" hints

Builds a short, human readable guess for unknown devices from what NetTools
knows: hostname, open ports, MAC vendor and whether the MAC is private.
Used to pre-fill the description of *new* devices (never over a description
written by the user).
"""

import re

PREFIX = 'Posible: '

# (substring of the lowercase vendor, hint). First match wins: put specific
# names before generic ones.
VENDOR_HINTS = [
    ('hualai', 'camara o sensor Wyze (Tianjin Hualai fabrica los dispositivos Wyze)'),
    ('wyze', 'camara o sensor Wyze'),
    ('ezviz', 'camara EZVIZ (videovigilancia, timbre o mirilla)'),
    ('hikvision', 'camara IP o grabador (NVR/DVR) Hikvision'),
    ('dahua', 'camara IP o grabador Dahua (tambien marca Imou)'),
    ('reolink', 'camara IP Reolink'),
    ('roborock', 'robot aspirador Roborock'),
    ('ecovacs', 'robot aspirador Ecovacs'),
    ('irobot', 'robot aspirador Roomba'),
    ('dreame', 'robot aspirador Dreame'),
    ('tuya', 'enchufe, bombilla, sensor o interruptor inteligente (app Tuya / Smart Life)'),
    ('espressif', 'dispositivo IoT con chip ESP32/ESP8266: enchufe, bombilla, rele (Shelly, Sonoff...), sensor o proyecto DIY'),
    ('shelly', 'rele o enchufe inteligente Shelly'),
    ('itead', 'interruptor o enchufe Sonoff'),
    ('altobeam', 'dispositivo IoT con chip WiFi AltoBeam, muy usado en camaras WiFi economicas'),
    ('wewins', 'modulo WiFi de un dispositivo IoT (habitual en camaras, enchufes o electrodomesticos chinos)'),
    ('hui zhou gaoshengda', 'modulo WiFi de un electrodomestico o TV'),
    ('beken', 'dispositivo IoT con chip Beken (enchufes, bombillas, camaras baratas)'),
    ('realtek', 'tarjeta de red de un PC, TV box o dispositivo IoT con chip Realtek'),
    ('mediatek', 'dispositivo con chip MediaTek (TV, router, movil o IoT)'),
    ('broadcom', 'dispositivo con chip Broadcom (router, TV, PC...)'),
    ('murata', 'modulo WiFi Murata (consolas, altavoces, electrodomesticos...)'),
    ('azurewave', 'tarjeta WiFi AzureWave (portatil, TV o consola)'),
    ('universal global scientific', 'modulo WiFi USI (portatil, TV o consola)'),
    ('hon hai', 'equipo fabricado por Foxconn: PC, consola, TV o router'),
    ('foxconn', 'equipo fabricado por Foxconn: PC, consola, TV o router'),
    ('lite-on', 'tarjeta WiFi Lite-On de un portatil o PC'),
    ('liteon', 'tarjeta WiFi Lite-On de un portatil o PC'),
    ('intel', 'PC o portatil (tarjeta de red Intel)'),
    ('lg innotek', 'modulo WiFi LG Innotek: electrodomestico o TV LG'),
    ('lg electronics', 'TV, barra de sonido o electrodomestico LG (ThinQ)'),
    ('samsung', 'movil, tablet, TV o electrodomestico Samsung'),
    ('sony interactive', 'consola PlayStation'),
    ('sony', 'TV Bravia, consola PlayStation o movil Sony'),
    ('nintendo', 'consola Nintendo (Switch)'),
    ('microsoft', 'Xbox o equipo Surface'),
    ('valve', 'Steam Deck'),
    ('apple', 'dispositivo Apple: iPhone, iPad, Mac, Apple TV, HomePod o Apple Watch'),
    ('google', 'dispositivo Google: Chromecast, Nest (altavoz, termostato, camara) o Pixel'),
    ('amazon', 'dispositivo Amazon: Echo/Alexa, Fire TV, Kindle o Ring'),
    ('ring', 'timbre o camara Ring'),
    ('sonos', 'altavoz Sonos'),
    ('bose', 'altavoz o barra de sonido Bose'),
    ('signify', 'puente o bombilla Philips Hue'),
    ('philips', 'puente Philips Hue, TV o electrodomestico Philips'),
    ('ikea', 'puente o dispositivo IKEA Home smart (Dirigera / Tradfri)'),
    ('netatmo', 'termostato, camara o estacion meteorologica Netatmo'),
    ('tado', 'termostato o puente tado'),
    ('xiaomi', 'dispositivo Xiaomi: movil, camara, robot aspirador, enchufe, sensor o TV box (app Mi Home)'),
    ('roku', 'reproductor Roku'),
    ('nvidia', 'NVIDIA Shield o PC con tarjeta NVIDIA'),
    ('raspberry', 'Raspberry Pi (Home Assistant, Pi-hole, servidor casero...)'),
    ('synology', 'NAS Synology'),
    ('qnap', 'NAS QNAP'),
    ('ugreen', 'NAS o adaptador de red UGREEN'),
    ('western digital', 'disco en red WD My Cloud'),
    ('proxmox', 'maquina virtual o contenedor LXC en Proxmox'),
    ('vmware', 'maquina virtual VMware'),
    ('qemu', 'maquina virtual (QEMU/KVM)'),
    ('red hat', 'maquina virtual (KVM/virtio)'),
    ('ubiquiti', 'equipo UniFi/Ubiquiti: punto de acceso, switch, router o camara'),
    ('tp-link', 'equipo TP-Link: router, punto de acceso, repetidor, enchufe o camara Tapo'),
    ('netgear', 'router, switch o repetidor Netgear'),
    ('mikrotik', 'router o switch MikroTik'),
    ('cisco', 'equipo de red Cisco/Linksys'),
    ('asustek', 'router ASUS o PC/portatil ASUS'),
    ('avm', 'router o repetidor FRITZ!Box'),
    ('sagemcom', 'router del operador (Sagemcom)'),
    ('askey', 'router del operador (Askey)'),
    ('arcadyan', 'router del operador (Arcadyan)'),
    ('zte', 'router del operador o movil ZTE'),
    ('huawei', 'movil, tablet o router Huawei'),
    ('honor', 'movil o tablet Honor'),
    ('oppo', 'movil Oppo'),
    ('oneplus', 'movil OnePlus'),
    ('vivo mobile', 'movil Vivo'),
    ('realme', 'movil Realme'),
    ('motorola', 'movil Motorola'),
    ('hp inc', 'impresora o PC HP'),
    ('hewlett', 'impresora o PC HP'),
    ('brother', 'impresora Brother'),
    ('canon', 'impresora o camara Canon'),
    ('seiko epson', 'impresora Epson'),
    ('epson', 'impresora Epson'),
    ('dell', 'PC, portatil o servidor Dell'),
    ('lenovo', 'PC, portatil o tablet Lenovo'),
    ('giga-byte', 'PC o mini PC con placa Gigabyte'),
    ('micro-star', 'PC o portatil MSI'),
    ('tesla', 'coche o Powerwall Tesla'),
    ('bsh', 'electrodomestico Bosch/Siemens/Balay (Home Connect)'),
    ('miele', 'electrodomestico Miele'),
    ('daikin', 'aire acondicionado Daikin'),
    ('panasonic', 'TV, aire acondicionado o camara Panasonic'),
    ('hisense', 'TV Hisense'),
    ('tcl', 'TV TCL'),
    ('withings', 'bascula o reloj Withings'),
    ('garmin', 'reloj o dispositivo Garmin'),
]

# hostname regex -> hint
HOSTNAME_HINTS = [
    (r'iphone', 'iPhone'),
    (r'ipad', 'iPad'),
    (r'macbook|imac|mac-?mini|mac-?studio', 'Mac'),
    (r'apple-?tv', 'Apple TV'),
    (r'homepod', 'HomePod'),
    (r'watch', 'reloj inteligente'),
    (r'galaxy|sm-[a-z]\d', 'movil o tablet Samsung Galaxy'),
    (r'android|pixel|redmi|poco|oneplus|xiaomi-?\d', 'movil Android'),
    (r'chromecast', 'Chromecast'),
    (r'google-?home|nest', 'altavoz o pantalla Google Nest'),
    (r'echo|alexa|amazon-', 'Amazon Echo / Alexa'),
    (r'fire-?tv|aft', 'Amazon Fire TV'),
    (r'roborock|rockrobo', 'robot aspirador Roborock'),
    (r'shelly', 'rele Shelly'),
    (r'sonoff|tasmota|espurna', 'enchufe o rele con firmware Tasmota/Sonoff'),
    (r'esp[-_]?\w{4,}|esp32|esp8266', 'dispositivo ESP32/ESP8266 (IoT/DIY)'),
    (r'wyze', 'camara Wyze'),
    (r'ezviz', 'camara EZVIZ'),
    (r'hikvision|ds-\d', 'camara Hikvision'),
    (r'sonos', 'altavoz Sonos'),
    (r'playstation|ps[45]', 'PlayStation'),
    (r'xbox', 'Xbox'),
    (r'switch', 'Nintendo Switch o switch de red'),
    (r'^npi|hp[0-9a-f]{6}|officejet|laserjet|deskjet', 'impresora HP'),
    (r'^brn|brother', 'impresora Brother'),
    (r'epson', 'impresora Epson'),
    (r'canon', 'impresora Canon'),
    (r'desktop-|laptop-|win-', 'PC con Windows'),
    (r'raspberrypi|raspberry', 'Raspberry Pi'),
    (r'homeassistant|hassio', 'Home Assistant'),
    (r'tv|bravia|webos|tizen|android-?tv', 'Smart TV'),
]

# port -> (weight, hint). Higher weight wins.
PORT_HINTS = {
    554: (90, 'camara (RTSP, puerto 554)'),
    8554: (85, 'camara (RTSP)'),
    37777: (90, 'camara o grabador Dahua'),
    8000: (30, 'servicio web en el 8000 (camaras Hikvision usan este puerto)'),
    9100: (90, 'impresora (puerto 9100)'),
    631: (80, 'impresora (IPP, puerto 631)'),
    515: (80, 'impresora (LPD, puerto 515)'),
    62078: (95, 'iPhone o iPad (puerto 62078)'),
    7000: (40, 'dispositivo AirPlay (Apple TV, HomePod, altavoz o TV)'),
    8008: (70, 'Chromecast / Google Cast'),
    8009: (80, 'Chromecast / Google Cast'),
    1400: (85, 'altavoz Sonos'),
    8123: (95, 'Home Assistant'),
    1883: (60, 'broker MQTT (domotica)'),
    8006: (95, 'servidor Proxmox VE'),
    5000: (40, 'servicio en el puerto 5000 (receptor AirPlay de un Mac, o NAS Synology)'),
    5001: (60, 'NAS Synology (DSM)'),
    548: (60, 'NAS o Mac con comparticion de archivos (AFP)'),
    32400: (85, 'servidor Plex'),
    8096: (80, 'servidor Jellyfin/Emby'),
    3389: (70, 'PC con Windows (Escritorio remoto)'),
    445: (40, 'PC o NAS con carpetas compartidas (SMB)'),
    53: (50, 'servidor DNS (router, Pi-hole o AdGuard)'),
    22: (20, 'equipo con Linux/SSH'),
    80: (10, 'tiene interfaz web: abre su IP en el navegador'),
    443: (10, 'tiene interfaz web: abre su IP en el navegador'),
}


def _vendor_hint(brand: str) -> str:
    b = (brand or '').lower()
    if not b or b.startswith('('):
        return ''
    for needle, hint in VENDOR_HINTS:
        if re.search(r'(?<![a-z0-9])' + re.escape(needle) + r'(?![a-z0-9])', b):
            return hint
    return ''


def _hostname_hint(hostname: str) -> str:
    h = (hostname or '').lower()
    if not h:
        return ''
    for pattern, hint in HOSTNAME_HINTS:
        if re.search(pattern, h):
            return hint
    return ''


def _ports_hint(ports: list) -> str:
    best = None
    for p in ports or []:
        try:
            port = int(p.get('port') if isinstance(p, dict) else p)
        except (TypeError, ValueError):
            continue
        if port in PORT_HINTS and (best is None or PORT_HINTS[port][0] > best[0]):
            best = PORT_HINTS[port]
    return best[1] if best else ''


def _is_private_mac(mac: str) -> bool:
    try:
        return bool(int((mac or '').replace('-', ':').split(':')[0], 16) & 0x02)
    except ValueError:
        return False


def guess(device: dict, ports: list = None) -> str:
    """Description hint for a device, '' if there is nothing useful to say."""
    parts = []
    host = _hostname_hint(device.get('hostname'))
    vendor = _vendor_hint(device.get('brand'))
    port = _ports_hint(ports)

    if host:
        parts.append(host)
    if vendor and (not host or host.lower() not in vendor.lower()):
        parts.append(vendor)
    if port:
        parts.append(port)

    if not parts and _is_private_mac(device.get('mac_address')):
        parts.append('movil, tablet, portatil o reloj con MAC privada/aleatoria '
                     '(iPhone, Android, Windows o Mac con "direccion privada" activada)')
    if not parts and not device.get('mac_address'):
        return ''
    if not parts:
        return ''
    # Remove repeated hints, keep order
    seen, unique = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return PREFIX + ' · '.join(unique)
