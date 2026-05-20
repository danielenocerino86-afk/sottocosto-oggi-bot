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

     # Debug: mostra struttura offers_v2 del primo item
    first = results.items[0]
    try:
        ov2 = first.offers_v2
        if ov2:
            print("   DEBUG offers_v2 type: {}".format(type(ov2)))
            print("   DEBUG offers_v2 attrs: {}".format([a for a in dir(ov2) if not a.startswith('_')]))
            if hasattr(ov2, 'listings') and ov2.listings:
                l0 = ov2.listings[0]
                print("   DEBUG listing[0] attrs: {}".format([a for a in dir(l0) if not a.startswith('_')]))
                if hasattr(l0, 'price'):
                    print("   DEBUG listing[0].price: {}".format(l0.price))
                if hasattr(l0, 'saving_basis'):
                    print("   DEBUG listing[0].saving_basis: {}".format(l0.saving_basis))
            elif hasattr(ov2, 'summaries') and ov2.summaries:
                s0 = ov2.summaries[0]
                print("   DEBUG summary[0] attrs: {}".format([a for a in dir(s0) if not a.startswith('_')]))
            else:
                print("   DEBUG offers_v2 content: {}".format(ov2))
        else:
            print("   DEBUG offers_v2 is None/empty")
    except Exception as e:
        print("   DEBUG error: {}".format(e))

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
        url = None
        current_price = None
        original_price = None
        image_url = None

        # Titolo
        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass

        # URL
        try:
            url = item.detail_page_url
        except (AttributeError, TypeError):
            pass

        if not asin or not title:
            return None

        # === METODO 1: item.prices (wrapper semplificato) ===
        try:
            if hasattr(item, 'prices') and item.prices:
                if hasattr(item.prices, 'price') and item.prices.price:
                    current_price = item.prices.price.amount if hasattr(item.prices.price, 'amount') else item.prices.price
                if hasattr(item.prices, 'price_savings') and item.prices.price_savings:
                    original_price_calc = None
                    if hasattr(item.prices.price_savings, 'amount') and current_price:
                        saving = item.prices.price_savings.amount
                        original_price_calc = current_price + saving
                    if original_price_calc:
                        original_price = original_price_calc
                if hasattr(item.prices, 'saving_basis') and item.prices.saving_basis:
                    sb = item.prices.saving_basis
                    original_price = sb.amount if hasattr(sb, 'amount') else sb
        except (AttributeError, TypeError) as e:
            print("   [DEBUG] prices method error: {}".format(e))

        # === METODO 2: item.offers.listings ===
        if not current_price:
            try:
                if hasattr(item, 'offers') and item.offers:
                    listings = item.offers.listings if hasattr(item.offers, 'listings') else None
                    if listings and len(listings) > 0:
                        listing = listings[0]
                        if hasattr(listing, 'price') and listing.price:
                            current_price = listing.price.amount
                        if hasattr(listing, 'saving_basis') and listing.saving_basis:
                            original_price = listing.saving_basis.amount
            except (AttributeError, TypeError, IndexError) as e:
                print("   [DEBUG] offers method error: {}".format(e))

        # === METODO 3: item.offers.summaries ===
        if not current_price:
            try:
                if hasattr(item, 'offers') and item.offers:
                    summaries = item.offers.summaries if hasattr(item.offers, 'summaries') else None
                    if summaries and len(summaries) > 0:
                        s = summaries[0]
                        if hasattr(s, 'lowest_price') and s.lowest_price:
                            current_price = s.lowest_price.amount
                        if hasattr(s, 'highest_price') and s.highest_price:
                            original_price = s.highest_price.amount
            except (AttributeError, TypeError, IndexError) as e:
                print("   [DEBUG] summaries method error: {}".format(e))

        # === METODO 4: accesso diretto a attributi raw ===
        if not current_price:
            for attr_name in ['price', 'current_price', 'buybox_price']:
                try:
                    val = getattr(item, attr_name, None)
                    if val:
                        current_price = val.amount if hasattr(val, 'amount') else float(val)
                        break
                except (AttributeError, TypeError, ValueError):
                    continue

        if not current_price:
            print("   [SKIP] No price for: {}".format(asin))
            return None

        # Se non ho il prezzo originale ma il prodotto ha il saving percent
        if not original_price or original_price <= current_price:
            try:
                if hasattr(item, 'prices') and item.prices:
                    if hasattr(item.prices, 'percentage_saved') and item.prices.percentage_saved:
                        pct = item.prices.percentage_saved
                        if pct > 0:
                            original_price = round(current_price / (1 - pct / 100), 2)
            except (AttributeError, TypeError):
                pass

        if not original_price or original_price <= current_price:
            return None

        discount = round(original_price - current_price, 2)
        discount_percent = round((discount / original_price) * 100)

        # Immagine
        try:
            if hasattr(item, 'images') and item.images:
                if hasattr(item.images, 'primary') and item.images.primary:
                    if hasattr(item.images.primary, 'large') and item.images.primary.large:
                        image_url = item.images.primary.large.url
        except (AttributeError, TypeError):
            pass

        # Fallback immagine: image_large del wrapper
        if not image_url:
            try:
                image_url = item.image_large if hasattr(item, 'image_large') else None
            except (AttributeError, TypeError):
                pass

        # Costruisci link affiliato con tag
        affiliate_url = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
        clean_url = "https://www.amazon.it/dp/{}".format(asin)

        return {
            "asin": asin,
            "title": title,
            "url": affiliate_url,
            "clean_url": clean_url,
            "current_price": current_price,
            "original_price": original_price,
            "discount": discount,
            "discount_percent": discount_percent,
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

    if pct >= 50:
        fire = "\U0001f525\U0001f525\U0001f525"
    elif pct >= 30:
        fire = "\U0001f525\U0001f525"
    else:
        fire = "\U0001f525"

    msg = "{fire} <b>-{pct}%</b> {fire}\n\n".format(fire=fire, pct=pct)
    msg += "\U0001f4e6 <b>{}</b>\n\n".format(deal["title"][:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(
        deal["original_price"], deal["current_price"]
    )
    msg += "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(deal["discount"])
    msg += '\U0001f6d2 <a href="{}">VAI ALL\'OFFERTA</a>\n\n'.format(deal["url"])
    msg += "{}\n\n".format(deal["clean_url"])
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
