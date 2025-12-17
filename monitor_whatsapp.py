from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
import requests
import os
import json
import time
import pytz

# ================== CONFIG ==================

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
TARGET_USER = os.environ.get("TARGET_USER")

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")  # "+52..., +52..." separados por coma

STATE_FILE = "presence_state.json"
PROFILE_FILE = "user_profile.json"
KEEPALIVE_FILE = "keepalive_state.json"

KEEPALIVE_SECONDS = 20 * 60 * 60   # 20 horas
POLL_SECONDS = 60                  # Chequeo Slack cada 60s
API_BLOCK_SLEEP = 30 * 60          # 30 min si Meta bloquea

MX_TZ = pytz.timezone("America/Mexico_City")

# ================== HELPERS ==================

def get_numbers():
    if not WHATSAPP_TO:
        return []
    return [n.strip() for n in WHATSAPP_TO.split(",") if n.strip()]


def send_whatsapp(message: str) -> bool:
    numbers = get_numbers()
    if not numbers:
        print("WHATSAPP_TO vacío")
        return True

    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    blocked = False

    for num in numbers:
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": num,
                "type": "text",
                "text": {"body": message},
            }

            r = requests.post(url, headers=headers, json=payload, timeout=20)
            print(f"WhatsApp → {num}:", r.status_code, r.text)

            if r.status_code == 400 and "API access blocked" in r.text:
                blocked = True

        except Exception as e:
            print("Error WhatsApp:", e)

    if blocked:
        print("⚠️ Meta bloqueó la API. Durmiendo 30 minutos.")
        time.sleep(API_BLOCK_SLEEP)
        return False

    return True


def load_file(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except:
        return None


def save_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_user_name(slack, user_id):
    cached = load_file(PROFILE_FILE)
    if cached and cached.get("user_id") == user_id:
        return cached.get("name")

    try:
        r = slack.users_info(user=user_id)
        u = r["user"]
        name = (
            u.get("real_name")
            or u.get("profile", {}).get("display_name")
            or user_id
        )
        save_file(PROFILE_FILE, {"user_id": user_id, "name": name})
        return name
    except:
        return user_id


# ================== MAIN LOOP ==================

def main():
    if not all([SLACK_BOT_TOKEN, TARGET_USER, WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, WHATSAPP_TO]):
        print("❌ Faltan variables de entorno")
        return

    slack = WebClient(token=SLACK_BOT_TOKEN)
    name = get_user_name(slack, TARGET_USER)

    state_data = load_file(STATE_FILE) or {}
    keep_data = load_file(KEEPALIVE_FILE) or {}

    old_state = state_data.get("state")
    last_sent_ts = keep_data.get("last_sent_ts")

    while True:
        now_dt = datetime.now(MX_TZ)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        now_ts = int(time.time())

        try:
            resp = slack.users_getPresence(user=TARGET_USER)
            new_state = resp.get("presence")

            if old_state != new_state:
                if old_state is None:
                    msg = f"🔵 Estado inicial de {name}: {new_state}\n{now_str}"
                elif new_state == "active":
                    msg = f"🟢 {name} se CONECTÓ\n{now_str}"
                else:
                    msg = f"🔴 {name} se DESCONECTÓ\n{now_str}"

                if send_whatsapp(msg):
                    last_sent_ts = now_ts
                    save_file(KEEPALIVE_FILE, {"last_sent_ts": last_sent_ts})

                old_state = new_state
                save_file(STATE_FILE, {"state": new_state})
                print("Cambio detectado:", new_state)

            else:
                if last_sent_ts is None or (now_ts - last_sent_ts) >= KEEPALIVE_SECONDS:
                    keep = f"🟦 Seguimos monitoreando… Estado actual: {new_state}\n{now_str}"
                    if send_whatsapp(keep):
                        last_sent_ts = now_ts
                        save_file(KEEPALIVE_FILE, {"last_sent_ts": last_sent_ts})
                    print("Keep-alive enviado")

                else:
                    print(f"[{now_str}] Sin cambios ({new_state})")

        except SlackApiError as e:
            print("Error Slack:", e.response.get("error"))
            time.sleep(300)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
