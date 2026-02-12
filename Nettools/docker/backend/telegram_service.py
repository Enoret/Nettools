"""
NetTools - Telegram Notification Service
"""

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
        mac = d.get('mac_address', '-')
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
