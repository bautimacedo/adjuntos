# bots/bot_notificador.py
import os
import sys
import time
from typing import Iterator, Optional, Dict
from urllib.parse import quote_plus

import requests

from utils.logger import ERROR_LOG_PATH

SUPPORT_BOT_TOKEN = "8289098822:AAEfnUjqB0dXgpO2xrt5VGr-PVbfDl6MMqY"
SUPPORT_CHAT_ID = -1003206038072

SEND_MESSAGE_URL = f"https://api.telegram.org/bot{SUPPORT_BOT_TOKEN}/sendMessage"
POLL_INTERVAL_SECONDS = 3


def tail_lines(path: str, start_position: Optional[int] = None) -> Iterator[str]:
    position = start_position if start_position is not None else 0

    while True:
        try:
            with open(path, "r", encoding="utf-8") as log_file:
                file_size = log_file.seek(0, os.SEEK_END)
                if file_size < position:
                    position = 0

                log_file.seek(position)
                chunk = log_file.read()
                position = log_file.tell()
        except FileNotFoundError:
            chunk = ""
            position = 0

        if chunk:
            for line in chunk.splitlines():
                yield line
        time.sleep(POLL_INTERVAL_SECONDS)


def send_notification_markdown(text: str) -> None:
    payload = {
        "chat_id": SUPPORT_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(SEND_MESSAGE_URL, data=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[NotifierBot] Error al notificar al equipo de soporte: {exc}", file=sys.stderr)


def parse_kv_line(line: str) -> Dict[str, str]:
    """
    Espera formato: 'WPP_REQUEST | k=v | k=v | ...'
    Devuelve dict con claves/valores.
    """
    parts = [p.strip() for p in line.split("|")]
    out: Dict[str, str] = {}
    for part in parts[1:]:  # saltamos 'WPP_REQUEST'
        if "=" in part:
            k, v = part.split("=", 1)
            out[k].strip() if False else None  # keep linter calm (no-op)
            out[k.strip()] = v.strip()
    return out


def handle_wpp_request(line: str) -> bool:
    """
    Si la línea es un WPP_REQUEST, arma URL wa.me con texto prellenado y notifica.
    Devuelve True si manejó la línea, False si no.
    """
    if "WPP_REQUEST" not in line:
        return False

    data = parse_kv_line(line)
    telefono_wa = data.get("telefono_wa", "").strip()
    usuario = data.get("usuario", "Cliente").strip()
    motivo = data.get("motivo", "Solicitud de contacto").strip()
    chat_id = data.get("chat_id", "").strip()

    if not telefono_wa.isdigit():
        return False

    saludo = (
        f"Hola {usuario}! Soy del soporte de NQNPetrol. "
        f"Vimos tu solicitud de asistencia ({motivo})."
    )
    texto = quote_plus(saludo)
    wa_url = f"https://wa.me/{telefono_wa}?text={texto}"

    md = (
        "*Solicitud de contacto por WhatsApp*\n\n"
        f"- Usuario: `{usuario}`\n"
        f"- Chat ID: `{chat_id}`\n"
        f"- Motivo: `{motivo}`\n"
        f"- Número: `{telefono_wa}`\n"
        f"- Link: {wa_url}\n\n"
        "_Tocá el link para abrir chat con saludo precargado._"
    )
    send_notification_markdown(md)
    return True


def send_plain_forward(line: str) -> None:
    send_notification_markdown(f"⚠️ *Error detectado en NQNPetrol*\n```\n{line}\n```")


def monitor_log(log_path: str = ERROR_LOG_PATH) -> None:
    start_position = None
    if os.path.exists(log_path):
        start_position = os.path.getsize(log_path)
    print(f"[NotifierBot] Monitoreando {log_path}")
    for raw_line in tail_lines(log_path, start_position=start_position):
        cleaned = raw_line.strip()
        if not cleaned:
            continue

        # Si es solicitud WPP, construimos URL y mensaje pro.
        if handle_wpp_request(cleaned):
            continue

        # Si no, reenviamos el texto crudo
        send_plain_forward(cleaned)
        time.sleep(0.5)


def main() -> None:
    monitor_log()


if __name__ == "__main__":
    main()
