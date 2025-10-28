import threading
import time

from bots.bot_cliente import main as run_client_bot
from bots.bot_notificador import monitor_log


def start_client_bot() -> None:
    print("[Main] Iniciando bot de clientes...")
    run_client_bot()


def start_notifier_bot() -> None:
    print("[Main] Iniciando bot de monitoreo de errores...")
    monitor_log()


def main() -> None:
    client_thread = threading.Thread(target=start_client_bot, name="ClientBot", daemon=True)
    notifier_thread = threading.Thread(target=start_notifier_bot, name="NotifierBot", daemon=True)

    client_thread.start()
    notifier_thread.start()

    print("[Main] Ambos bots en ejecución. Presioná Ctrl+C para detener.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Finalizando bots...")


if __name__ == "__main__":
    main()
