"""
NetTools - Telegram Notification Service
"""

import html
import json
import logging

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None
    logger.warning("requests library not installed — Telegram notifications disabled")

TELEGRAM_API = "https://api.telegram.org"


def send_telegram_message(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> dict:
    """Send a message via Telegram Bot API.

    Returns dict with 'success' bool and optional 'error' string.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured (missing bot_token or chat_id)")
        return {"success": False, "error": "Bot Token o Chat ID no configurado"}

    if requests is None:
        logger.error("Cannot send Telegram message: requests library not installed")
        return {"success": False, "error": "Libreria 'requests' no instalada en el servidor"}

    url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Telegram message sent successfully")
            return {"success": True}
        else:
            # Parse Telegram API error
            try:
                error_data = resp.json()
                description = error_data.get('description', f'HTTP {resp.status_code}')
            except Exception:
                description = f"HTTP {resp.status_code}"
            logger.error(f"Telegram API error {resp.status_code}: {description}")
            return {"success": False, "error": description}
    except requests.exceptions.Timeout:
        logger.error("Telegram API timeout")
        return {"success": False, "error": "Timeout: no se pudo conectar con la API de Telegram"}
    except requests.exceptions.ConnectionError:
        logger.error("Telegram API connection error")
        return {"success": False, "error": "Error de conexion: verifica que el servidor tenga acceso a Internet"}
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return {"success": False, "error": str(e)}


# ---------- Texts (es / en) ----------
TEXTS = {
    'es': {
        'new_one': 'Nuevo dispositivo detectado',
        'new_many': '{n} nuevos dispositivos detectados',
        'unknown': 'Desconocido',
        'no_mac': 'sin MAC (red enrutada)',
        'brand': 'Marca',
        'type': 'Tipo',
        'ports_title': 'NetTools - Cambios en puertos abiertos',
        'opened': 'Abiertos',
        'closed': 'Cerrados',
        'vs_avg': 'vs media 7d',
        'slow_title': 'NetTools - Velocidad por debajo de lo esperado',
        'test_title': 'NetTools - Test de velocidad',
        'download': 'Descarga',
        'upload': 'Subida',
        'loss': 'Perdida de paquetes',
        'server': 'Servidor',
        'threshold': 'Umbral configurado',
        'see_result': 'Ver resultado en Speedtest',
        'failed_title': 'NetTools - Test de velocidad fallido',
        'failed_body': 'El test programado no se ha podido completar:',
        'ok_title': 'NetTools - Conexion exitosa',
        'ok_body': ('Las notificaciones de Telegram estan configuradas correctamente.\n'
                    'Recibiras alertas cuando se detecten nuevos dispositivos en tu red.'),
        'no_token': 'Bot Token no configurado',
        'no_chat': 'Chat ID no configurado',
        'sent': 'Mensaje de prueba enviado correctamente',
        'tg_error': 'Error de Telegram: {error}',
        'unknown_error': 'Error desconocido',
        'outage_internet': 'NetTools - Internet ha vuelto',
        'outage_gateway': 'NetTools - El router vuelve a responder',
        'outage_body_internet': 'Ha habido un corte de Internet',
        'outage_body_gateway': 'El router (o la red local) no respondia',
        'from_to': 'Desde {start} hasta {end}',
        'duration': 'Duracion',
    },
    'en': {
        'new_one': 'New device detected',
        'new_many': '{n} new devices detected',
        'unknown': 'Unknown',
        'no_mac': 'no MAC (routed network)',
        'brand': 'Brand',
        'type': 'Type',
        'ports_title': 'NetTools - Open port changes',
        'opened': 'Opened',
        'closed': 'Closed',
        'vs_avg': 'vs 7-day average',
        'slow_title': 'NetTools - Speed below expectations',
        'test_title': 'NetTools - Speed test',
        'download': 'Download',
        'upload': 'Upload',
        'loss': 'Packet loss',
        'server': 'Server',
        'threshold': 'Configured threshold',
        'see_result': 'See the result on Speedtest',
        'failed_title': 'NetTools - Speed test failed',
        'failed_body': 'The scheduled test could not be completed:',
        'ok_title': 'NetTools - Connection successful',
        'ok_body': ('Telegram notifications are configured correctly.\n'
                    'You will get alerts when new devices are detected on your network.'),
        'no_token': 'Bot token not set',
        'no_chat': 'Chat ID not set',
        'sent': 'Test message sent',
        'tg_error': 'Telegram error: {error}',
        'unknown_error': 'Unknown error',
        'outage_internet': 'NetTools - Internet is back',
        'outage_gateway': 'NetTools - The router is responding again',
        'outage_body_internet': 'There was an Internet outage',
        'outage_body_gateway': 'The router (or the local network) was not responding',
        'from_to': 'From {start} to {end}',
        'duration': 'Duration',
    },
}

TYPE_NAMES = {
    'es': {'router': 'Router', 'switch': 'Switch', 'ap': 'Punto de acceso', 'server': 'Servidor',
           'desktop': 'PC', 'laptop': 'Portatil', 'phone': 'Telefono', 'tablet': 'Tablet',
           'printer': 'Impresora', 'camera': 'Camara', 'iot': 'IoT', 'nas': 'NAS', 'tv': 'Smart TV',
           'gaming': 'Consola'},
    'en': {'router': 'Router', 'switch': 'Switch', 'ap': 'Access point', 'server': 'Server',
           'desktop': 'PC', 'laptop': 'Laptop', 'phone': 'Phone', 'tablet': 'Tablet',
           'printer': 'Printer', 'camera': 'Camera', 'iot': 'IoT', 'nas': 'NAS', 'tv': 'Smart TV',
           'gaming': 'Console'},
}


def _t(lang: str, key: str, **kw) -> str:
    text = TEXTS.get(lang, TEXTS['es']).get(key) or TEXTS['es'][key]
    return text.format(**kw) if kw else text


def send_new_device_alert(bot_token: str, chat_id: str, devices: list, lang: str = 'es') -> bool:
    """Send an alert about newly discovered devices.

    `devices` is a list of dicts with keys: ip_address, mac_address, hostname, brand, device_type
    """
    if not devices:
        return True

    count = len(devices)
    title = _t(lang, 'new_one') if count == 1 else _t(lang, 'new_many', n=count)
    header = f"🔔 <b>NetTools - {title}</b>\n"

    lines = []
    for d in devices:
        name = html.escape(d.get('hostname') or d.get('ip_address') or _t(lang, 'unknown'))
        ip = html.escape(d.get('ip_address') or '-')
        mac = html.escape(d.get('mac_address') or _t(lang, 'no_mac'))
        brand = html.escape(d.get('brand') or '')
        dtype = d.get('device_type', 'other')

        line = f"\n📡 <b>{name}</b>"
        line += f"\n   IP: <code>{ip}</code>"
        line += f"\n   MAC: <code>{mac}</code>"
        if brand:
            line += f"\n   {_t(lang, 'brand')}: {brand}"
        if dtype and dtype != 'other':
            line += f"\n   {_t(lang, 'type')}: {TYPE_NAMES.get(lang, TYPE_NAMES['es']).get(dtype, dtype)}"
        lines.append(line)

    message = header + "\n".join(lines)

    result = send_telegram_message(bot_token, chat_id, message)
    return result.get("success", False)


def send_port_changes_alert(bot_token: str, chat_id: str, changes: list, lang: str = 'es') -> bool:
    """Ports opened/closed since the previous scan, per device.
    `changes`: [{name, ip, new_ports: [{port, service}], closed_ports: [...]}]"""
    if not changes:
        return True

    def fmt(p):
        svc = p.get('service') or ''
        return f"{p['port']}" + (f" ({html.escape(svc)})" if svc else '')

    lines = [f"🚪 <b>{_t(lang, 'ports_title')}</b>"]
    for c in changes:
        lines.append(f"\n📡 <b>{html.escape(c['name'] or '')}</b> <code>{html.escape(c['ip'] or '')}</code>")
        if c['new_ports']:
            lines.append(f"   🆕 {_t(lang, 'opened')}: " + ", ".join(fmt(p) for p in c['new_ports']))
        if c['closed_ports']:
            lines.append(f"   ✖️ {_t(lang, 'closed')}: " + ", ".join(fmt(p) for p in c['closed_ports']))
    result = send_telegram_message(bot_token, chat_id, "\n".join(lines))
    return result.get("success", False)


def _fmt_delta(value, avg, lang: str = 'es') -> str:
    """' (+3% vs media 7d)' or '' when there is no average."""
    if value is None or not avg:
        return ''
    pct = (value - avg) / avg * 100
    return f" <i>({pct:+.0f}% {_t(lang, 'vs_avg')})</i>"


def send_speed_test_result(bot_token: str, chat_id: str, result: dict,
                           averages: dict = None, threshold: float = 0, lang: str = 'es') -> bool:
    """Send the result of a scheduled speed test."""
    averages = averages or {}
    dl = result.get('download_speed') or 0
    ul = result.get('upload_speed') or 0
    slow = threshold and (dl < threshold or ul < threshold)

    title = f"⚠️ <b>{_t(lang, 'slow_title')}</b>" if slow else f"📶 <b>{_t(lang, 'test_title')}</b>"
    lines = [
        title,
        "",
        f"⬇️ {_t(lang, 'download')}: <b>{dl:.1f} Mbps</b>{_fmt_delta(dl, averages.get('download'), lang)}",
        f"⬆️ {_t(lang, 'upload')}: <b>{ul:.1f} Mbps</b>{_fmt_delta(ul, averages.get('upload'), lang)}",
        f"⏱ Ping: {result.get('ping') or 0:.1f} ms · Jitter: {result.get('jitter') or 0:.1f} ms",
    ]

    raw = result.get('raw_data')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    raw = raw or {}
    loss = raw.get('packetLoss')
    if loss:
        lines.append(f"📉 {_t(lang, 'loss')}: {loss:.1f}%")

    server = result.get('server_location') or result.get('server_name')
    if server:
        lines.append(f"🌐 {_t(lang, 'server')}: {html.escape(str(server))}")
    if result.get('isp'):
        lines.append(f"🏢 ISP: {html.escape(str(result['isp']))}")
    if slow:
        lines.append(f"\n{_t(lang, 'threshold')}: {threshold:.0f} Mbps")

    url = (raw.get('result') or {}).get('url')
    if url:
        lines.append(f'\n<a href="{html.escape(url)}">{_t(lang, "see_result")}</a>')

    return send_telegram_message(bot_token, chat_id, "\n".join(lines)).get('success', False)


def send_speed_test_failure(bot_token: str, chat_id: str, error: str, lang: str = 'es') -> bool:
    message = (
        f"❌ <b>{_t(lang, 'failed_title')}</b>\n\n"
        f"{_t(lang, 'failed_body')}\n<code>{html.escape(str(error))[:500]}</code>"
    )
    return send_telegram_message(bot_token, chat_id, message).get('success', False)


def fmt_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s" if m < 10 and s else f"{m} min"
    return f"{s} s"


def send_outage_resolved(bot_token: str, chat_id: str, event: dict, lang: str = 'es') -> bool:
    """Sent when the connection is back (during the outage Telegram is unreachable)."""
    kind = event.get('kind', 'internet')
    message = (
        f"{'🌐' if kind == 'internet' else '🔌'} <b>{_t(lang, 'outage_' + kind)}</b>\n\n"
        f"{_t(lang, 'outage_body_' + kind)}.\n"
        f"{_t(lang, 'from_to', start=html.escape(event.get('start') or ''), end=html.escape(event.get('end') or ''))}\n"
        f"{_t(lang, 'duration')}: <b>{fmt_duration(event.get('duration'))}</b>"
    )
    return send_telegram_message(bot_token, chat_id, message).get('success', False)


def test_connection(bot_token: str, chat_id: str, lang: str = 'es') -> dict:
    """Send a test message to verify the Telegram configuration.

    Returns dict with 'success' bool and 'message' string (always in Spanish:
    the UI translates server messages).
    """
    if not bot_token:
        return {"success": False, "message": _t('es', 'no_token')}
    if not chat_id:
        return {"success": False, "message": _t('es', 'no_chat')}

    test_msg = f"✅ <b>{_t(lang, 'ok_title')}</b>\n\n{_t(lang, 'ok_body')}"

    result = send_telegram_message(bot_token, chat_id, test_msg)
    if result.get("success"):
        return {"success": True, "message": _t('es', 'sent')}
    else:
        error = result.get("error", _t('es', 'unknown_error'))
        return {"success": False, "message": _t('es', 'tg_error', error=error)}
