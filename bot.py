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
        version="3.2",
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
            min_saving_percent=MIN_DISCOUNT_PERCENT,
        )
    except Exception as e:
        print("[ERRORE API] {}: {}".format(keyword, e))
        return []

    if not results or not results.items:
        print("   Nessun risultato per {}".format(keyword))
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
        title = None
        current_price = None
        original_price = None
        discount_pct = None
        saving_amount = None
        image_url = None

        # Titolo
        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass

        if not asin or not title:
            return None

        # Prezzi da offers_v2.listings[0].price
        try:
            listing = item.offers_v2.listings[0]
            price_obj = listing.price

            # Prezzo attuale: price.money.amount
            current_price = price_obj.money.amount

            # Prezzo originale: price.saving_basis.money.amount
            if price_obj.saving_basis and price_obj.saving_basis.money:
                original_price = price_obj.saving_basis.money.amount

            # Sconto %: price.savings.percentage
            if price_obj.savings:
                discount_pct = price_obj.savings.percentage
                if price_obj.savings.money:
                    saving_amount = price_obj.savings.money.amount

        except (AttributeError, TypeError, IndexError) as e:
            print("   [SKIP] Errore prezzi {}: {}".format(asin, e))
            return None

        if not current_price:
            print("   [SKIP] No price: {}".format(asin))
            return None

        # Se non ho il prezzo originale ma ho lo sconto %, lo calcolo
        if not original_price and discount_pct and discount_pct > 0:
            original_price = round(current_price / (1 - discount_pct / 100), 2)

        # Se non ho lo sconto % ma ho entrambi i prezzi, lo calcolo
        if not discount_pct and original_price and original_price > current_price:
            discount_pct = round(((original_price - current_price) / original_price) * 100)

        if not original_price or original_price <= current_price:
            return None

        if not saving_amount:
            saving_amount = round(original_price - current_price, 2)

        if not discount_pct or discount_pct < MIN_DISCOUNT_PERCENT:
            return None

        # Immagine
        try:
            image_url = item.images.primary.large.url
        except (AttributeError, TypeError):
            pass

        return {
            "asin": asin,
            "title": title,
            "current_price": current_price,
            "original_price": original_price,
            "discount": saving_amount,
            "discount_percent": discount_pct,
            "image_url": image_url,
        }
    except Exception as e:
        print("[PARSE] Errore: {}".format(e))
        return None


def send_telegram_message(text):
    base_url = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
    try:
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
    pct = deal["discount_percent"]
    asin = deal["asin"]

    if pct >= 50:
        fire = "\U0001f525\U0001f525\U0001f525"
    elif pct >= 30:
        fire = "\U0001f525\U0001f525"
    else:
        fire = "\U0001f525"

    affiliate_link = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean_link = "https://www.amazon.it/dp/{}".format(asin)

    msg = "{fire} <b>-{pct}%</b> {fire}\n\n".format(fire=fire, pct=pct)
    msg += "\U0001f4e6 <b>{}</b>\n\n".format(deal["title"][:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(
        deal["original_price"], deal["current_price"]
    )
    msg += "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(deal["discount"])
    msg += '\U0001f6d2 <a href="{}">VAI ALL\'OFFERTA</a>\n\n'.format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    msg += "\U0001f4e3 @sottocosto_oggi\n"
    msg += "#offerta #amazon #sconto{}".format(pct)

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
            success = send_telegram_message(message)

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
