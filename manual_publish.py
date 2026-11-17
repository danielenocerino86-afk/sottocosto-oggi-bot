"""Manual, authenticated Telegram publishing through GitHub Actions.

Credentials are read only from GitHub Secrets, never from the browser.
"""
import html
import os
import re
import sys
from storage import Store, cents
from publishing import send, publish


def build_message(asin, title, price):
    if not re.fullmatch(r"[A-Z0-9]{10}", asin):
        raise ValueError("ASIN non valido")
    title = title.strip()
    if not title or len(title) > 180:
        raise ValueError("Titolo non valido")
    amount = cents(price) / 100
    if not (0 < amount < 100000):
        raise ValueError("Prezzo non valido")
    tag = os.environ["AMAZON_PARTNER_TAG"]
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", tag):
        raise ValueError("Partner tag non valido")
    url = f"https://www.amazon.it/dp/{asin}?tag={tag}"
    return f"📦 <b>{html.escape(title)}</b>\n💰 <b>{amount:.2f} €</b>\n🛒 <a href=\"{url}\">Vai all'offerta</a>"


def main():
    required = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "AMAZON_PARTNER_TAG")
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError("Credenziali mancanti")
    message = build_message(os.environ["DEAL_ASIN"], os.environ["DEAL_TITLE"], os.environ["DEAL_PRICE"])
    if os.environ.get("BOT_PAUSED", "").lower() == "true":
        raise RuntimeError("Bot paused")
    deal = {"asin": os.environ["DEAL_ASIN"], "title": os.environ["DEAL_TITLE"], "current_price": cents(os.environ["DEAL_PRICE"]) / 100}
    ok = publish(Store(), deal, lambda: send(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHANNEL_ID"], message))
    if not ok:
        raise RuntimeError("Publication rejected or deduplicated")
    print("Pubblicazione confermata")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Pubblicazione non confermata; verificare stato e Telegram") from None
