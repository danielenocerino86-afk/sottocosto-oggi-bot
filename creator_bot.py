"""
Sottocosto Oggi - Creator Bot
Polling Telegram per gestire il comando /creator in chat privata.
Gira come workflow GitHub Actions separato ogni 5 minuti.

Comando: /creator <link_amazon>
Solo l'admin (configurato via env ADMIN_ID) puo' usarlo.
"""

import os
import json
import requests
from pathlib import Path

from amazon_creatorsapi import AmazonCreatorsApi, Country

from creator_module import handle_creator_command

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

STATE_FILE = Path(__file__).parent / "creator_state.json"


def log(msg):
    for secret in (TELEGRAM_BOT_TOKEN, AMAZON_CREDENTIAL_SECRET):
        if secret:
            msg = str(msg).replace(secret, "[REDACTED]")
    print(msg, flush=True)


def get_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def get_updates(offset):
    url = "https://api.telegram.org/bot{}/getUpdates".format(TELEGRAM_BOT_TOKEN)
    try:
        resp = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=15)
        return resp.json().get("result", [])
    except Exception as e:
        log("[ERR] getUpdates: {}".format(e))
        return []


def send_message(chat_id, text):
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_BOT_TOKEN)
    try:
        requests.post(url, json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        log("[ERR] sendMessage: {}".format(e))


def send_photo(chat_id, photo_bytes, caption=None, filename="photo.png"):
    url = "https://api.telegram.org/bot{}/sendPhoto".format(TELEGRAM_BOT_TOKEN)
    try:
        files = {"photo": (filename, photo_bytes, "image/png")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        requests.post(url, files=files, data=data, timeout=30)
    except Exception as e:
        log("[ERR] sendPhoto: {}".format(e))


def send_document(chat_id, file_bytes, caption=None, filename="image.png"):
    """Invia come documento per preservare la qualita' originale."""
    url = "https://api.telegram.org/bot{}/sendDocument".format(TELEGRAM_BOT_TOKEN)
    try:
        files = {"document": (filename, file_bytes, "image/png")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        requests.post(url, files=files, data=data, timeout=30)
    except Exception as e:
        log("[ERR] sendDocument: {}".format(e))


def create_api():
    return AmazonCreatorsApi(
        credential_id=AMAZON_CREDENTIAL_ID,
        credential_secret=AMAZON_CREDENTIAL_SECRET,
        version="3.2", tag=AMAZON_PARTNER_TAG,
        country=Country.IT, throttling=1.0,
    )


def handle_message(message, api):
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "").strip()

    # Solo l'admin puo' usare il bot
    if user_id != ADMIN_ID:
        log("Ignoro messaggio da user_id={}".format(user_id))
        return

    if not text:
        return

    if text.startswith("/start"):
        send_message(chat_id,
            "👋 <b>Ciao!</b>\n\n"
            "Comandi disponibili:\n\n"
            "<b>/creator</b> &lt;link Amazon&gt;\n"
            "→ Genera storia Instagram + post quadrato + caption\n\n"
            "Esempio:\n"
            "<code>/creator https://www.amazon.it/dp/B0D816S1JH</code>"
        )
        return

    if text.startswith("/creator"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id,
                "❌ Usa: <code>/creator &lt;link Amazon&gt;</code>"
            )
            return

        url = parts[1].strip()
        send_message(chat_id, "🔄 Sto generando storia e post...")

        storia, post, caption, error = handle_creator_command(api, url, AMAZON_PARTNER_TAG)

        if error:
            send_message(chat_id, error)
            return

        # Invia storia (immagine)
        send_photo(chat_id, storia, caption="📱 Storia Instagram (1080x1920)",
                   filename="storia.png")
        # Re-invia storia come documento per preservare qualita'
        storia.seek(0)
        send_document(chat_id, storia, filename="storia_HD.png")

        # Invia post quadrato
        send_photo(chat_id, post, caption="📷 Post quadrato (1080x1080)",
                   filename="post.png")
        post.seek(0)
        send_document(chat_id, post, filename="post_HD.png")

        # Invia caption
        send_message(chat_id, "<b>📋 Caption pronta:</b>\n\n<code>{}</code>".format(caption))
        log("Creator completato!")


def main():
    log("=== Creator Bot polling ===")

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "AMAZON_CREDENTIAL_ID",
        "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG", "ADMIN_ID"] if not os.environ.get(v)]
    if missing:
        log("Mancano variabili: {}".format(missing))
        return

    state = get_state()
    offset = state.get("last_update_id", 0) + 1
    log("Offset: {}".format(offset))

    updates = get_updates(offset)
    log("Updates ricevuti: {}".format(len(updates)))

    if not updates:
        return

    api = create_api()

    max_id = state.get("last_update_id", 0)
    for upd in updates:
        upd_id = upd.get("update_id", 0)
        if upd_id > max_id:
            max_id = upd_id

        message = upd.get("message")
        if message:
            try:
                handle_message(message, api)
            except Exception as e:
                log("[ERR] handle_message: {}".format(e))

    state["last_update_id"] = max_id
    save_state(state)
    log("Nuovo offset salvato: {}".format(max_id + 1))


if __name__ == "__main__":
    main()
