"""
Sottocosto Oggi - Bot Telegram v16 TECH VERTICAL
Solo offerte tech di marchi riconosciuti. Pubblica appena trova offerte nuove.
Monitora Offerte del Giorno e Offerte Lampo Amazon.
"""

import os
import json
import datetime
import time
import random
import re
import requests
from pathlib import Path

from amazon_creatorsapi import AmazonCreatorsApi, Country
from amazon_creatorsapi.models import Condition

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "15"))
MIN_PRICE = 10.0
MAX_POSTS_PER_CYCLE = 8
POST_INTERVAL_SECONDS = 30

PUBLISH_START_HOUR = 7
PUBLISH_END_HOUR = 23
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"

# Brand tech riconosciuti (minuscolo per confronto)
APPROVED_BRANDS = [
    # Smartphone / Telefonia
    "apple", "samsung", "google", "oneplus", "motorola", "xiaomi", "oppo", "realme", "huawei", "honor", "nothing",
    # Audio
    "sony", "bose", "jbl", "sennheiser", "marshall", "bang & olufsen", "beats", "jabra", "anker", "soundcore",
    "harman kardon", "denon", "audio-technica", "shure",
    # Computer / Laptop
    "lenovo", "hp", "dell", "asus", "acer", "msi", "microsoft surface", "razer",
    # Tablet
    "ipad", "galaxy tab", "fire hd", "kindle",
    # TV / Monitor
    "lg", "philips", "hisense", "tcl", "benq", "dell monitor", "asus monitor",
    # Gaming
    "playstation", "xbox", "nintendo", "steelseries", "logitech", "corsair", "hyperx", "trust",
    # Smart Home
    "amazon echo", "alexa", "google nest", "philips hue", "ring", "blink", "tp-link", "eufy",
    "arlo", "meross", "tado", "netatmo", "shelly",
    # Casa Tech / Elettrodomestici
    "dyson", "irobot", "roomba", "ecovacs", "roborock", "dreame", "tineco",
    "de'longhi", "delonghi", "nespresso", "krups", "kenwood", "moulinex", "braun",
    "ninja", "instant pot", "weber", "bosch",
    # Wearable
    "apple watch", "galaxy watch", "garmin", "fitbit", "amazfit", "polar", "suunto",
    # Foto / Video
    "canon", "nikon", "gopro", "dji", "insta360", "fujifilm",
    # Storage / Accessori
    "sandisk", "western digital", "seagate", "crucial", "kingston",
    "belkin", "ugreen", "spigen", "anker",
    # Stampa / 3D
    "creality", "bambu lab", "elegoo", "anycubic", "prusa", "brother", "epson",
    # Networking
    "fritz!box", "fritzbox", "netgear", "linksys", "ubiquiti",
]

# Keyword di ricerca focalizzate su tech
SEARCH_KEYWORDS = [
    "Apple offerta",
    "Samsung Galaxy offerta",
    "Sony cuffie",
    "Bose cuffie",
    "JBL speaker",
    "Dyson aspirapolvere",
    "iRobot Roomba",
    "Ecovacs robot",
    "PlayStation 5",
    "Nintendo Switch",
    "Xbox controller",
    "Garmin smartwatch",
    "Apple Watch",
    "Samsung Galaxy Watch",
    "GoPro",
    "DJI drone",
    "Philips Hue",
    "Amazon Echo",
    "Logitech gaming",
    "Razer gaming",
    "SanDisk SSD",
    "Anker caricatore",
    "De'Longhi caffe",
    "Nespresso",
    "Lenovo laptop",
    "ASUS laptop",
    "LG TV",
    "Samsung TV",
    "Creality stampante 3D",
    "Canon fotocamera",
    "Braun rasoio",
    "Kindle Paperwhite",
    "Fire TV Stick",
    "Ring videocitofono",
    "Roborock aspirapolvere",
    "Corsair tastiera",
    "Google Nest",
    "TP-Link smart",
]

