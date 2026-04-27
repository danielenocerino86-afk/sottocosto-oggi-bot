"""
Sottocosto Oggi — Bot Telegram
Recupera offerte da Amazon Creators API e le pubblica su @sottocosto_oggi.
"""

import os
import json
import datetime
import time
import requests
from pathlib import Path

from amazon_creatorsapi import AmazonCreatorsApi, Country
from amazon_creatorsapi.models import SearchItemsResource, Condition

# ============================================================
# CONFIGURAZIONE (da GitHub Secrets o variabili d'ambiente)
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

# Soglia minima di sconto (%) per pubblicare l'offerta
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "20"))

# File per tracciare offerte già pubblicate (evita duplicati)
POSTED_FILE = Path(__file__).parent / "posted_deals.json"

# Keyword/categorie da cercare
SEARCH_KEYWORDS = [
    "Elettronica",
    "Informatica",
    "Casa e cucina",
    "Sport e tempo libero",
    "Videogiochi",
]


# ============================================================
# INIZIALIZZAZIONE API
# ============================================================
def create_api() -> AmazonCreatorsApi:
    """Crea l'istanza dell'API Amazon Creators."""
    return AmazonCreatorsApi(
        credential_id=AMAZON_CREDENTIAL_ID,
        credential_secret=AMAZON_CREDENTIAL_SECRET,
        version="2.2",
        tag=AMAZON_PARTNER_TAG,
        country=Country.IT,
        throttling=1.0,
    )


# ============================================================
# RICERCA OFFERTE
# ============================================================
def search_deals(api: AmazonCreatorsApi, keyword: str, max_results: int = 10) -> list[dict]:
    """Cerca prodotti in offerta per una keyword."""
        try:
        results = api.search_items(
            keywords=keyword,
            item_count=max_results,
            condition=Condition.NEW,
        )
    except Exception as e:
        print(f"[ERRORE API] {keyword}: {e}")
        return []

    if not results or not results.items:
        return []

    deals = []
    for item in results.items:
        deal = parse_item(item)
        if deal and deal["discount_percent"] >= MIN_DISCOUNT_PERCENT:
            deals.append(deal)

    return deals


def parse_item(item) -> dict | None:
    """Estrae le informazioni utili da un item dell'API."""
    try:
        asin = item.asin
        title = item.item_info.title.display_value
        url = item.detail_page_url

        listing = item.offers.listings[0]
        current_price = listing.price.amount

        # Prezzo originale (saving_basis)
        original_price = None
        if hasattr(listing, 'saving_basis') and listing.saving_basis:
            original_price = listing.saving_basis.amount

        if not original_price or original_price <= current_price:
            return None

        discount = original_price - current_price
        discount_percent = round((discount / original_price) * 100)

        image_url = None
        try:
            image_url = item.images.primary.large.url
        except (AttributeError, TypeError):
            pass

        return {
            "asin": asin,
            "title": title,
            "url": url,
            "current_price": current_price,
            "original_price": original_price,
            "discount": discount,
            "discount_percent": discount_percent,
            "image_url": image_url,
        }
    except (AttributeError, IndexError, TypeError) as e:
        print(f"[PARSE] Errore parsing item: {e}")
        return None


# ============================================================
# TELEGRAM
# ============================================================
def send_telegram_message(text: str, photo_url: str | None = None) -> bool:
    """Invia un messaggio (con foto opzionale) al canale Telegram."""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    try:
        if photo_url:
            resp = requests.post(
                f"{base_url}/sendPhoto",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "photo": photo_url,
                    "caption": text,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
        else:
            resp = requests.post(
                f"{base_url}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )

        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"[TELEGRAM] Errore invio: {e}")
        return False


def format_deal_message(deal: dict) -> str:
    """Formatta il messaggio Telegram per un'offerta."""
    if deal["discount_percent"] >= 50:
        fire = "\U0001f525\U0001f525\U0001f525"
    elif deal["discount_percent"] >= 30:
        fire = "\U0001f525\U0001f525"
    else:
        fire = "\U0001f525"

    msg = (
        f"{fire} <b>-{deal['discount_percent']}%</b> {fire}\n\n"
        f"\U0001f4e6 <b>{deal['title'][:200]}</b>\n\n"
        f"\U0001f4b0 <s>{deal['original_price']:.2f}\u20ac</s> \u27a1 <b>{deal['current_price']:.2f}\u20ac</b>\n"
        f"\U0001f4b8 Risparmi: {deal['discount']:.2f}\u20ac\n\n"
        f'\U0001f6d2 <a href="{deal["url"]}">VAI ALL\'OFFERTA</a>\n\n'
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4e3 @sottocosto_oggi\n"
        f"#offerta #amazon #sconto{deal['discount_percent']}"
    )
    return msg


# ============================================================
# GESTIONE DUPLICATI
# ============================================================
def load_posted() -> set:
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text())
            return set(data)
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_posted(posted: set):
    recent = list(posted)[-500:]
    POSTED_FILE.write_text(json.dumps(recent))


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"Sottocosto Oggi Bot - Avvio {datetime.datetime.now().isoformat()}")
    print(f"Canale: {TELEGRAM_CHANNEL_ID}")
    print(f"Partner Tag: {AMAZON_PARTNER_TAG}")
    print(f"Sconto minimo: {MIN_DISCOUNT_PERCENT}%")

    # Validazione configurazione
    missing = []
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
                "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"Variabili mancanti: {', '.join(missing)}")
        return

    api = create_api()
    posted = load_posted()
    new_deals_count = 0

    for keyword in SEARCH_KEYWORDS:
        print(f"\nCerco offerte: {keyword}")
        deals = search_deals(api, keyword)
        print(f"   Trovate {len(deals)} offerte con sconto >= {MIN_DISCOUNT_PERCENT}%")

        for deal in deals:
            if deal["asin"] in posted:
                print(f"   Gia pubblicata: {deal['asin']}")
                continue

            print(f"   Pubblico: {deal['title'][:60]}... (-{deal['discount_percent']}%)")
            message = format_deal_message(deal)
            success = send_telegram_message(message, deal.get("image_url"))

            if success:
                posted.add(deal["asin"])
                new_deals_count += 1
                print(f"   Pubblicata!")
            else:
                print(f"   Errore invio")

            time.sleep(3)

    save_posted(posted)
    print(f"\nCompletato! {new_deals_count} nuove offerte pubblicate.")


if __name__ == "__main__":
    main()
