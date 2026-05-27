"""
Sottocosto Oggi - Bot Telegram v19
Fix: no categorie consecutive uguali, filtro qualita rinforzato, keyword mirate.
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
MIN_PRICE = 15.0
MIN_RATING = 3.5
MIN_REVIEWS = 50
NO_RATING_MIN_PRICE = 30.0
FLASH_DEAL_PERCENT = 50
MAX_POSTS_PER_CYCLE = 3
POST_INTERVAL_SECONDS = 120

PUBLISH_START_HOUR = 7
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"

# Keyword mirate su prodotti di qualita conosciuta
KEYWORD_GROUPS = {
    "smartphone": [
        "iPhone offerta", "Samsung Galaxy offerta", "Google Pixel",
        "OnePlus smartphone", "Motorola smartphone", "Xiaomi 14",
    ],
    "audio": [
        "Sony cuffie wireless", "Bose cuffie", "JBL speaker bluetooth",
        "Sennheiser cuffie", "Marshall speaker", "Jabra auricolari",
        "AirPods", "Galaxy Buds", "Beats cuffie",
    ],
    "computer": [
        "Lenovo laptop offerta", "HP laptop offerta", "ASUS laptop",
        "Dell monitor", "Samsung monitor", "Logitech mouse",
        "Corsair tastiera", "Samsung SSD", "Crucial SSD NVMe",
    ],
    "smart_home": [
        "Echo Dot Alexa", "Google Nest", "Philips Hue",
        "Ring videocitofono", "TP-Link smart", "Eufy videocamera",
        "iRobot Roomba", "Roborock aspirapolvere", "Dyson aspirapolvere",
    ],
    "wearable": [
        "Apple Watch", "Samsung Galaxy Watch", "Garmin smartwatch",
        "Fitbit", "Amazfit smartwatch",
    ],
    "gaming": [
        "PlayStation 5 offerta", "Nintendo Switch gioco",
        "Xbox controller", "SteelSeries cuffie gaming",
        "Razer mouse gaming", "Logitech gaming",
    ],
    "foto_video": [
        "GoPro offerta", "DJI drone", "Canon fotocamera",
        "Sony fotocamera", "Fujifilm instax",
    ],
    "casa_tech": [
        "De'Longhi macchina caffe", "Nespresso offerta",
        "Ninja friggitrice aria", "Kenwood robot cucina",
        "Philips friggitrice", "Bosch elettrodomestico",
    ],
    "accessori": [
        "Anker power bank", "Anker caricatore USB-C",
        "Belkin caricatore wireless", "Samsung caricatore",
        "Apple caricatore", "Ugreen hub USB-C",
    ],
    "tablet": [
        "iPad offerta", "Samsung Galaxy Tab", "Kindle Paperwhite",
        "Fire HD tablet", "Lenovo tablet",
    ],
    "networking": [
        "Fritz!Box router", "TP-Link router WiFi 6",
        "Netgear mesh WiFi", "Eero mesh",
    ],
    "stampa_3d": [
        "Creality stampante 3D", "Bambu Lab", "Elegoo stampante 3D",
        "Anycubic", "Filamento PLA 1.75",
    ],
    "tv": [
        "LG TV OLED offerta", "Samsung TV 4K",
        "Fire TV Stick", "Chromecast Google",
        "Sony TV offerta", "Hisense TV",
    ],
    "cura_persona": [
        "Philips rasoio elettrico", "Braun regolabarba",
        "Oral-B spazzolino elettrico", "Dyson asciugacapelli",
        "Braun epilatore",
    ],
}

# Parole nel titolo che indicano prodotto scadente
TITLE_BLACKLIST = [
    "generico", "no brand", "senza marca", "unbranded",
    "lotto di", "set 100 pezzi", "bulk", "all'ingrosso",
    "2 in 1 economico", "multiuso economico",
    # Termini che indicano cloni/copie
    "stile", "tipo", "simile a", "ispirato",
    # Qualita bassa
    "usa e getta",
]

# Brand cinesi di bassissima qualita da evitare
BRAND_BLACKLIST = [
    "dmoao", "timu", "yestel", "teclast", "oscal",
    "oukitel", "blackview", "umidigi", "cubot", "doogee",
    "ulefone", "hotwav", "fossibot", "rugged king",
    "kalinco", "tozo", "qhot", "veatool",
]

FOOTER_PHRASES = [
    "Solo tech di qualita'", "Offerte tech verificate",
    "Tech al miglior prezzo", "Scelti per te",
    "Prezzi al minimo", "Affari tech imperdibili",
    "Il meglio della tech", "Qualita' garantita",
]

GOOD_MORNING = [
    "\u2600\ufe0f <b>Buongiorno tech lovers!</b>\n\nOggi monitoriamo offerte sui migliori brand tech.\n\n\U0001f514 Pubblichiamo appena troviamo uno sconto vero!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b>\n\nSconti tech in arrivo. Solo prodotti di qualita'.\n\n\U0001f6a8 Stay tuned!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\U0001f31e <b>Buongiorno!</b>\n\nNuova giornata di offerte tech su Amazon.\n\nApple, Samsung, Sony, Dyson e molto altro...\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]


def log(msg):
    print(msg, flush=True)


def get_italy_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    return get_italy_now().hour >= PUBLISH_START_HOUR


def select_keywords():
    selected = []
    for group_name, keywords in KEYWORD_GROUPS.items():
        n = min(len(keywords), random.randint(1, 3))
        selected.extend(random.sample(keywords, n))
    random.shuffle(selected)
    return selected


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


def is_spam(title):
    if len(title) > 400:
        return True
    if sum(1 for c in title if 0x4E00 < ord(c) < 0x9FFF) > 3:
        return True
    t = title.lower()
    if any(w in t for w in TITLE_BLACKLIST):
        return True
    if any(w in t for w in BRAND_BLACKLIST):
        return True
    return False


def get_deal_category(title):
    """Restituisce la categoria del deal per evitare consecutive uguali."""
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "wearable"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "cellulare"]): return "smartphone"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "laptop"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd"]): return "tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "fire tv", "oled"]): return "tv"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji"]): return "foto"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock"]): return "smarthome"
    if any(w in t for w in ["caffe", "nespresso", "friggitrice", "robot cucina"]): return "cucina"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming"]): return "gaming"
    if any(w in t for w in ["alexa", "echo", "nest", "hue", "ring"]): return "smarthome"
    if any(w in t for w in ["rasoio", "regolabarba", "spazzolino", "asciugacapelli"]): return "curapersona"
    if any(w in t for w in ["ssd", "hard disk", "microsd", "nvme"]): return "storage"
    if any(w in t for w in ["caricatore", "power bank", "cavo", "hub usb"]): return "accessori"
    if any(w in t for w in ["tastiera", "mouse", "webcam"]): return "periferiche"
    if any(w in t for w in ["router", "wifi", "mesh"]): return "networking"
    return "altro"


def diversify_deals(deals):
    """Riordina le offerte per evitare categorie consecutive uguali."""
    if len(deals) <= 1:
        return deals

    result = []
    remaining = list(deals)
    last_cat = None

    while remaining:
        found = False
        for i, d in enumerate(remaining):
            cat = get_deal_category(d["title"])
            if cat != last_cat or len(remaining) == 1:
                result.append(d)
                last_cat = cat
                remaining.pop(i)
                found = True
                break
        if not found:
            result.append(remaining.pop(0))
            last_cat = get_deal_category(result[-1]["title"])

    return result


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
        if not asin or not title or is_spam(title):
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

        # Filtro qualita
        if rating is not None:
            try:
                if float(rating) < MIN_RATING:
                    return None
            except (ValueError, TypeError):
                pass
        if review_count is not None:
            try:
                if int(review_count) < MIN_REVIEWS:
                    return None
            except (ValueError, TypeError):
                pass
        if rating is None and review_count is None and current_price < NO_RATING_MIN_PRICE:
            return None

        return {
            "asin": asin, "title": title,
            "current_price": current_price, "original_price": original_price,
            "discount": saving_amount, "discount_percent": discount_pct,
            "image_url": image_url, "rating": rating, "review_count": review_count,
            "has_deal": has_deal,
        }
    except Exception:
        return None


def get_category_emoji(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "\U0001f5a8"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "\U0001f3a7"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "\u231a"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "cellulare"]): return "\U0001f4f1"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "\U0001f4bb"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd"]): return "\U0001f4f2"
    if any(w in t for w in ["tv ", "television", "monitor", "fire tv", "oled"]): return "\U0001f4fa"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji"]): return "\U0001f4f7"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock", "dyson"]): return "\U0001f9f9"
    if any(w in t for w in ["caffe", "nespresso", "espresso"]): return "\u2615"
    if any(w in t for w in ["friggitrice", "robot cucina", "mixer"]): return "\U0001f373"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming"]): return "\U0001f3ae"
    if any(w in t for w in ["alexa", "echo", "nest", "hue", "ring"]): return "\U0001f3e0"
    if any(w in t for w in ["rasoio", "regolabarba", "spazzolino", "asciugacapelli"]): return "\U0001f488"
    if any(w in t for w in ["ssd", "hard disk", "microsd", "nvme"]): return "\U0001f4be"
    if any(w in t for w in ["caricatore", "power bank", "cavo usb", "hub usb"]): return "\U0001f50b"
    if any(w in t for w in ["tastiera", "mouse", "webcam"]): return "\u2328"
    if any(w in t for w in ["router", "wifi", "mesh"]): return "\U0001f4e1"
    if any(w in t for w in ["proiettore"]): return "\U0001f4fd"
    return "\U0001f4e6"


def get_category_hashtag(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "#stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "#audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "#wearable"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "cellulare"]): return "#smartphone"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "#laptop"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd"]): return "#tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "fire tv", "oled"]): return "#tv"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji"]): return "#foto"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock", "dyson"]): return "#smarthome"
    if any(w in t for w in ["caffe", "nespresso", "friggitrice", "robot cucina"]): return "#cucina"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming"]): return "#gaming"
    if any(w in t for w in ["alexa", "echo", "nest", "hue", "ring"]): return "#smarthome"
    if any(w in t for w in ["rasoio", "regolabarba", "spazzolino", "asciugacapelli"]): return "#curapersona"
    if any(w in t for w in ["ssd", "hard disk", "microsd", "nvme"]): return "#storage"
    if any(w in t for w in ["caricatore", "power bank", "cavo", "hub usb"]): return "#accessori"
    if any(w in t for w in ["tastiera", "mouse", "webcam"]): return "#periferiche"
    if any(w in t for w in ["router", "wifi", "mesh"]): return "#networking"
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
        requests.utils.quote("Offerta tech su @sottocosto_oggi!"))
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
    cat_emoji = get_category_emoji(title)
    cat_tag = get_category_hashtag(title)
    aff = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean = "https://www.amazon.it/dp/{}".format(asin)

    if special == "top":
        msg = "\U0001f3c6 <b>MIGLIOR OFFERTA TECH DI OGGI</b> \U0001f3c6\n\n"
        ftag = "#offertadelgiorno"
        ftxt = "Il top di oggi!"
    elif special == "flash" or deal.get("has_deal"):
        msg = "\u26a1 <b>OFFERTA LAMPO -{pct}%</b> \u26a1\n<i>A tempo! Potrebbe finire presto.</i>\n\n".format(pct=pct)
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
    msg += "{} #amazon #sconto{} {}\n".format(ftag, pct, cat_tag)
    msg += "\u26a0\ufe0f <i>Prezzo soggetto a variazioni</i>"
    return msg


def send_good_morning():
    send_telegram(random.choice(GOOD_MORNING))
    log("Buongiorno!")

def send_prime_promo(tag):
    msgs = [
        "\U0001f4e6 <b>Amazon Prime \u2014 Prova gratuita 30 giorni</b>\n\nSpedizioni illimitate in 1 giorno, Prime Video con film e serie TV, Prime Music, foto illimitate e accesso anticipato alle Offerte Lampo.\n\nGratis per 30 giorni. Cancelli quando vuoi, senza impegno.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={tag}\">Attiva la prova gratuita</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(tag=tag),
        "\U0001f69a <b>Consegne gratuite in 1 giorno con Amazon Prime</b>\n\nPrime Video, Prime Music, foto illimitate e 30 minuti di anticipo sulle Offerte Lampo. Tutto incluso.\n\nProva 30 giorni, gratis. Nessun vincolo.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={tag}\">Prova Prime gratis</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(tag=tag),
    ]
    send_telegram(random.choice(msgs))
    log("Promo Prime!")

def send_music_promo(tag):
    msgs = [
        "\U0001f3b5 <b>Amazon Music Unlimited \u2014 30 giorni gratis</b>\n\n90 milioni di brani in alta qualita', senza pubblicita'. Scarica offline, ascolta ovunque.\n\nGratis per 30 giorni. Poi 9,99\u20ac/mese, cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/gp/dmusic/promotions/AmazonMusicUnlimited?tag={tag}\">Prova Music Unlimited</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(tag=tag),
        "\U0001f3a7 <b>90 milioni di brani, zero pubblicita'</b>\n\nAmazon Music Unlimited: musica illimitata in HD, download offline, compatibile con Alexa.\n\n30 giorni di prova gratuita. Poi 9,99\u20ac/mese, cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/gp/dmusic/promotions/AmazonMusicUnlimited?tag={tag}\">Prova gratis</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(tag=tag),
    ]
    send_telegram(random.choice(msgs))
    log("Promo Music!")

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
    msg += "Oggi: <b>{}</b> offerte tech!\n\n\U0001f514 Domani nuovi sconti!\n\U0001f4f2 <b>@sottocosto_oggi</b>".format(len(deals))
    send_telegram(msg)
    log("Recap!")

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
    msg += "\U0001f525 {} offerte pubblicate\n\U0001f4b0 Sconto medio: {}%\n".format(len(all_d), avg)
    msg += "\U0001f3c6 Best: {} (-{}%)\n\n".format(best["title"][:50], best["discount_percent"])
    msg += "Buona settimana! \U0001f680\n\U0001f4e3 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Stats!")


def load_stats():
    if STATS_FILE.exists():
        try: return json.loads(STATS_FILE.read_text())
        except: return {}
    return {}

def save_deal_stat(deal):
    stats = load_stats()
    today = datetime.date.today().isoformat()
    if today not in stats: stats[today] = []
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
        except: return {}
    return {}

def save_posted(posted): POSTED_FILE.write_text(json.dumps(posted))

def is_posted(posted, key):
    today = datetime.date.today().isoformat()
    return key in posted.get(today, [])

def mark_posted(posted, key):
    today = datetime.date.today().isoformat()
    if today not in posted: posted[today] = []
    if key not in posted[today]: posted[today].append(key)

def count_deals(posted):
    today = datetime.date.today().isoformat()
    return len([k for k in posted.get(today, []) if not k.startswith("_")])


def main():
    now = get_italy_now()
    hour = now.hour
    today = datetime.date.today().isoformat()
    weekday = now.weekday()

    log("=== Bot v19 | {} | IT: {} ===".format(datetime.datetime.now().isoformat(), now.strftime("%H:%M")))

    if not is_publish_time():
        log("Fuori orario. Stop.")
        return

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
        "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"] if not os.environ.get(v)]
    if missing:
        log("Mancano: {}".format(missing))
        return

    posted = load_posted()
    log("Oggi: {}".format(count_deals(posted)))

    # Buongiorno
    if hour == 7 and not is_posted(posted, "_morning"):
        send_good_morning()
        mark_posted(posted, "_morning")
        save_posted(posted)
        time.sleep(5)

    # Stats settimanali
    if weekday == 0 and hour == 9 and not is_posted(posted, "_weekly"):
        send_weekly_stats()
        mark_posted(posted, "_weekly")
        save_posted(posted)
        time.sleep(5)

    # Promo Prime
    if hour == 12 and not is_posted(posted, "_prime"):
        send_prime_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_prime")
        save_posted(posted)
        time.sleep(5)

    # Promo Music
    if hour == 20 and not is_posted(posted, "_music"):
        send_music_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_music")
        save_posted(posted)
        time.sleep(5)

    # Recap serale
    if hour == 23 and not is_posted(posted, "_recap"):
        send_evening_recap(today)
        mark_posted(posted, "_recap")
        save_posted(posted)
        return

    # Cerca offerte
    api = create_api()
    keywords = select_keywords()
    log("Keywords: {}".format(len(keywords)))

    all_deals = []
    seen = set(posted.get(today, []))

    for kw in keywords:
        deals = search_deals(api, kw)
        for d in deals:
            if d["asin"] in seen or len(all_deals) >= MAX_POSTS_PER_CYCLE * 5:
                continue
            seen.add(d["asin"])
            d["_kw"] = kw
            all_deals.append(d)

    log("Trovate: {}".format(len(all_deals)))
    if not all_deals:
        log("Nessuna. Fine.")
        return

    # Ordina per sconto, poi diversifica categorie
    all_deals.sort(key=lambda d: (d.get("has_deal", False), d["discount_percent"]), reverse=True)
    all_deals = diversify_deals(all_deals)

    # Top del giorno
    if hour >= 9 and not is_posted(posted, "_top"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        log("TOP: {}... (-{}%)".format(best["title"][:40], best["discount_percent"]))
        msg = format_deal(best, special="top")
        btn = make_share_button(best["asin"])
        if send_telegram(msg, best.get("image_url"), btn):
            mark_posted(posted, best["asin"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            time.sleep(POST_INTERVAL_SECONDS)

    # Pubblica (max 3 per ciclo, categorie diverse)
    published = 0
    for d in all_deals:
        if published >= MAX_POSTS_PER_CYCLE or not is_publish_time() or is_posted(posted, d["asin"]):
            continue
        dn = count_deals(posted) + 1
        special = "flash" if d.get("has_deal") or d["discount_percent"] >= FLASH_DEAL_PERCENT else None
        cat = get_deal_category(d["title"])
        log("#{} [{}]: {}... (-{}%){}".format(dn, cat, d["title"][:35], d["discount_percent"],
            " [DEAL]" if special else ""))
        msg = format_deal(d, dn, special=special)
        btn = make_share_button(d["asin"])
        if send_telegram(msg, d.get("image_url"), btn):
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            published += 1
            time.sleep(POST_INTERVAL_SECONDS)

    log("=== Oggi: {} ===".format(count_deals(posted)))


if __name__ == "__main__":
    main()
