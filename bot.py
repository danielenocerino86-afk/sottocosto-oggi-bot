"""
Sottocosto Oggi - Bot Telegram v7
Recupera offerte da Amazon Creators API e le pubblica su @sottocosto_oggi.
Anti-duplicati giornaliero. Mix casuale categorie. Hashtag categoria cliccabili.
"""

import os
import json
import datetime
import time
import random
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
MAX_POSTS_PER_CATEGORY = 5
POST_INTERVAL_SECONDS = 120

POSTED_FILE = Path(__file__).parent / "posted_deals.json"

SEARCH_KEYWORDS = [
    "Abbigliamento uomo",
    "Abbigliamento donna",
    "Scarpe",
    "Borse donna",
    "Bellezza e cosmetica",
    "Cura della persona",
    "Gioielli",
    "Orologi",
    "Elettronica",
    "Informatica",
    "Casa e cucina",
    "Sport e tempo libero",
    "Videogiochi",
    "Giochi e giocattoli",
    "Giardino e giardinaggio",
    "Fai da te",
    "Stampante 3D",
    "Filamento 3D",
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
        rating = None
        review_count = None

        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass

        if not asin or not title:
            return None

        try:
            listing = item.offers_v2.listings[0]
            price_obj = listing.price
            current_price = price_obj.money.amount
            if price_obj.saving_basis and price_obj.saving_basis.money:
                original_price = price_obj.saving_basis.money.amount
            if price_obj.savings:
                discount_pct = price_obj.savings.percentage
                if price_obj.savings.money:
                    saving_amount = price_obj.savings.money.amount
        except (AttributeError, TypeError, IndexError) as e:
            print("   [SKIP] Errore prezzi {}: {}".format(asin, e))
            return None

        if not current_price:
            return None
        if not original_price and discount_pct and discount_pct > 0:
            original_price = round(current_price / (1 - discount_pct / 100), 2)
        if not discount_pct and original_price and original_price > current_price:
            discount_pct = round(((original_price - current_price) / original_price) * 100)
        if not original_price or original_price <= current_price:
            return None
        if not saving_amount:
            saving_amount = round(original_price - current_price, 2)
        if not discount_pct or discount_pct < MIN_DISCOUNT_PERCENT:
            return None

        try:
            image_url = item.images.primary.large.url
        except (AttributeError, TypeError):
            pass

        try:
            if item.customer_reviews:
                if hasattr(item.customer_reviews, 'star_rating') and item.customer_reviews.star_rating:
                    rating = item.customer_reviews.star_rating.value
                if hasattr(item.customer_reviews, 'count') and item.customer_reviews.count:
                    review_count = item.customer_reviews.count
        except (AttributeError, TypeError):
            pass

        return {
            "asin": asin, "title": title,
            "current_price": current_price, "original_price": original_price,
            "discount": saving_amount, "discount_percent": discount_pct,
            "image_url": image_url, "rating": rating, "review_count": review_count,
        }
    except Exception as e:
        print("[PARSE] Errore: {}".format(e))
        return None


def get_category_emoji(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg", "resina 3d", "ugello"]): return "\U0001f5a8"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon"]): return "\U0001f3a7"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "\u231a"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel"]): return "\U0001f4f1"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "\U0001f4bb"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "\U0001f4f2"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo"]): return "\U0001f4fa"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro"]): return "\U0001f4f7"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal"]): return "\U0001f45f"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito"]): return "\U0001f455"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone"]): return "\U0001f45c"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "\U0001f48d"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo"]): return "\U0001f484"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat"]): return "\U0001f373"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia"]): return "\U0001f9f9"
    if any(w in t for w in ["lampad", "luce", "led", "illumin"]): return "\U0001f4a1"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller"]): return "\U0001f3ae"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis"]): return "\U0001f3cb"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "irrigaz"]): return "\U0001f331"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "\U0001f4da"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego"]): return "\U0001f9f8"
    return "\U0001f4e6"


