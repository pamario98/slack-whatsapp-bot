from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
import requests
import os
import json
import time

# ============ VARIABLES DE ENTORNO =============

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
TARGET_USER = os.environ.get("TARGET_USER")

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")

STATE_FILE = "presence_state.json"
PROFILE_FILE = "user_profile.json"


# ============ FUNCIONES AUXILIARES =============

def send_whatsapp(message: str):
    """Envía mensaje por WhatsApp Cloud API"""
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
    if not os.path.exists(STATE_FILE):
        return None
    try:
        return open(STATE_FILE, "r").read().strip() or None
    except:
        return None


def save_state(state: str):
    with open(STATE_FILE, "w") as f:
        f.write(state)


def load_profile():
    if not os.path.exists(PROFILE_FILE):
        return None
    try:
        return json.load(open(PROFILE_FILE, "r", encoding="utf-8"))
    except:
        return None


def save_profile(profile: dict):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False)


def get_user_name(slack_client, user_id: str) -> str:
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
    except:
        return user_id


# ============ MAIN LOOP =============

def main_loop():
    if not SLACK_BOT_TOKEN or not TARGET_USER:
        print("Faltan SLACK_BOT_TOKEN o TARGET_USER.")
        return

    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID and WHATSAPP_TO):
        print("Faltan variables de WhatsApp.")
        return

    slack = WebClient(token=SLACK_BOT_TOKEN)
    person_name = get_user_name(slack, TARGET_USER)

    old_state = load_state()

    while True:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            resp = slack.users_getPresence(user=TARGET_USER)
            new_state = resp.get("presence")

            if old_state != new_state:
                if old_state is not None:
                    # No mandar mensaje la primera vez
                    if new_state == "active":
                        text = f"🟢 {person_name} se CONECTÓ ({old_state} → {new_state})\n{now_str}"
                    else:
                        text = f"🔴 {person_name} se DESCONECTÓ ({old_state} → {new_state})\n{now_str}"

                    send_whatsapp(text)

                save_state(new_state)
                old_state = new_state
                print(f"Cambio detectado: {new_state}")
            else:
                print(f"[{now_str}] Sin cambios ({new_state})")

        except SlackApiError as e:
            print("Error Slack:", e.response.get("error"))

        time.sleep(10)  # <================= AQUÍ SE CAMBIA LA FRECUENCIA


if __name__ == "__main__":
    main_loop()