FOOTER_PHRASES = [
    "Solo marchi top",
    "Tech al miglior prezzo",
    "Offerte tech verificate",
    "Brand che contano",
    "Scelti per te",
    "Solo il meglio della tech",
    "Qualita' garantita",
    "Top brand, prezzi mini",
]

GOOD_MORNING = [
    "\u2600\ufe0f <b>Buongiorno tech lovers!</b>\n\nOggi monitoriamo le offerte dei migliori brand: Apple, Samsung, Sony, Dyson, Bose e molti altri.\n\n\U0001f514 Pubblichiamo appena troviamo uno sconto vero!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b>\n\nLe offerte tech di oggi stanno arrivando. Solo marchi top, zero cinesate.\n\n\U0001f6a8 Stay tuned!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\U0001f31e <b>Buongiorno!</b>\n\nNuova giornata, nuovi sconti sui migliori brand tech.\n\nSony, Apple, Samsung, Dyson... vediamo cosa ci riserva Amazon oggi!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]


def log(msg):
    print(msg, flush=True)


def get_italy_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    h = get_italy_now().hour
    return PUBLISH_START_HOUR <= h <= PUBLISH_END_HOUR


def is_approved_brand(title):
    t = title.lower()
    for brand in APPROVED_BRANDS:
        if brand in t:
            return True
    return False


def clean_title(title):
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'[,/|]\s*(?:compatibile con|adatto per|per)\s+[\w\s/,]+$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\([^)]*compatib[^)]*\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\[[^\]]*\]', '', title)
    if len(title) > 120:
        cuts = [title.find(c, 70) for c in [', ', ' - ', '. ', ' | ']]
        cuts = [p for p in cuts if 70 < p < 150]
        if cuts:
            title = title[:min(cuts)]
    return title.strip().rstrip(',').rstrip('-').strip()[:200]


def is_spam_title(title):
    if len(title) > 400:
        return True
    if sum(1 for c in title if 0x4E00 < ord(c) < 0x9FFF) > 3:
        return True
    if any(w in title.lower() for w in ["clicca qui", "compra ora", "gratis 100%", "buy now"]):
        return True
    return False


def select_keywords():
    n = min(len(SEARCH_KEYWORDS), random.randint(8, 15))
    return random.sample(SEARCH_KEYWORDS, n)


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
        log("[ERR] {}: {}".format(keyword, e))
        return []
    if not results or not results.items:
        return []
    deals = []
    for item in results.items:
        deal = parse_item(item)
        if deal:
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
        has_deal = False

        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass
        if not asin or not title or is_spam_title(title):
            return None

        # Filtro brand: solo marchi approvati
        if not is_approved_brand(title):
            return None

        title = clean_title(title)

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
            # Check se ha un deal attivo (Offerta del Giorno, Lightning, ecc.)
            if hasattr(listing, 'deal_details') and listing.deal_details:
                has_deal = True
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
            "has_deal": has_deal,
        }
    except Exception:
        return None


def get_brand_from_title(title):
    t = title.lower()
    for brand in APPROVED_BRANDS:
        if brand in t:
            return brand.title()
    return ""


