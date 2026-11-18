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


def send_new_device_alert(bot_token: str, chat_id: str, devices: list) -> bool:
    """Send an alert about newly discovered devices.

    `devices` is a list of dicts with keys: ip_address, mac_address, hostname, brand, device_type
    """
    if not devices:
        return True

    count = len(devices)
    header = f"🔔 <b>NetTools - {'Nuevo dispositivo detectado' if count == 1 else f'{count} nuevos dispositivos detectados'}</b>\n"

    lines = []
    for d in devices:
        name = d.get('hostname') or d.get('ip_address') or 'Desconocido'
        ip = d.get('ip_address', '-')
        mac = d.get('mac_address') or 'sin MAC (red enrutada)'
        brand = d.get('brand', '')
        dtype = d.get('device_type', 'other')

        line = f"\n📡 <b>{name}</b>"
        line += f"\n   IP: <code>{ip}</code>"
        line += f"\n   MAC: <code>{mac}</code>"
        if brand:
            line += f"\n   Marca: {brand}"
        if dtype and dtype != 'other':
            line += f"\n   Tipo: {dtype}"
        lines.append(line)

    message = header + "\n".join(lines)

    result = send_telegram_message(bot_token, chat_id, message)
    return result.get("success", False)


def send_port_changes_alert(bot_token: str, chat_id: str, changes: list) -> bool:
    """Ports opened/closed since the previous scan, per device.
    `changes`: [{name, ip, new_ports: [{port, service}], closed_ports: [...]}]"""
    if not changes:
        return True

    def fmt(p):
        svc = p.get('service') or ''
        return f"{p['port']}" + (f" ({html.escape(svc)})" if svc else '')

    lines = [f"🚪 <b>NetTools - Cambios en puertos abiertos</b>"]
    for c in changes:
        lines.append(f"\n📡 <b>{html.escape(c['name'] or '')}</b> <code>{html.escape(c['ip'] or '')}</code>")
        if c['new_ports']:
            lines.append("   🆕 Abiertos: " + ", ".join(fmt(p) for p in c['new_ports']))
        if c['closed_ports']:
            lines.append("   ✖️ Cerrados: " + ", ".join(fmt(p) for p in c['closed_ports']))
    result = send_telegram_message(bot_token, chat_id, "\n".join(lines))
    return result.get("success", False)


def _fmt_delta(value, avg) -> str:
    """' (+3% vs media 7d)' or '' when there is no average."""
    if value is None or not avg:
        return ''
    pct = (value - avg) / avg * 100
    return f" <i>({pct:+.0f}% vs media 7d)</i>"


def send_speed_test_result(bot_token: str, chat_id: str, result: dict,
                           averages: dict = None, threshold: float = 0) -> bool:
    """Send the result of a scheduled speed test."""
    averages = averages or {}
    dl = result.get('download_speed') or 0
    ul = result.get('upload_speed') or 0
    slow = threshold and (dl < threshold or ul < threshold)

    title = "⚠️ <b>NetTools - Velocidad por debajo de lo esperado</b>" if slow \
        else "📶 <b>NetTools - Test de velocidad</b>"
    lines = [
        title,
        "",
        f"⬇️ Descarga: <b>{dl:.1f} Mbps</b>{_fmt_delta(dl, averages.get('download'))}",
        f"⬆️ Subida: <b>{ul:.1f} Mbps</b>{_fmt_delta(ul, averages.get('upload'))}",
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
        lines.append(f"📉 Perdida de paquetes: {loss:.1f}%")

    server = result.get('server_location') or result.get('server_name')
    if server:
        lines.append(f"🌐 Servidor: {html.escape(str(server))}")
    if result.get('isp'):
        lines.append(f"🏢 ISP: {html.escape(str(result['isp']))}")
    if slow:
        lines.append(f"\nUmbral configurado: {threshold:.0f} Mbps")

    url = (raw.get('result') or {}).get('url')
    if url:
        lines.append(f'\n<a href="{html.escape(url)}">Ver resultado en Speedtest</a>')

    return send_telegram_message(bot_token, chat_id, "\n".join(lines)).get('success', False)


def send_speed_test_failure(bot_token: str, chat_id: str, error: str) -> bool:
    message = (
        "❌ <b>NetTools - Test de velocidad fallido</b>\n\n"
        f"El test programado no se ha podido completar:\n<code>{html.escape(str(error))[:500]}</code>"
    )
    return send_telegram_message(bot_token, chat_id, message).get('success', False)


def test_connection(bot_token: str, chat_id: str) -> dict:
    """Send a test message to verify the Telegram configuration.

    Returns dict with 'success' bool and 'message' string.
    """
    if not bot_token:
        return {"success": False, "message": "Bot Token no configurado"}
    if not chat_id:
        return {"success": False, "message": "Chat ID no configurado"}

    test_msg = (
        "✅ <b>NetTools - Conexion exitosa</b>\n\n"
        "Las notificaciones de Telegram estan configuradas correctamente.\n"
        "Recibiras alertas cuando se detecten nuevos dispositivos en tu red."
    )

    result = send_telegram_message(bot_token, chat_id, test_msg)
    if result.get("success"):
        return {"success": True, "message": "Mensaje de prueba enviado correctamente"}
    else:
        error = result.get("error", "Error desconocido")
        return {"success": False, "message": f"Error de Telegram: {error}"}
