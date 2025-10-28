import os
import sys
import time
from typing import Iterator, Optional

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


def send_notification(text: str) -> None:
    payload = {
        "chat_id": SUPPORT_CHAT_ID,
        "text": text,
    }
    try:
        response = requests.post(SEND_MESSAGE_URL, data=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[NotifierBot] Error al notificar al equipo de soporte: {exc}", file=sys.stderr)


def monitor_log(log_path: str = ERROR_LOG_PATH) -> None:
    start_position = None
    if os.path.exists(log_path):
        start_position = os.path.getsize(log_path)
    print(f"[NotifierBot] Monitoreando {log_path}")
    for line in tail_lines(log_path, start_position=start_position):
        cleaned = line.strip()
        if not cleaned:
            continue
        formatted = f"⚠️ Error detectado en NQNPetrol\n{cleaned}"
        send_notification(formatted)
        time.sleep(0.5)


def main() -> None:
    monitor_log()


if __name__ == "__main__":
    main()
