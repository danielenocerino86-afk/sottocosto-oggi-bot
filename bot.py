"""
Sottocosto Oggi - Bot Telegram v11
Pubblica 07:00-00:00 ora italiana. Mix casuale. Anti-duplicati giornaliero.
Priorita sconti alti. Filtro spam e prezzo minimo. Stelle rating.
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
MIN_PRICE = 5.0
MAX_POSTS_PER_CATEGORY = 3
MAX_POSTS_TOTAL = 25
POST_INTERVAL_SECONDS = 60

PUBLISH_START_HOUR = 7
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"

SEARCH_KEYWORDS = [
    "Smartphone",
    "Telefonia accessori",
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
    "Tablet",
    "Casa e cucina",
    "Casa intelligente smart home",
    "Illuminazione",
    "Sport e tempo libero",
    "Videogiochi",
    "Giochi e giocattoli",
    "Giardino e giardinaggio",
    "Fai da te",
    "Animali domestici",
    "Auto e moto accessori",
    "Salute e cura persona",
    "Valigie e borse viaggio",
    "Stampante 3D",
    "Filamento 3D",
    "Mobili e arredamento",
    "Biancheria letto e bagno",
    "Materassi e cuscini",
    "Strumenti musicali",
    "Prodotti per neonati",
    "Cancelleria e ufficio",
    "Alimentari e cura casa",
    "Fotocamere e accessori",
    "Arredamento bagno",
    "Climatizzazione e riscaldamento",
    "Aspirapolvere e pulizia casa",
]


def get_italy_now():
    utc_now = datetime.datetime.utcnow()
    return utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    return get_italy_now().hour >= PUBLISH_START_HOUR


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
        return []

    deals = []
    for item in results.items:
        deal = parse_item(item)
        if deal:
            deals.append(deal)

    return deals


def is_spam_title(title):
    if len(title) > 300:
        return True
    non_ascii = sum(1 for c in title if ord(c) > 0x4E00 and ord(c) < 0x9FFF)
    if non_ascii > 3:
        return True
    spam_words = ["clicca qui", "compra ora", "offerta limitata", "solo oggi", "gratis 100%"]
    t = title.lower()
    if any(w in t for w in spam_words):
        return True
    return False


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

        if is_spam_title(title):
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
        except (AttributeError, TypeError, IndexError):
            return None

        if not current_price or current_price < MIN_PRICE:
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
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon", "soundbar"]): return "\U0001f3a7"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "\u231a"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel", "custodia telefono", "cover telefono"]): return "\U0001f4f1"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "\U0001f4bb"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "\U0001f4f2"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo", "fire tv", "streaming"]): return "\U0001f4fa"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro", "drone", "reflex", "mirrorless"]): return "\U0001f4f7"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal", "mocassin", "ciabatt"]): return "\U0001f45f"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito", "gonna", "shorts"]): return "\U0001f455"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone", "trolley", "bagaglio"]): return "\U0001f45c"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "\U0001f48d"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo", "maschera viso", "rossetto"]): return "\U0001f484"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat", "caffettier"]): return "\U0001f373"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia", "scopa"]): return "\U0001f9f9"
    if any(w in t for w in ["lampad", "luce", "led", "illumin", "smart light"]): return "\U0001f4a1"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller", "gaming"]): return "\U0001f3ae"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis", "yoga", "corsa"]): return "\U0001f3cb"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "irrigaz", "barbecue"]): return "\U0001f331"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "\U0001f4da"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego", "puzzle"]): return "\U0001f9f8"
    if any(w in t for w in ["cane", "gatto", "animale", "pet", "guinzaglio", "crocchin", "antiparassit"]): return "\U0001f43e"
    if any(w in t for w in ["auto", "moto", "automobile", "tergicristal", "dashcam", "caricatore auto"]): return "\U0001f697"
    if any(w in t for w in ["alexa", "echo", "smart home", "domotica", "presa smart", "termostato"]): return "\U0001f3e0"
    if any(w in t for w in ["neonat", "biberon", "pannolin", "passeggino", "seggiolino"]): return "\U0001f476"
    if any(w in t for w in ["mobil", "scrivania", "libreria", "armadio", "divano", "sedia", "tavol"]): return "\U0001fa91"
    if any(w in t for w in ["materass", "cuscin", "coperta", "lenzuol", "piumon", "trapunta"]): return "\U0001f6cf"
    if any(w in t for w in ["chitarra", "pianola", "tastiera musicale", "ukulele", "batteria musicale"]): return "\U0001f3b8"
    if any(w in t for w in ["penna", "quaderno", "zaino scuola", "matita", "cancelleria", "evidenziator"]): return "\u270f"
    if any(w in t for w in ["condizionator", "ventilator", "stufa", "radiator", "climatizza", "riscalda"]): return "\u2744"
    return "\U0001f4e6"


def get_category_hashtag(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg", "resina 3d", "ugello"]): return "#stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon", "soundbar"]): return "#audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "#orologi"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel", "custodia telefono", "cover telefono"]): return "#smartphone"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "#computer"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "#tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo", "fire tv", "streaming"]): return "#tv"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro", "drone", "reflex", "mirrorless"]): return "#fotografia"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal", "mocassin", "ciabatt"]): return "#scarpe"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito", "gonna", "shorts"]): return "#abbigliamento"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone", "trolley", "bagaglio"]): return "#borse"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "#gioielli"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo", "maschera viso", "rossetto"]): return "#bellezza"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat", "caffettier"]): return "#cucina"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia", "scopa"]): return "#casa"
    if any(w in t for w in ["lampad", "luce", "led", "illumin", "smart light"]): return "#casa"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller", "gaming"]): return "#gaming"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis", "yoga", "corsa"]): return "#sport"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "irrigaz", "barbecue"]): return "#giardino"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "#libri"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego", "puzzle"]): return "#giocattoli"
    if any(w in t for w in ["cane", "gatto", "animale", "pet", "guinzaglio", "crocchin", "antiparassit"]): return "#animali"
    if any(w in t for w in ["auto", "moto", "automobile", "tergicristal", "dashcam", "caricatore auto"]): return "#auto"
    if any(w in t for w in ["alexa", "echo", "smart home", "domotica", "presa smart", "termostato"]): return "#smarthome"
    if any(w in t for w in ["neonat", "biberon", "pannolin", "passeggino", "seggiolino"]): return "#neonati"
    if any(w in t for w in ["mobil", "scrivania", "libreria", "armadio", "divano", "sedia", "tavol"]): return "#arredamento"
    if any(w in t for w in ["materass", "cuscin", "coperta", "lenzuol", "piumon", "trapunta"]): return "#casa"
    if any(w in t for w in ["chitarra", "pianola", "tastiera musicale", "ukulele", "batteria musicale"]): return "#musica"
    if any(w in t for w in ["penna", "quaderno", "zaino scuola", "matita", "cancelleria", "evidenziator"]): return "#cancelleria"
    if any(w in t for w in ["condizionator", "ventilator", "stufa", "radiator", "climatizza", "riscalda"]): return "#clima"
    return "#tech"


def send_telegram(text, image_url=None):
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
        print("[TELEGRAM] Errore: {}".format(e))
        return False


def format_deal_message(deal, deal_number=0):
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
        try:
            r = float(deal["rating"])
            full = int(r)
            empty = 5 - full
            stars = "\u2B50" * full + "\u2606" * empty
            rc = deal.get("review_count", "")
            msg += "{} {}/5{}\n\n".format(stars, deal["rating"], " ({} recensioni)".format(rc) if rc else "")
        except (ValueError, TypeError):
            pass

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    if deal_number > 0:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerta #{} di oggi\n".format(deal_number)
    else:
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
    if asin not in posted[today]:
        posted[today].append(asin)


def main():
    italy_now = get_italy_now()
    today = datetime.date.today().isoformat()

    print("Sottocosto Oggi Bot v11 - {}".format(datetime.datetime.now().isoformat()))
    print("Ora italiana: {}".format(italy_now.strftime("%H:%M")))

    if not is_publish_time():
        print("Fuori orario (prima delle {:02d}:00). Stop.".format(PUBLISH_START_HOUR))
        return

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
    print("Gia pubblicate oggi: {} | Categorie: {} | Min prezzo: {}".format(
        already_today, len(SEARCH_KEYWORDS), MIN_PRICE))

    all_deals = []
    seen_asins = set(posted.get(today, []))

    for keyword in SEARCH_KEYWORDS:
        deals = search_deals(api, keyword)
        new_count = 0
        for deal in deals:
            if new_count >= MAX_POSTS_PER_CATEGORY:
                break
            asin = deal["asin"]
            if asin in seen_asins:
                continue
            seen_asins.add(asin)
            deal["_category"] = keyword
            all_deals.append(deal)
            new_count += 1
        if new_count > 0:
            print("  {} -> {} nuove".format(keyword, new_count))

    print("\nOfferte nuove: {}".format(len(all_deals)))

    if not all_deals:
        print("Nessuna offerta nuova.")
        return

    # Ordina per sconto decrescente, poi mischia a blocchi
    all_deals.sort(key=lambda d: d["discount_percent"], reverse=True)
    top_deals = all_deals[:5]
    rest_deals = all_deals[5:]
    random.shuffle(rest_deals)
    all_deals = top_deals + rest_deals

    if len(all_deals) > MAX_POSTS_TOTAL:
        all_deals = all_deals[:MAX_POSTS_TOTAL]

    new_deals_count = 0
    for deal in all_deals:
        if not is_publish_time():
            print("Orario scaduto. Stop.")
            break

        if is_already_posted(posted, deal["asin"]):
            continue

        deal_number = already_today + new_deals_count + 1
        print("  #{} [{}] {}... (-{}%)".format(deal_number, deal["_category"], deal["title"][:45], deal["discount_percent"]))
        message = format_deal_message(deal, deal_number)
        success = send_telegram(message, deal.get("image_url"))
        if success:
            mark_as_posted(posted, deal["asin"])
            save_posted(posted)
            new_deals_count += 1
            time.sleep(POST_INTERVAL_SECONDS)
        else:
            print("  Errore invio")

    total_today = len(posted.get(today, []))
    print("\nFatto! {} nuove. Totale oggi: {}".format(new_deals_count, total_today))


if __name__ == "__main__":
    main()
