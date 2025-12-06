from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
import requests
import os
import json

# ============ VARIABLES DE ENTORNO =============

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
TARGET_USER = os.environ.get("TARGET_USER")            # ID usuario Slack

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")      # Token de Meta (EAAG...)
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")# Phone Number ID
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")            # Ej: 52155XXXXXXXX

STATE_FILE = "presence_state.json"
PROFILE_FILE = "user_profile.json"


# ============ FUNCIONES AUXILIARES =============

def send_whatsapp(message: str):
    """Envía mensaje de texto por WhatsApp Cloud API"""
    try:
        url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": WHATSAPP_TO,
            "type": "text",
            "text": {"body": message}
        }
        r = requests.post(url, headers=headers, json=data)
        print("Respuesta WhatsApp:", r.status_code, r.text)
    except Exception as e:
        print("Error enviando WhatsApp:", e)


def load_state():
    """Lee último estado guardado (active/away)"""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        return open(STATE_FILE, "r").read().strip() or None
    except Exception:
        return None


def save_state(state: str):
    """Guarda último estado"""
    with open(STATE_FILE, "w") as f:
        f.write(state)


def load_profile():
    if not os.path.exists(PROFILE_FILE):
        return None
    try:
        return json.load(open(PROFILE_FILE, "r", encoding="utf-8"))
    except Exception:
        return None


def save_profile(profile: dict):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False)


def get_user_name(slack_client, user_id: str) -> str:
    """Obtiene nombre de la persona vigilada"""
    profile = load_profile()
    if profile and profile.get("user_id") == user_id:
        return profile.get("name") or user_id

    try:
        resp = slack_client.users_info(user=user_id)
        user = resp.get("user", {})
        real_name = user.get("real_name") or user.get("profile", {}).get("real_name")
        display_name = user.get("profile", {}).get("display_name")
        name = real_name or display_name or user_id

        save_profile({"user_id": user_id, "name": name})
        return name
    except SlackApiError as e:
        print("Error obteniendo info de usuario:", e.response.get("error"))
        return user_id


# ============ MAIN =============

def main():
    # Validaciones
    if not SLACK_BOT_TOKEN or not TARGET_USER:
        print("Faltan SLACK_BOT_TOKEN o TARGET_USER.")
        return

    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID and WHATSAPP_TO):
        print("Faltan WHATSAPP_TOKEN, WHATSAPP_PHONE_ID o WHATSAPP_TO.")
        return

    slack = WebClient(token=SLACK_BOT_TOKEN)
    person_name = get_user_name(slack, TARGET_USER)

    old_state = load_state()
    now_str = datetime.now().strftime("%Y-%m-%d %Y-%m-%d %H:%M:%S")

    try:
        resp = slack.users_getPresence(user=TARGET_USER)
        new_state = resp.get("presence")  # 'active' o 'away'

        if old_state != new_state:
            if old_state is not None:
                # Solo mandamos mensaje si NO es la primera vez
                if new_state == "active":
                    texto = f"🟢 {person_name} se CONECTÓ a Slack ({old_state} → {new_state})\n{now_str}"
                elif new_state == "away":
                    texto = f"🔴 {person_name} se DESCONECTÓ de Slack ({old_state} → {new_state})\n{now_str}"
                else:
                    texto = f"{person_name} cambió de estado: {old_state} → {new_state}\n{now_str}"

                send_whatsapp(texto)

            save_state(new_state)
            print(f"Cambio detectado: {old_state} -> {new_state}")
        else:
            print(f"[{now_str}] Sin cambios. Estado actual: {new_state}")

    except SlackApiError as e:
        print("Error al consultar presencia en Slack:", e.response.get("error"))


if __name__ == "__main__":
    main()
