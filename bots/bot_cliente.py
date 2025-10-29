# bots/bot_cliente.py
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List, Tuple
import re

import requests

import jsonsender
from utils.logger import log_error, log_operation

# ================== Config ==================
BOT_TOKEN = "8242825417:AAHS5y43tAG5KV3Btadx1Kvz7nRXvFkFyAg"
URL_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}/"

POLL_TIMEOUT = 30          # long polling
SLEEP_BETWEEN_POLLS = 4    # para no ciclar fuerte
SESSION_TTL_SECS = 180     # ⏳ duración de la ventana (ajustá a gusto)

MISSION_DURATION = 12 * 60  # ~12 minutos
mission_running = False
mission_start_time = 0.0
current_mission_name: Optional[str] = None

# Ajustes del flujo de soporte por WhatsApp
WPP_MIN_DIGITS = 8
WPP_MAX_DIGITS = 15

# ================== Logging helpers ==================
def client_log_operation(message: str, **context: Any) -> None:
    log_operation(f"[ClientBot] {message}", **context)

def client_log_error(message: str, **context: Any) -> None:
    log_error(f"[ClientBot] {message}", **context)

# ================== Estado en memoria ==================
# sessions[chat_id] = {"started_at": datetime, "expires_at": datetime, "user_name": str}
sessions: Dict[int, Dict[str, Any]] = {}
offset = 0  # Para no procesar mensajes viejos

# Estado simple para el flujo de soporte por WhatsApp
# support_flow[chat_id] = {"step": "ask_opt_in" | "ask_phone"}
support_flow: Dict[int, Dict[str, str]] = {}

# ================== Helpers de API ==================
def get_updates(offset_value: int) -> List[Dict[str, Any]]:
    """
    Obtiene updates con long polling. No envía mensajes (no hay chat_id en este nivel).
    Ante error, loguea y retorna lista vacía para que el loop principal continúe.
    """
    try:
        url = f"{URL_BASE}getUpdates?timeout={POLL_TIMEOUT}&offset={offset_value}"
        resp = requests.get(url, timeout=POLL_TIMEOUT + 5)
        resp.raise_for_status()
        result = resp.json().get("result", [])
        if result:
            client_log_operation("Actualizaciones recibidas", total=len(result))
        return result
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status == 409:
            client_log_error("Error 409: Bot activo en otra instancia", error=str(e))
        else:
            client_log_error("Error HTTP inesperado al pedir updates", error=str(e), status_code=status)
        return []
    except Exception as e:
        client_log_error("Error general al pedir updates", error=str(e))
        return []

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
    client_log_operation(
        "Sesión finalizada",
        chat_id=chat_id,
        duration_seconds=int((now() - session["started_at"]).total_seconds()) if session else None
    )

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