def get_category_emoji(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "\U0001f5a8"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "\U0001f3a7"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes", "garmin", "fitbit"]): return "\u231a"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "oneplus"]): return "\U0001f4f1"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil", "chromebook"]): return "\U0001f4bb"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd"]): return "\U0001f4f2"
    if any(w in t for w in ["tv ", "television", "monitor", "fire tv", "oled", "qled"]): return "\U0001f4fa"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji", "reflex"]): return "\U0001f4f7"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock", "dreame", "dyson", "tineco"]): return "\U0001f9f9"
    if any(w in t for w in ["caffe", "nespresso", "delonghi", "krups", "macchina caff"]): return "\u2615"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "switch", "gaming", "controller"]): return "\U0001f3ae"
    if any(w in t for w in ["alexa", "echo", "nest", "smart home", "hue", "ring", "blink"]): return "\U0001f3e0"
    if any(w in t for w in ["rasoio", "regolabarba", "piastra", "asciugacapelli", "braun"]): return "\U0001f488"
    if any(w in t for w in ["ssd", "hard disk", "microsd", "sandisk", "memoria"]): return "\U0001f4be"
    if any(w in t for w in ["caricatore", "power bank", "cavo", "usb", "anker", "belkin"]): return "\U0001f50b"
    if any(w in t for w in ["tastiera", "mouse", "webcam", "logitech", "corsair"]): return "\u2328"
    if any(w in t for w in ["router", "wifi", "fritz", "mesh", "ripetitor"]): return "\U0001f4e1"
    return "\U0001f4e6"


