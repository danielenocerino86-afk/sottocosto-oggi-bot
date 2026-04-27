"""
Sottocosto Oggi - Bot Telegram
Recupera offerte da Amazon Creators API e le pubblica su @sottocosto_oggi.
"""

import os
import json
import datetime
import time
import requests
from pathlib import Path

from amazon_creatorsapi import AmazonCreatorsApi, Country
from amazon_creatorsapi.models import Condition

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "20"))

POSTED_FILE = Path(__file__).parent / "posted_deals.json"

SEARCH_KEYWORDS = [
    "Elettronica",
    "Informatica",
    "Casa e cucina",
    "Sport e tempo libero",
    "Videogiochi",
]


def create_api():
    return AmazonCreatorsApi(
        credential_id=AMAZON_CREDENTIAL_ID,
        credential_secret=AMAZON_CREDENTIAL_SECRET,
        version="2.2",
        tag=AMAZON_PARTNER_TAG,
        country=Country.IT,
        throttling=1.0,
    )


def search_deals(api, keyword, max_results=10):
    try:
        results = api.search_items(
            keywords=keyword,
            item_count=max_results,
            condition=Condition.NEW,
        )
    except Exception as e:
        print("[ERRORE API] {}: {}".format(keyword, e))
        return []

    if not results or not results.items:
        return []

    deals = []
    for item in results.items:
        deal = parse_item(item)
        if deal and deal["discount_percent"] >= MIN_DISCOUNT_PERCENT:
            deals.append(deal)

    return deals


def parse_item(item):
    try:
        asin = item.asin
        title = item.item_info.title.display_value
        url = item.detail_page_url

        listing = item.offers.listings[0]
        current_price = listing.price.amount

        original_price = None
        if hasattr(listing, "saving_basis") and listing.saving_basis:
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
        print("[PARSE] Errore parsing item: {}".format(e))
        return None


def send_telegram_message(text, photo_url=None):
    base_url = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)

    try:
        if photo_url:
            resp = requests.post(
                "{}/sendPhoto".format(base_url),
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
                "{}/sendMessage".format(base_url),
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
        print("[TELEGRAM] Errore invio: {}".format(e))
        return False


def format_deal_message(deal):
    if deal["discount_percent"] >= 50:
        fire = "\U0001f525\U0001f525\U0001f525"
    elif deal["discount_percent"] >= 30:
        fire = "\U0001f525\U0001f525"
    else:
        fire = "\U0001f525"

    msg = (
        "{fire} <b>-{pct}%</b> {fire}\n\n"
        "\U0001f4e6 <b>{title}</b>\n\n"
        "\U0001f4b0 <s>{orig:.2f}\u20ac</s> \u27a1 <b>{curr:.2f}\u20ac</b>\n"
        "\U0001f4b8 Risparmi: {disc:.2f}\u20ac\n\n"
        "\U0001f6d2 <a href=\"{url}\">VAI ALL'OFFERTA</a>\n\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f4e3 @sottocosto_oggi\n"
        "#offerta #amazon #sconto{pct}"
    ).format(
        fire=fire,
        pct=deal["discount_percent"],
        title=deal["title"][:200],
        orig=deal["original_price"],
        curr=deal["current_price"],
        disc=deal["discount"],
        url=deal["url"],
    )
    return msg


def load_posted():
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text())
            return set(data)
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_posted(posted):
    recent = list(posted)[-500:]
    POSTED_FILE.write_text(json.dumps(recent))


def main():
    print("Sottocosto Oggi Bot - Avvio {}".format(datetime.datetime.now().isoformat()))
    print("Canale: {}".format(TELEGRAM_CHANNEL_ID))
    print("Partner Tag: {}".format(AMAZON_PARTNER_TAG))
    print("Sconto minimo: {}%".format(MIN_DISCOUNT_PERCENT))

    missing = []
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
                "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print("Variabili mancanti: {}".format(", ".join(missing)))
        return

    api = create_api()
    posted = load_posted()
    new_deals_count = 0

    for keyword in SEARCH_KEYWORDS:
        print("\nCerco offerte: {}".format(keyword))
        deals = search_deals(api, keyword)
        print("   Trovate {} offerte con sconto >= {}%".format(len(deals), MIN_DISCOUNT_PERCENT))

        for deal in deals:
            if deal["asin"] in posted:
                print("   Gia pubblicata: {}".format(deal["asin"]))
                continue

            print("   Pubblico: {}... (-{}%)".format(deal["title"][:60], deal["discount_percent"]))
            message = format_deal_message(deal)
            success = send_telegram_message(message, deal.get("image_url"))

            if success:
                posted.add(deal["asin"])
                new_deals_count += 1
                print("   Pubblicata!")
            else:
                print("   Errore invio")

            time.sleep(3)

    save_posted(posted)
    print("\nCompletato! {} nuove offerte pubblicate.".format(new_deals_count))


if __name__ == "__main__":
    main()
