"""Manual, authenticated Telegram publishing through GitHub Actions.

Credentials are read only from GitHub Secrets, never from the browser.
"""
import html
import os
import re
import sys
import requests


def build_message(asin, title, price):
    if not re.fullmatch(r"[A-Z0-9]{10}", asin):
        raise ValueError("ASIN non valido")
    title = title.strip()
    if not title or len(title) > 180:
        raise ValueError("Titolo non valido")
    amount = float(price)
    if not (0 < amount < 100000):
        raise ValueError("Prezzo non valido")
    tag = os.environ["AMAZON_PARTNER_TAG"]
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", tag):
        raise ValueError("Partner tag non valido")
    url = f"https://www.amazon.it/dp/{asin}?tag={tag}"
    return f"📦 <b>{html.escape(title)}</b>\\n💰 <b>{amount:.2f} €</b>\\n🛒 <a href=\"{url}\">Vai all'offerta</a>"


def main():
    required = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "AMAZON_PARTNER_TAG")
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError("Credenziali mancanti")
    message = build_message(os.environ["DEAL_ASIN"], os.environ["DEAL_TITLE"], os.environ["DEAL_PRICE"])
    endpoint = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    response = requests.post(endpoint, json={"chat_id": os.environ["TELEGRAM_CHANNEL_ID"], "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram non ha confermato la pubblicazione")
    print("Pubblicazione confermata")


if __name__ == "__main__":
    main()
