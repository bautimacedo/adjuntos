import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import sys

import requests

import jsonsender
from utils.logger import log_error, log_operation

# ================== Config ==================
BOT_TOKEN = "8242825417:AAHS5y43tAG5KV3Btadx1Kvz7nRXvFkFyAg"
URL_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}/"

POLL_TIMEOUT = 30          # long polling
SLEEP_BETWEEN_POLLS = 4    # para no ciclar fuerte
SESSION_TTL_SECS = 180     # ⏳ duración de la ventana (ajustá a gusto)

MISSION_DURATION = 12 * 60
mission_running = False
mission_start_time = 0.0
current_mission_name: Optional[str] = None


# ================== Logging helpers ==================

def client_log_operation(message: str, **context: Any) -> None:
    log_operation(f"[ClientBot] {message}", **context)


def client_log_error(message: str, **context: Any) -> None:
    log_error(f"[ClientBot] {message}", **context)



# ================== Estado en memoria ==================
# sessions[chat_id] = {"started_at": datetime, "expires_at": datetime, "user_name": str}
sessions: Dict[int, Dict[str, Any]] = {}
offset = 0  # Para no procesar mensajes viejos


# ================== Helpers de API ==================
def get_updates(chat_id: int, offset_value: int):
    try:
        url = f"{URL_BASE}getUpdates?timeout={POLL_TIMEOUT}&offset={offset_value}"
        r = requests.get(url, timeout=POLL_TIMEOUT + 5)
        r.raise_for_status()
        result = r.json().get("result", [])
        if result:
            client_log_operation("Actualizaciones recibidas", total=len(result))
        return result
    except requests.exceptions.HTTPError as e:
        if r.status_code == 409:
            client_log_error("Error 409: Bot Activo en Otra Instancia", error=str(e))
        else:
            client_log_error("Error HTTP inesperado", error=str(e))
    except Exception as e:
        client_log_error("Error General", error=str(e))
    send_message(
        chat_id, "Se ha Producido un Error interno en el Bot. Contactar con Soporte.")
    sys.exit(1)
        