def get_category_hashtag(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "#stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "#audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "garmin", "fitbit"]): return "#wearable"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "oneplus"]): return "#smartphone"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "#laptop"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd"]): return "#tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "oled", "qled"]): return "#tv"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji"]): return "#foto"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock", "dreame", "dyson"]): return "#smartHome"
    if any(w in t for w in ["caffe", "nespresso", "delonghi"]): return "#casa"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming"]): return "#gaming"
    if any(w in t for w in ["alexa", "echo", "nest", "hue", "ring", "blink"]): return "#smartHome"
    if any(w in t for w in ["ssd", "hard disk", "microsd", "sandisk"]): return "#storage"
    if any(w in t for w in ["caricatore", "power bank", "anker", "belkin"]): return "#accessori"
    if any(w in t for w in ["tastiera", "mouse", "logitech", "corsair"]): return "#periferiche"
    if any(w in t for w in ["router", "wifi", "fritz", "mesh"]): return "#networking"
    return "#tech"


def send_telegram(text, image_url=None, reply_markup=None):
    base_url = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
    try:
        if image_url:
            payload = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text, "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            resp = requests.post("{}/sendPhoto".format(base_url), json=payload, timeout=15)
            if resp.json().get("ok"):
                return True
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post("{}/sendMessage".format(base_url), json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        log("[TG] Errore: {}".format(e))
        return False


def make_share_button(asin):
    url = "https://t.me/share/url?url={}&text={}".format(
        requests.utils.quote("https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)),
        requests.utils.quote("Guarda questa offerta tech su @sottocosto_oggi!"))
    return {"inline_keyboard": [[{"text": "\U0001f4e4 Condividi", "url": url}]]}


def fmt_stars(rating, review_count):
    try:
        r = float(rating)
        return "{}{} {}/5{}".format("\u2B50" * int(r), "\u2606" * (5 - int(r)), rating,
            " ({} recensioni)".format(review_count) if review_count else "")
    except (ValueError, TypeError):
        return ""


def fmt_saving(saving):
    if saving >= 100:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f4a5\n\n".format(saving)
    if saving >= 50:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f525\n\n".format(saving)
    return "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(saving)


def format_deal(deal, deal_number=0, special=None):
    pct = deal["discount_percent"]
    asin = deal["asin"]
    title = deal["title"]
    brand = get_brand_from_title(title)
    cat_emoji = get_category_emoji(title)
    cat_tag = get_category_hashtag(title)
    aff = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean = "https://www.amazon.it/dp/{}".format(asin)
    brand_tag = "#{}".format(brand.lower().replace(" ", "").replace("'", "").replace("&", "")) if brand else ""

    if special == "top":
        msg = "\U0001f3c6 <b>MIGLIOR OFFERTA TECH DI OGGI</b> \U0001f3c6\n\n"
        ftag = "#offertadelgiorno"
        ftxt = "Il top di oggi!"
    elif special == "flash" or deal.get("has_deal"):
        msg = "\u26a1 <b>OFFERTA LAMPO -{pct}%</b> \u26a1\n<i>Offerta a tempo! Potrebbe finire presto.</i>\n\n".format(pct=pct)
        ftag = "#offertalampo"
        ftxt = "Corri!"
    else:
        alert = "\U0001f6a8" * (3 if pct >= 50 else 2 if pct >= 30 else 1)
        msg = "{} <b>SCONTO -{}%</b> {}\n\n".format(alert, pct, alert)
        ftag = "#offerta"
        ftxt = random.choice(FOOTER_PHRASES)

    msg += "{} <b>{}</b>\n\n".format(cat_emoji, title)
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(deal["original_price"], deal["current_price"])
    msg += fmt_saving(deal["discount"])

    if deal.get("rating"):
        s = fmt_stars(deal["rating"], deal.get("review_count"))
        if s:
            msg += "{}\n\n".format(s)

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(aff)
    msg += "{}\n\n".format(clean)
    msg += "\u2501" * 15 + "\n"
    if deal_number > 0:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerta #{}\n".format(deal_number)
    else:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 {}\n".format(ftxt)
    msg += "{} #amazon #sconto{} {} {}".format(ftag, pct, cat_tag, brand_tag).strip()
    msg += "\n\u26a0\ufe0f <i>Prezzo soggetto a variazioni</i>"
    return msg


def send_good_morning():
    send_telegram(random.choice(GOOD_MORNING))
    log("Buongiorno inviato!")


def send_evening_recap(today):
    stats = load_stats()
    deals = stats.get(today, [])
    if not deals:
        return
    top3 = sorted(deals, key=lambda d: d["discount_percent"], reverse=True)[:3]
    msg = "\U0001f319 <b>TOP 3 offerte tech di oggi</b>\n\n"
    for i, d in enumerate(top3):
        e = get_category_emoji(d["title"])
        link = "https://www.amazon.it/dp/{}?tag={}".format(d["asin"], AMAZON_PARTNER_TAG)
        msg += "{}. {} <a href=\"{}\">{}</a>\n   <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b> (-{}%)\n\n".format(
            i+1, e, link, d["title"][:60], d["original_price"], d["current_price"], d["discount_percent"])
    msg += "Oggi: <b>{}</b> offerte tech pubblicate!\n\n".format(len(deals))
    msg += "\U0001f514 Domani nuovi sconti dai migliori brand!\n\U0001f4f2 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Recap serale!")


def send_weekly_stats():
    stats = load_stats()
    if not stats:
        return
    all_d = [d for deals in stats.values() for d in deals]
    if not all_d:
        return
    avg = round(sum(d["discount_percent"] for d in all_d) / len(all_d))
    best = max(all_d, key=lambda d: d["discount_percent"])
    msg = "\U0001f4ca <b>Settimana tech in numeri</b>\n\n"
    msg += "\U0001f525 {} offerte brand verificate\n".format(len(all_d))
    msg += "\U0001f4b0 Sconto medio: {}%\n".format(avg)
    msg += "\U0001f3c6 Best deal: {} (-{}%)\n\n".format(best["title"][:50], best["discount_percent"])
    msg += "Buona settimana! \U0001f680\n\U0001f4e3 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Stats settimanali!")


def load_stats():
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except:
            return {}
    return {}


def save_deal_stat(deal):
    stats = load_stats()
    today = datetime.date.today().isoformat()
    if today not in stats:
        stats[today] = []
    stats[today].append({"asin": deal["asin"], "title": deal["title"],
        "current_price": deal["current_price"], "original_price": deal["original_price"],
        "discount_percent": deal["discount_percent"]})
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    stats = {k: v for k, v in stats.items() if k >= week_ago}
    STATS_FILE.write_text(json.dumps(stats))


def load_posted():
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text())
            if isinstance(data, dict):
                today = datetime.date.today().isoformat()
                return {k: v for k, v in data.items() if k == today}
            return {}
        except:
            return {}
    return {}


