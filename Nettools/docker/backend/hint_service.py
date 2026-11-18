"""
NetTools - "What could this device be?" hints

Builds a short, human readable guess for unknown devices from what NetTools
knows: hostname, open ports, MAC vendor and whether the MAC is private.
Used to pre-fill the description of *new* devices (never over a description
written by the user).
"""

import re

PREFIX = 'Posible: '
PREFIX_EN = 'Possibly: '

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


PRIVATE_ES = ('movil, tablet, portatil o reloj con MAC privada/aleatoria '
              '(iPhone, Android, Windows o Mac con "direccion privada" activada)')
PRIVATE_EN = ('phone, tablet, laptop or watch with a private/random MAC '
              '(iPhone, Android, Windows or Mac with "private address" turned on)')

# English versions of the hints (Spanish is the source text)
EN = {
    'camara o sensor Wyze (Tianjin Hualai fabrica los dispositivos Wyze)': 'Wyze camera or sensor (Tianjin Hualai makes Wyze devices)',
    'camara o sensor Wyze': 'Wyze camera or sensor',
    'camara EZVIZ (videovigilancia, timbre o mirilla)': 'EZVIZ camera (security camera, doorbell or door viewer)',
    'camara IP o grabador (NVR/DVR) Hikvision': 'Hikvision IP camera or recorder (NVR/DVR)',
    'camara IP o grabador Dahua (tambien marca Imou)': 'Dahua IP camera or recorder (also sold as Imou)',
    'camara IP Reolink': 'Reolink IP camera',
    'robot aspirador Roborock': 'Roborock robot vacuum',
    'robot aspirador Ecovacs': 'Ecovacs robot vacuum',
    'robot aspirador Roomba': 'Roomba robot vacuum',
    'robot aspirador Dreame': 'Dreame robot vacuum',
    'enchufe, bombilla, sensor o interruptor inteligente (app Tuya / Smart Life)': 'smart plug, bulb, sensor or switch (Tuya / Smart Life app)',
    'dispositivo IoT con chip ESP32/ESP8266: enchufe, bombilla, rele (Shelly, Sonoff...), sensor o proyecto DIY': 'IoT device with an ESP32/ESP8266 chip: plug, bulb, relay (Shelly, Sonoff...), sensor or DIY project',
    'rele o enchufe inteligente Shelly': 'Shelly smart relay or plug',
    'interruptor o enchufe Sonoff': 'Sonoff switch or plug',
    'dispositivo IoT con chip WiFi AltoBeam, muy usado en camaras WiFi economicas': 'IoT device with an AltoBeam WiFi chip, common in cheap WiFi cameras',
    'modulo WiFi de un dispositivo IoT (habitual en camaras, enchufes o electrodomesticos chinos)': 'WiFi module of an IoT device (common in Chinese cameras, plugs or appliances)',
    'modulo WiFi de un electrodomestico o TV': 'WiFi module of an appliance or TV',
    'dispositivo IoT con chip Beken (enchufes, bombillas, camaras baratas)': 'IoT device with a Beken chip (plugs, bulbs, cheap cameras)',
    'tarjeta de red de un PC, TV box o dispositivo IoT con chip Realtek': 'network card of a PC, TV box or IoT device with a Realtek chip',
    'dispositivo con chip MediaTek (TV, router, movil o IoT)': 'device with a MediaTek chip (TV, router, phone or IoT)',
    'dispositivo con chip Broadcom (router, TV, PC...)': 'device with a Broadcom chip (router, TV, PC...)',
    'modulo WiFi Murata (consolas, altavoces, electrodomesticos...)': 'Murata WiFi module (consoles, speakers, appliances...)',
    'tarjeta WiFi AzureWave (portatil, TV o consola)': 'AzureWave WiFi card (laptop, TV or console)',
    'modulo WiFi USI (portatil, TV o consola)': 'USI WiFi module (laptop, TV or console)',
    'equipo fabricado por Foxconn: PC, consola, TV o router': 'device made by Foxconn: PC, console, TV or router',
    'tarjeta WiFi Lite-On de un portatil o PC': 'Lite-On WiFi card of a laptop or PC',
    'PC o portatil (tarjeta de red Intel)': 'PC or laptop (Intel network card)',
    'modulo WiFi LG Innotek: electrodomestico o TV LG': 'LG Innotek WiFi module: LG appliance or TV',
    'TV, barra de sonido o electrodomestico LG (ThinQ)': 'LG TV, soundbar or appliance (ThinQ)',
    'movil, tablet, TV o electrodomestico Samsung': 'Samsung phone, tablet, TV or appliance',
    'consola PlayStation': 'PlayStation console',
    'TV Bravia, consola PlayStation o movil Sony': 'Sony Bravia TV, PlayStation console or Sony phone',
    'consola Nintendo (Switch)': 'Nintendo console (Switch)',
    'Xbox o equipo Surface': 'Xbox or Surface device',
    'Steam Deck': 'Steam Deck',
    'dispositivo Apple: iPhone, iPad, Mac, Apple TV, HomePod o Apple Watch': 'Apple device: iPhone, iPad, Mac, Apple TV, HomePod or Apple Watch',
    'dispositivo Google: Chromecast, Nest (altavoz, termostato, camara) o Pixel': 'Google device: Chromecast, Nest (speaker, thermostat, camera) or Pixel',
    'dispositivo Amazon: Echo/Alexa, Fire TV, Kindle o Ring': 'Amazon device: Echo/Alexa, Fire TV, Kindle or Ring',
    'timbre o camara Ring': 'Ring doorbell or camera',
    'altavoz Sonos': 'Sonos speaker',
    'altavoz o barra de sonido Bose': 'Bose speaker or soundbar',
    'puente o bombilla Philips Hue': 'Philips Hue bridge or bulb',
    'puente Philips Hue, TV o electrodomestico Philips': 'Philips Hue bridge, Philips TV or appliance',
    'puente o dispositivo IKEA Home smart (Dirigera / Tradfri)': 'IKEA Home smart hub or device (Dirigera / Tradfri)',
    'termostato, camara o estacion meteorologica Netatmo': 'Netatmo thermostat, camera or weather station',
    'termostato o puente tado': 'tado thermostat or bridge',
    'dispositivo Xiaomi: movil, camara, robot aspirador, enchufe, sensor o TV box (app Mi Home)': 'Xiaomi device: phone, camera, robot vacuum, plug, sensor or TV box (Mi Home app)',
    'reproductor Roku': 'Roku player',
    'NVIDIA Shield o PC con tarjeta NVIDIA': 'NVIDIA Shield or PC with an NVIDIA card',
    'Raspberry Pi (Home Assistant, Pi-hole, servidor casero...)': 'Raspberry Pi (Home Assistant, Pi-hole, home server...)',
    'NAS Synology': 'Synology NAS',
    'NAS QNAP': 'QNAP NAS',
    'NAS o adaptador de red UGREEN': 'UGREEN NAS or network adapter',
    'disco en red WD My Cloud': 'WD My Cloud network drive',
    'maquina virtual o contenedor LXC en Proxmox': 'virtual machine or LXC container on Proxmox',
    'maquina virtual VMware': 'VMware virtual machine',
    'maquina virtual (QEMU/KVM)': 'virtual machine (QEMU/KVM)',
    'maquina virtual (KVM/virtio)': 'virtual machine (KVM/virtio)',
    'equipo UniFi/Ubiquiti: punto de acceso, switch, router o camara': 'UniFi/Ubiquiti device: access point, switch, router or camera',
    'equipo TP-Link: router, punto de acceso, repetidor, enchufe o camara Tapo': 'TP-Link device: router, access point, extender, plug or Tapo camera',
    'router, switch o repetidor Netgear': 'Netgear router, switch or extender',
    'router o switch MikroTik': 'MikroTik router or switch',
    'equipo de red Cisco/Linksys': 'Cisco/Linksys network device',
    'router ASUS o PC/portatil ASUS': 'ASUS router or ASUS PC/laptop',
    'router o repetidor FRITZ!Box': 'FRITZ!Box router or repeater',
    'router del operador (Sagemcom)': 'ISP router (Sagemcom)',
    'router del operador (Askey)': 'ISP router (Askey)',
    'router del operador (Arcadyan)': 'ISP router (Arcadyan)',
    'router del operador o movil ZTE': 'ISP router or ZTE phone',
    'movil, tablet o router Huawei': 'Huawei phone, tablet or router',
    'movil o tablet Honor': 'Honor phone or tablet',
    'movil Oppo': 'Oppo phone',
    'movil OnePlus': 'OnePlus phone',
    'movil Vivo': 'Vivo phone',
    'movil Realme': 'Realme phone',
    'movil Motorola': 'Motorola phone',
    'impresora o PC HP': 'HP printer or PC',
    'impresora Brother': 'Brother printer',
    'impresora o camara Canon': 'Canon printer or camera',
    'impresora Epson': 'Epson printer',
    'PC, portatil o servidor Dell': 'Dell PC, laptop or server',
    'PC, portatil o tablet Lenovo': 'Lenovo PC, laptop or tablet',
    'PC o mini PC con placa Gigabyte': 'PC or mini PC with a Gigabyte board',
    'PC o portatil MSI': 'MSI PC or laptop',
    'coche o Powerwall Tesla': 'Tesla car or Powerwall',
    'electrodomestico Bosch/Siemens/Balay (Home Connect)': 'Bosch/Siemens appliance (Home Connect)',
    'electrodomestico Miele': 'Miele appliance',
    'aire acondicionado Daikin': 'Daikin air conditioner',
    'TV, aire acondicionado o camara Panasonic': 'Panasonic TV, air conditioner or camera',
    'TV Hisense': 'Hisense TV',
    'TV TCL': 'TCL TV',
    'bascula o reloj Withings': 'Withings scale or watch',
    'reloj o dispositivo Garmin': 'Garmin watch or device',
    'reloj inteligente': 'smartwatch',
    'movil o tablet Samsung Galaxy': 'Samsung Galaxy phone or tablet',
    'movil Android': 'Android phone',
    'altavoz o pantalla Google Nest': 'Google Nest speaker or display',
    'rele Shelly': 'Shelly relay',
    'enchufe o rele con firmware Tasmota/Sonoff': 'plug or relay with Tasmota/Sonoff firmware',
    'dispositivo ESP32/ESP8266 (IoT/DIY)': 'ESP32/ESP8266 device (IoT/DIY)',
    'camara Wyze': 'Wyze camera',
    'camara EZVIZ': 'EZVIZ camera',
    'camara Hikvision': 'Hikvision camera',
    'Nintendo Switch o switch de red': 'Nintendo Switch or network switch',
    'impresora HP': 'HP printer',
    'impresora Canon': 'Canon printer',
    'PC con Windows': 'Windows PC',
    'camara (RTSP, puerto 554)': 'camera (RTSP, port 554)',
    'camara (RTSP)': 'camera (RTSP)',
    'camara o grabador Dahua': 'Dahua camera or recorder',
    'servicio web en el 8000 (camaras Hikvision usan este puerto)': 'web service on port 8000 (Hikvision cameras use this port)',
    'impresora (puerto 9100)': 'printer (port 9100)',
    'impresora (IPP, puerto 631)': 'printer (IPP, port 631)',
    'impresora (LPD, puerto 515)': 'printer (LPD, port 515)',
    'iPhone o iPad (puerto 62078)': 'iPhone or iPad (port 62078)',
    'dispositivo AirPlay (Apple TV, HomePod, altavoz o TV)': 'AirPlay device (Apple TV, HomePod, speaker or TV)',
    'broker MQTT (domotica)': 'MQTT broker (home automation)',
    'servidor Proxmox VE': 'Proxmox VE server',
    'servicio en el puerto 5000 (receptor AirPlay de un Mac, o NAS Synology)': 'service on port 5000 (AirPlay receiver of a Mac, or Synology NAS)',
    'NAS Synology (DSM)': 'Synology NAS (DSM)',
    'NAS o Mac con comparticion de archivos (AFP)': 'NAS or Mac with file sharing (AFP)',
    'servidor Plex': 'Plex server',
    'servidor Jellyfin/Emby': 'Jellyfin/Emby server',
    'PC con Windows (Escritorio remoto)': 'Windows PC (Remote Desktop)',
    'PC o NAS con carpetas compartidas (SMB)': 'PC or NAS with shared folders (SMB)',
    'servidor DNS (router, Pi-hole o AdGuard)': 'DNS server (router, Pi-hole or AdGuard)',
    'equipo con Linux/SSH': 'Linux/SSH device',
    'tiene interfaz web: abre su IP en el navegador': 'has a web interface: open its IP in the browser',
    PRIVATE_ES: PRIVATE_EN,
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


def guess(device: dict, ports: list = None, lang: str = 'es') -> str:
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
        parts.append(PRIVATE_ES)
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
    if lang == 'en':
        return PREFIX_EN + ' · '.join(EN.get(p, p) for p in unique)
    return PREFIX + ' · '.join(unique)