def get_category_hashtag(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg", "resina 3d", "ugello"]): return "#stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon"]): return "#audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "#orologi"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel"]): return "#smartphone"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "#computer"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "#tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo"]): return "#tv"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro"]): return "#fotografia"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal"]): return "#scarpe"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito"]): return "#abbigliamento"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone"]): return "#borse"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "#gioielli"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo"]): return "#bellezza"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat"]): return "#cucina"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia"]): return "#casa"
    if any(w in t for w in ["lampad", "luce", "led", "illumin"]): return "#casa"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller"]): return "#gaming"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis"]): return "#sport"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "irrigaz"]): return "#giardino"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "#libri"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego"]): return "#giocattoli"
    return "#tech"


def send_telegram_message(text, image_url=None):
    base_url = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
    try:
        if image_url:
            resp = requests.post("{}/sendPhoto".format(base_url),
                json={"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text, "parse_mode": "HTML"}, timeout=15)
            if resp.json().get("ok"):
                return True
            print("   Foto fallita, invio senza immagine...")
        resp = requests.post("{}/sendMessage".format(base_url),
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}, timeout=15)
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print("[TELEGRAM] Errore invio: {}".format(e))
        return False


def format_deal_message(deal):
    pct = deal["discount_percent"]
    asin = deal["asin"]
    title = deal["title"]

    if pct >= 50: alert = "\U0001f6a8\U0001f6a8\U0001f6a8"
    elif pct >= 30: alert = "\U0001f6a8\U0001f6a8"
    else: alert = "\U0001f6a8"

    cat_emoji = get_category_emoji(title)
    cat_tag = get_category_hashtag(title)
    affiliate_link = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean_link = "https://www.amazon.it/dp/{}".format(asin)

    msg = "{alert} <b>SCONTO -{pct}%</b> {alert}\n\n".format(alert=alert, pct=pct)
    msg += "{emoji} <b>{title}</b>\n\n".format(emoji=cat_emoji, title=title[:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(deal["original_price"], deal["current_price"])
    msg += "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(deal["discount"])

    if deal.get("rating"):
        rc = deal.get("review_count", "")
        msg += "\u2b50 {}/5{}\n\n".format(deal["rating"], " ({} recensioni)".format(rc) if rc else "")

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerte ogni giorno\n"
    msg += "#offerta #amazon #sconto{} {}\n".format(pct, cat_tag)
    msg += "\u26a0\ufe0f <i>Prezzo soggetto a variazioni</i>"

    return msg


def load_posted():
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text())
            if isinstance(data, dict):
                today = datetime.date.today().isoformat()
                return {k: v for k, v in data.items() if k == today}
            return {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def save_posted(posted):
    POSTED_FILE.write_text(json.dumps(posted))


def is_already_posted(posted, asin):
    today = datetime.date.today().isoformat()
    if today not in posted:
        posted[today] = []
    return asin in posted[today]


def mark_as_posted(posted, asin):
    today = datetime.date.today().isoformat()
    if today not in posted:
        posted[today] = []
    posted[today].append(asin)


def main():
    today = datetime.date.today().isoformat()
    print("Sottocosto Oggi Bot v7 - Avvio {}".format(datetime.datetime.now().isoformat()))
    print("Data: {}".format(today))
    print("Canale: {}".format(TELEGRAM_CHANNEL_ID))
    print("Partner Tag: {}".format(AMAZON_PARTNER_TAG))
    print("Sconto minimo: {}%".format(MIN_DISCOUNT_PERCENT))
    print("Max post per categoria: {}".format(MAX_POSTS_PER_CATEGORY))
    print("Intervallo tra post: {} secondi".format(POST_INTERVAL_SECONDS))
    print("Categorie: {}".format(len(SEARCH_KEYWORDS)))

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
    already_today = len(posted.get(today, []))
    print("Offerte gia pubblicate oggi: {}".format(already_today))

    all_deals = []
    for keyword in SEARCH_KEYWORDS:
        print("\nCerco offerte: {}".format(keyword))
        deals = search_deals(api, keyword)
        print("   Trovate {} offerte con sconto >= {}%".format(len(deals), MIN_DISCOUNT_PERCENT))
        count = 0
        for deal in deals:
            if count >= MAX_POSTS_PER_CATEGORY:
                break
            if not is_already_posted(posted, deal["asin"]):
                deal["_category"] = keyword
                all_deals.append(deal)
                count += 1

    print("\n--- Totale offerte nuove raccolte: {} ---".format(len(all_deals)))
    random.shuffle(all_deals)

    new_deals_count = 0
    for deal in all_deals:
        print("   Pubblico [{}]: {}... (-{}%)".format(deal["_category"], deal["title"][:50], deal["discount_percent"]))
        message = format_deal_message(deal)
        success = send_telegram_message(message, deal.get("image_url"))
        if success:
            mark_as_posted(posted, deal["asin"])
            new_deals_count += 1
            print("   Pubblicata! (attendo {} sec)".format(POST_INTERVAL_SECONDS))
            time.sleep(POST_INTERVAL_SECONDS)
        else:
            print("   Errore invio")

    save_posted(posted)
    total_today = len(posted.get(today, []))
    print("\nCompletato! {} nuove in questo ciclo. Totale oggi: {}".format(new_deals_count, total_today))


if __name__ == "__main__":
    main()