def save_posted(posted):
    POSTED_FILE.write_text(json.dumps(posted))


def is_posted(posted, key):
    today = datetime.date.today().isoformat()
    return key in posted.get(today, [])


def mark_posted(posted, key):
    today = datetime.date.today().isoformat()
    if today not in posted:
        posted[today] = []
    if key not in posted[today]:
        posted[today].append(key)


def count_deals(posted):
    today = datetime.date.today().isoformat()
    return len([k for k in posted.get(today, []) if not k.startswith("_")])


def main():
    now = get_italy_now()
    hour = now.hour
    today = datetime.date.today().isoformat()
    weekday = now.weekday()

    log("=== Bot v16 TECH | {} | IT: {} ===".format(datetime.datetime.now().isoformat(), now.strftime("%H:%M")))

    if not is_publish_time():
        log("Fuori orario. Stop.")
        return

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
        "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"] if not os.environ.get(v)]
    if missing:
        log("Mancano: {}".format(missing))
        return

    posted = load_posted()
    log("Oggi: {} offerte".format(count_deals(posted)))

    # Buongiorno (7:00-7:59)
    if hour == 7 and not is_posted(posted, "_morning"):
        send_good_morning()
        mark_posted(posted, "_morning")
        save_posted(posted)
        time.sleep(5)

    # Stats settimanali (lunedi 9:00-9:59)
    if weekday == 0 and hour == 9 and not is_posted(posted, "_weekly"):
        send_weekly_stats()
        mark_posted(posted, "_weekly")
        save_posted(posted)
        time.sleep(5)

    # Recap serale (23:00-23:59)
    if hour == 23 and not is_posted(posted, "_recap"):
        send_evening_recap(today)
        mark_posted(posted, "_recap")
        save_posted(posted)
        return

    # Cerca offerte tech
    api = create_api()
    keywords = select_keywords()
    log("Cerco in {} keyword...".format(len(keywords)))

    all_deals = []
    seen = set(posted.get(today, []))

    for kw in keywords:
        deals = search_deals(api, kw)
        for d in deals:
            if d["asin"] in seen:
                continue
            if len(all_deals) >= MAX_POSTS_PER_CYCLE * 3:
                break
            seen.add(d["asin"])
            d["_kw"] = kw
            all_deals.append(d)

    log("Trovate: {} offerte brand".format(len(all_deals)))
    if not all_deals:
        log("Nessuna nuova. Fine.")
        return

    # Ordina: deal attivi prima, poi per sconto
    all_deals.sort(key=lambda d: (d.get("has_deal", False), d["discount_percent"]), reverse=True)

    # Offerta del giorno (9+)
    if hour >= 9 and not is_posted(posted, "_top"):
        best = all_deals[0]
        log("TOP: {}... (-{}%)".format(best["title"][:40], best["discount_percent"]))
        msg = format_deal(best, special="top")
        btn = make_share_button(best["asin"])
        if send_telegram(msg, best.get("image_url"), btn):
            mark_posted(posted, best["asin"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals = all_deals[1:]
            time.sleep(POST_INTERVAL_SECONDS)

    # Pubblica le restanti (max per ciclo)
    published = 0
    for d in all_deals:
        if published >= MAX_POSTS_PER_CYCLE:
            break
        if not is_publish_time() or is_posted(posted, d["asin"]):
            continue

        dn = count_deals(posted) + 1
        special = "flash" if d.get("has_deal") else None
        log("#{}: {}... (-{}%){}".format(dn, d["title"][:40], d["discount_percent"],
            " [DEAL]" if d.get("has_deal") else ""))

        msg = format_deal(d, dn, special=special)
        btn = make_share_button(d["asin"])
        if send_telegram(msg, d.get("image_url"), btn):
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            published += 1
            time.sleep(POST_INTERVAL_SECONDS)

    log("=== Fine. Oggi: {} offerte ===".format(count_deals(posted)))


if __name__ == "__main__":
    main()