def send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    url = f"{URL_BASE}sendMessage"
    data: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(url, data=data, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        client_log_error("Error al enviar mensaje", chat_id=chat_id, error=str(e), payload=text)


def remove_keyboard(chat_id: int, text: str = "Ventana cerrada. Escribí 'hola' para empezar de nuevo."):
    send_message(chat_id, text, reply_markup={"remove_keyboard": True})


# ================== Sesiones ==================
def now():
    return datetime.now(timezone.utc)


def is_session_active(chat_id: int) -> bool:
    s = sessions.get(chat_id)
    if not s:
        return False
    if now() >= s["expires_at"]:
        sessions.pop(chat_id, None)
        return False
    return True


def touch_session(chat_id: int) -> None:
    if chat_id in sessions:
        sessions[chat_id]["expires_at"] = now() + timedelta(seconds=SESSION_TTL_SECS)


def start_session(chat_id: int, user_name: str) -> None:
    sessions[chat_id] = {
        "started_at": now(),
        "expires_at": now() + timedelta(seconds=SESSION_TTL_SECS),
        "user_name": user_name,
    }
    client_log_operation("Sesión iniciada", chat_id=chat_id, user_name=user_name)


def end_session(chat_id: int) -> None:
    session = sessions.pop(chat_id, None)
    client_log_operation("Sesión finalizada", chat_id=chat_id, duration_seconds=int((now() - session["started_at"]).total_seconds()) if session else None)


# ================== UI: Menú ==================
def main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "mision1"}],
            [{"text": "Lista de misiones"}],
            [{"text": "Estado"}],
            [{"text": "Cerrar"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True
    }


def send_main_menu(chat_id: int):
    send_message(
        chat_id,
        (
            "Menú principal:\n"
            "• mision1 — Inicia la misión programada.\n"
            "• Lista de misiones — Consulta las misiones disponibles.\n"
            "• Estado — Revisa el estado operativo del dron.\n"
            "• Cerrar — Finaliza la sesión actual."
        ),
        reply_markup=main_menu_keyboard()
    )


# ================== Lógica de misiones ==================
def update_mission_state():
    global mission_running, mission_start_time, current_mission_name

    if mission_running:
        elapsed = time.time() - mission_start_time
        if elapsed >= MISSION_DURATION:
            client_log_operation(
                "Misión completada por duración programada",
                mission=current_mission_name,
                elapsed_seconds=int(elapsed),
            )
            mission_running = False
            mission_start_time = 0.0
            current_mission_name = None


def format_mission_status() -> str:
    update_mission_state()

    if mission_running and current_mission_name:
        elapsed = time.time() - mission_start_time
        remaining = max(0, int(MISSION_DURATION - elapsed))
        minutes, seconds = divmod(remaining, 60)
        return (
            "🛠️ Estado operativo: EN EJECUCIÓN\n"
            f"Misión activa: {current_mission_name}.\n"
            f"Tiempo restante estimado: {minutes} min {seconds} s."
        )

    return "🛠️ Estado operativo: INACTIVO\nNo hay misiones en curso en este momento."


# ================== Lógica de comandos ==================
def handle_start_or_hola(chat_id: int, user_name: str):
    if is_session_active(chat_id):
        touch_session(chat_id)
        send_message(chat_id, f"Ya tienes una ventana activa, {user_name}. Utiliza el menú o escribe 'cerrar' para reiniciar.")
        return
    start_session(chat_id, user_name)
    send_message(
        chat_id,
        (
            f"Hola, {user_name} 👋 Soy el bot operacional de NQNPetrol. "
            f"Tienes una ventana de atención de {SESSION_TTL_SECS} segundos."
        ),
    )
    send_main_menu(chat_id)


def handle_lista_misiones(chat_id: int):
    if not is_session_active(chat_id):
        remove_keyboard(chat_id, "Tu ventana estaba cerrada por inactividad. Escribí 'hola' para abrir una nueva.")
        return
    touch_session(chat_id)
    send_message(
        chat_id,
        (
            "Misiones disponibles:\n"
            "1. Perímetro Planta — Patrulla automática del perímetro.\n\n"
            "Selecciona la misión escribiendo o tocando 'mision1'."
        ),
    )


def handle_mision1(chat_id: int):
    global mission_running, mission_start_time, current_mission_name

    if not is_session_active(chat_id):
        remove_keyboard(chat_id, "Tu ventana estaba cerrada por inactividad. Escribí 'hola' para abrir una nueva.")
        return

    touch_session(chat_id)
    update_mission_state()

    if mission_running:
        elapsed = time.time() - mission_start_time
        remaining = int(MISSION_DURATION - elapsed)

        if remaining > 0:
            minutes, seconds = divmod(remaining, 60)
            send_message(
                chat_id,
                (
                    "🚫 Operación rechazada.\n"
                    "La misión 'Perímetro Planta' continúa en progreso.\n"
                    f"Vuelve a intentarlo en {minutes} min {seconds} s."
                ),
            )
            client_log_operation(
                "Intento de envío mientras misión activa",
                chat_id=chat_id,
                remaining_seconds=remaining,
            )
            return

    send_message(chat_id, "Iniciando misión programada 🚀")
    try:
        response = jsonsender.enviar()
        mission_running = True
        mission_start_time = time.time()
        current_mission_name = "mision1"

        client_log_operation(
            "Misión enviada correctamente",
            chat_id=chat_id,
            mission=current_mission_name,
            response=response,
        )

        send_message(
            chat_id,
            (
                "✅ Misión 'Perímetro Planta' enviada correctamente.\n"
                "Bloqueo operativo activo hasta su finalización (~12 min)."
            ),
        )

    except requests.exceptions.RequestException as e:
        client_log_error(
            "Error de comunicación con FlytBase",
            chat_id=chat_id,
            mission="mision1",
            error=str(e),
        )
        send_message(
            chat_id,
            (
                "⚠️ No se pudo enviar la misión a FlytBase.\n"
                "Nuestro equipo ya está al tanto; intenta nuevamente o contacta soporte."
            ),
        )
    except Exception as e:
        client_log_error(
            "Error inesperado al procesar misión",
            chat_id=chat_id,
            mission="mision1",
            error=str(e),
        )
        send_message(
            chat_id,
            (
                "❌ Se produjo un error inesperado al programar la misión.\n"
                "Hemos registrado el incidente para su análisis."
            ),
        )


def handle_estado(chat_id: int):
    if not is_session_active(chat_id):
        remove_keyboard(chat_id, "Tu ventana estaba cerrada por inactividad. Escribí 'hola' para abrir una nueva.")
        return

    touch_session(chat_id)
    status_message = format_mission_status()
    client_log_operation("Consulta de estado", chat_id=chat_id, status=status_message)
    send_message(chat_id, status_message)


def handle_cerrar(chat_id: int):
    if is_session_active(chat_id):
        end_session(chat_id)
    client_log_operation("Cierre de sesión solicitado", chat_id=chat_id)
    remove_keyboard(chat_id)


def handle_fallback(chat_id: int):
    if is_session_active(chat_id):
        touch_session(chat_id)
        send_message(
            chat_id,
            (
                "No pude interpretar el mensaje recibido.\n"
                "Utiliza el menú para continuar o escribe 'Lista de misiones'."
            ),
        )
        send_main_menu(chat_id)
    else:
        send_message(chat_id, "No hay ventana activa. Escribe 'hola' para abrir una nueva sesión operativa.")


# ================== Ignorar mensajes viejos ==================
def clear_pending_updates():
    """Descarta mensajes pendientes antes de iniciar el loop."""
    global offset
    try:
        url = f"{URL_BASE}getUpdates?timeout=1"
        r = requests.get(url, timeout=3)
        r.raise_for_status()
        data = r.json().get("result", [])
        if data:
            offset = data[-1]["update_id"] + 1
            client_log_operation("Ignorando mensajes previos al arranque", total=len(data))
        else:
            client_log_operation("No hay mensajes pendientes al inicio")
    except Exception as e:
        client_log_error("Error al limpiar mensajes pendientes", error=str(e))


# ================== Loop principal ==================
def main():
    global offset
    client_log_operation("Bot iniciado con ventanas de conversación y control de misión…")

    clear_pending_updates()

    while True:
        updates = get_updates(offset)
        if updates:
            for update in updates:
                offset = update["update_id"] + 1

                if "message" not in update:
                    continue

                message = update["message"]
                chat_id = message["chat"]["id"]
                text = (message.get("text") or "").strip()
                user_name = message["from"].get("first_name", "Desconocido")

                if not is_session_active(chat_id) and chat_id in sessions:
                    end_session(chat_id)
                    remove_keyboard(chat_id, "⏳ La ventana expiró por inactividad. Escribí 'hola' para empezar de nuevo.")

                lower = text.lower()
                if lower in ("/start", "hola"):
                    handle_start_or_hola(chat_id, user_name)
                elif lower == "lista de misiones":
                    handle_lista_misiones(chat_id)
                elif lower == "mision1":
                    handle_mision1(chat_id)
                elif lower == "estado":
                    handle_estado(chat_id)
                elif lower in ("cerrar", "/cerrar"):
                    handle_cerrar(chat_id)
                else:
                    handle_fallback(chat_id)

        time.sleep(SLEEP_BETWEEN_POLLS)


if __name__ == "__main__":
    main()