def yes_no_keyboard():
    return {
        "keyboard": [
            [{"text": "Sí"}, {"text": "No"}],
            [{"text": "/cancelar"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True
    }

def back_keyboard():
    return {
        "keyboard": [
            [{"text": "/cancelar"}],
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

# ================== WhatsApp Support Flow ==================
def prompt_support_opt_in(chat_id: int) -> None:
    """Ofrece al usuario ser contactado por WhatsApp."""
    support_flow[chat_id] = {"step": "ask_opt_in"}
    send_message(
        chat_id,
        (
            "Contactaremos al soporte.\n"
            "Si querés atención personalizada, podemos pedir tu número y te escriben por WhatsApp.\n"
            "¿Querés que te contacten por WhatsApp?\n\n"
            "Elegí una opción:"
        ),
        reply_markup=yes_no_keyboard()
    )

def normalize_and_validate_phone(text: str) -> Tuple[bool, Optional[str]]:
    """
    Acepta formatos variados, extrae dígitos y permite +.
    Valida largo entre WPP_MIN_DIGITS y WPP_MAX_DIGITS.
    """
    cleaned = re.sub(r"[^\d+]", "", text).strip()

    # Si hay más de un '+' o '+' no es primero, inválido
    if cleaned.count("+") > 1 or (len(cleaned) > 0 and "+" in cleaned[1:]):
        return False, None

    # Quitar '+' para contar dígitos
    digits = re.sub(r"[^\d]", "", cleaned)
    if not (WPP_MIN_DIGITS <= len(digits) <= WPP_MAX_DIGITS):
        return False, None

    # Normalizamos a formato e164 (+...) si venía con prefijo; si no, dejamos solo dígitos
    normalized = cleaned if cleaned.startswith("+") else digits
    return True, normalized

def handle_support_flow(chat_id: int, text: str, user_name: str) -> bool:
    """
    Maneja estados del flujo de soporte. Devuelve True si consumió el mensaje.
    """
    state = support_flow.get(chat_id)
    if not state:
        return False

    lower = text.lower().strip()

    # Escape global del flujo
    if lower == "/cancelar":
        support_flow.pop(chat_id, None)
        send_message(chat_id, "Flujo cancelado. ¿Querés volver al menú?", reply_markup=main_menu_keyboard())
        return True

    # Paso 1: ask_opt_in
    if state["step"] == "ask_opt_in":
        if lower in ("si", "sí"):
            support_flow[chat_id] = {"step": "ask_phone"}
            send_message(
                chat_id,
                "Perfecto. Decime tu número de WhatsApp (con prefijo si podés, ej: +549299xxxxxxx).",
                reply_markup=back_keyboard()
            )
            return True
        elif lower == "no":
            support_flow.pop(chat_id, None)
            send_message(chat_id, "Sin problema. Si cambiás de idea, escribí 'soporte' más tarde.", reply_markup=main_menu_keyboard())
            return True
        else:
            send_message(chat_id, "Elegí *Sí* o *No* por favor.", reply_markup=yes_no_keyboard())
            return True

    # Paso 2: ask_phone
    if state["step"] == "ask_phone":
        ok, phone = normalize_and_validate_phone(text)
        if not ok:
            send_message(
                chat_id,
                (
                    "No pude reconocer ese número. Mandalo con prefijo si podés (ej: +54...), "
                    f"y entre {WPP_MIN_DIGITS}-{WPP_MAX_DIGITS} dígitos."
                ),
                reply_markup=back_keyboard()
            )
            return True

        # Preparar datos para Notifier:
        # - telefono_wa = solo dígitos (sin +) para wa.me
        # - motivo: breve label útil para el soporte
        telefono_wa = "".join(ch for ch in phone if ch.isdigit())
        motivo = f"Error misión {current_mission_name or 'desconocida'}"

        # Escribimos una línea especial fácil de parsear por el notificador
        # usando un único string (sin kwargs), así no se mezcla con el formateo del logger.
        client_log_error(
            "WPP_REQUEST | chat_id=%s | usuario=%s | telefono_e164=%s | telefono_wa=%s | motivo=%s"
            % (chat_id, user_name, phone, telefono_wa, motivo)
        )

        support_flow.pop(chat_id, None)
        send_message(
            chat_id,
            "✅ ¡Listo! Soporte te va a contactar por WhatsApp en breve.",
            reply_markup=main_menu_keyboard()
        )
        return True

    return False

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
        send_message(chat_id, f"Ya tenés una ventana activa, {user_name}. Usá el menú o escribí 'cerrar' para reiniciar.")
        return
    start_session(chat_id, user_name)
    send_message(
        chat_id,
        (
            f"Hola, {user_name} 👋 Soy el bot operacional de NQNPetrol. "
            f"Tenés una ventana de atención de {SESSION_TTL_SECS} segundos."
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
            "Seleccioná la misión escribiendo o tocando 'mision1'."
        ),
    )

def handle_mision1(chat_id: int, user_name: str):
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
                    f"Volvé a intentarlo en {minutes} min {seconds} s."
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
                "Contactaremos al soporte.\n\n"
                "¿Querés que te contacten por WhatsApp para una atención personalizada?"
            ),
        )
        prompt_support_opt_in(chat_id)

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
                "Contactaremos al soporte.\n\n"
                "¿Querés que te contacten por WhatsApp para una atención personalizada?"
            ),
        )
        prompt_support_opt_in(chat_id)

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
                "Usá el menú para continuar o escribí 'Lista de misiones'."
            ),
        )
        send_main_menu(chat_id)
    else:
        send_message(chat_id, "No hay ventana activa. Escribí 'hola' para abrir una nueva sesión operativa.")

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

                # Si el usuario está en flujo de soporte, lo atendemos primero
                if chat_id in support_flow:
                    if handle_support_flow(chat_id, text, user_name):
                        continue

                if not is_session_active(chat_id) and chat_id in sessions:
                    end_session(chat_id)
                    remove_keyboard(chat_id, "⏳ La ventana expiró por inactividad. Escribí 'hola' para empezar de nuevo.")

                lower = text.lower()
                if lower in ("/start", "hola"):
                    handle_start_or_hola(chat_id, user_name)
                elif lower == "lista de misiones":
                    handle_lista_misiones(chat_id)
                elif lower == "mision1":
                    handle_mision1(chat_id, user_name)
                elif lower == "estado":
                    handle_estado(chat_id)
                elif lower in ("cerrar", "/cerrar"):
                    handle_cerrar(chat_id)
                elif lower == "soporte":
                    prompt_support_opt_in(chat_id)
                else:
                    handle_fallback(chat_id)

        time.sleep(SLEEP_BETWEEN_POLLS)

if __name__ == "__main__":
    main()
