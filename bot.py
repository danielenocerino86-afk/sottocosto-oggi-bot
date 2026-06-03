"""
Sottocosto Oggi - Bot v26 EDITORIAL
- Modalità diagnostica: log dettagliato di ogni decisione
- Regole editoriali: priorità categorie casa/cucina, moda, sport, bellezza, elettronica
- Anti-loop: auto-pulisce memoria se troppo piena
- Filtri di qualità per marchi noti
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

BOT_VERSION = "v26-EDITORIAL"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

# ========== CONFIG ==========
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "10"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 9.0           # piu' permissivo
MIN_RATING = 3.5
MIN_REVIEWS = 25          # ridotto da 30
NO_RATING_MIN_PRICE = 20.0
MAX_POSTS_PER_CYCLE = 5
MAX_DEALS_POOL = 200      # aumentato per piu' scelta
POST_INTERVAL_SECONDS = 90

PUBLISH_START_HOUR = 7
PUBLISH_END_HOUR = 23
TIMEZONE_OFFSET = 2

# Anti-loop: se memoria > N, resetta (probabile bug)
MAX_MEMORY_SIZE = 500

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"


def log(msg):
    print(msg, flush=True)


# ============================================================
# REGOLE EDITORIALI
# ============================================================

# PRIORITA' categorie (in ordine come da richiesta editoriale)
CATEGORY_PRIORITY = {
    'casa_cucina': 1,     # MASSIMA priorita'
    'cucina': 1,
    'casaarredo': 1,
    'moda': 2,
    'abbigliamento': 2,
    'scarpe': 2,
    'borse': 2,
    'gioielli': 2,
    'sport': 3,
    'bellezza': 4,
    'curapersona': 4,
    'audio': 5,           # elettronica
    'smartphone': 5,
    'tablet': 5,
    'tv': 5,
    'wearable': 5,
    'laptop': 5,
    'gaming': 5,
    'foto': 5,
    'smarthome': 5,
    'accessori': 6,
    'altro': 9,
}

# MARCHI NOTI - quelli con priorita' alta
TRUSTED_BRANDS = {
    'top': ['Apple', 'Samsung', 'Sony', 'Bose', 'Dyson', 'Philips', 'Bosch',
            'LEGO', 'Levi\'s', 'Nike', 'Adidas', 'Ray-Ban', 'Garmin',
            'L\'Oreal', 'Estée Lauder', 'Chanel', 'Dior', 'Kerastase',
            'KitchenAid', 'De\'Longhi', 'Nespresso', 'Tefal', 'Le Creuset',
            'iRobot', 'Roomba', 'Roborock'],
    'good': ['Xiaomi', 'JBL', 'Logitech', 'Anker', 'Kindle', 'Echo',
             'Tommy Hilfiger', 'Calvin Klein', 'Puma', 'New Balance',
             'Maybelline', 'Clinique', 'Lancome', 'Pandora', 'Swarovski',
             'Ninja', 'Lavazza', 'Krups', 'WMF', 'Kenwood',
             'TP-Link', 'Netgear', 'Asus', 'HP', 'Lenovo', 'Dell',
             'GoPro', 'DJI', 'Canon', 'Fitbit', 'Amazfit'],
}


# ============================================================
# KEYWORD ORGANIZZATE PER PRIORITA' EDITORIALE
# ============================================================

# Priorita' 1: Deal attivi Amazon
DEAL_KEYWORDS = [
    "offerta del giorno", "offerta lampo",
    "deal today amazon", "offerte oggi",
    "sconto del giorno", "offerta limitata",
]

# Priorita' 2: CASA/CUCINA (categoria editoriale top)
HOUSE_KITCHEN_KEYWORDS = [
    "De'Longhi macchina caffe", "Nespresso offerta",
    "KitchenAid", "Kenwood robot cucina",
    "Ninja friggitrice aria", "Philips friggitrice",
    "Tefal padella", "Le Creuset",
    "WMF pentole", "Bialetti caffe",
    "Russell Hobbs", "Smeg piccoli elettrodomestici",
    "Joseph Joseph cucina", "Brabantia",
    "Tempur cuscino", "Emma materasso",
    "Lenzuola raso cotone", "Kärcher idropulitrice",
    "iRobot Roomba", "Roborock", "Dreame robot",
    "Dyson aspirapolvere", "Philips Hue",
]

# Priorita' 3: MODA
FASHION_KEYWORDS = [
    "Levi's jeans", "Tommy Hilfiger", "Calvin Klein",
    "Lacoste polo", "Ralph Lauren",
    "Nike scarpe", "Adidas scarpe", "Puma sneaker",
    "New Balance", "Birkenstock", "Geox scarpe",
    "Michael Kors borsa", "Furla", "Guess borsa",
    "Pandora gioielli", "Swarovski",
    "Ray-Ban occhiali", "Hugo Boss profumo",
    "Pinko", "Liu Jo",
]

# Priorita' 4: SPORT
SPORT_KEYWORDS = [
    "Nike running", "Adidas running",
    "ASICS running", "Brooks running",
    "Garmin GPS", "Theragun",
    "Decathlon", "Columbia outdoor",
    "The North Face", "Salomon",
]

# Priorita' 5: BELLEZZA
BEAUTY_KEYWORDS = [
    "L'Oreal Paris", "Maybelline", "NYX Professional",
    "Clinique", "Estee Lauder", "Lancome crema",
    "La Roche Posay", "Vichy", "Bioderma",
    "Kerastase", "L'Oreal Professionnel",
    "GHD piastra", "Dyson Airwrap",
    "Oral-B elettrico", "Philips Sonicare",
    "Chanel profumo", "Dior profumo",
    "Babyliss", "Remington",
]

# Priorita' 6: ELETTRONICA (qualita')
TECH_KEYWORDS = [
    "iPhone offerta", "Samsung Galaxy", "Apple Watch",
    "Sony cuffie", "Bose cuffie", "JBL speaker",
    "AirPods", "Galaxy Buds", "Beats",
    "Lenovo laptop", "HP laptop", "ASUS laptop",
    "iPad", "Samsung Galaxy Tab", "Kindle Paperwhite",
    "Echo Dot Alexa", "Fire TV Stick",
    "LG OLED", "Samsung QLED", "Sony Bravia",
    "PlayStation 5", "Nintendo Switch", "Xbox controller",
    "GoPro Hero", "DJI Mini",
    "Garmin smartwatch", "Fitbit", "Amazfit",
]

# Keyword fresh per ore serali
EVENING_KEYWORDS = [
    "best seller offerta", "piu venduti",
    "Top rated", "amazon choice",
    "prezzo minimo", "novita Amazon",
    "appena uscito", "scopri Amazon",
]

# Blacklist marchi scadenti / cinesi sconosciuti
BRAND_BLACKLIST = [
    "dmoao", "timu", "yestel", "teclast", "oscal", "oukitel",
    "blackview", "umidigi", "cubot", "doogee", "ulefone", "hotwav",
    "fossibot", "iiif150", "agm",
    "tozo", "qhot", "veatool", "donerton", "boltune",
    "obkz", "neclife", "fastsnail", "yiwentec",
    "topk", "iniu", "herilios", "lisen", "ailun", "wsky", "pikoy",
    "kalinco", "uliptz", "trongle", "syosin", "ainope",
    "redragon", "havit", "fantech", "rapoo", "vgn", "akko",
    "fokoos", "feeyar",
    "kospet", "amovee", "yatofyas", "binden",
    "ulanzi", "suaoki", "esonstyle",
    "outxe", "wopnt", "judee",
]

TITLE_BLACKLIST = [
    "generico", "no brand", "senza marca", "unbranded",
    "lotto di", "set 100 pezzi", "bulk", "all'ingrosso",
    "ispirato a", "stile", "usa e getta", "monouso",
]

TITLE_SUSPICIOUS = [
    "smartwatch chiamate", "smartwatch 1.85", "smartwatch 1.96",
    "drone professionale evitamento",
    "cuffie da gioco ps4 ps5",
]

GOOD_MORNING = [
    "\u2600\ufe0f <b>Buongiorno!</b>\n\nUna nuova giornata di offerte sta iniziando.\n\nTech, moda, casa, bellezza, sport, gaming... Tutto verificato.\n\n\U0001f514 Attiva le notifiche!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b>\n\nIl team \u00e8 al lavoro per trovarti le migliori offerte di oggi.\n\nProdotti di qualit\u00e0, sconti veri.\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]

FOOTER_PHRASES = [
    "Selezionate per te", "Solo offerte vere", "Sconti del giorno",
    "Affari verificati", "Il top di oggi",
]


# ============================================================
# UTILITY
# ============================================================

def get_italy_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    h = get_italy_now().hour
    return PUBLISH_START_HOUR <= h < PUBLISH_END_HOUR


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
    if any(w in t for w in TITLE_SUSPICIOUS):
        return True
    if re.search(r'\b1\.\d{2}\b.*\b1\.\d{2}\b', t):
        return True
    return False


def brand_priority(title):
    """Ritorna priorita' del brand: 0=trusted top, 1=trusted good, 2=unknown."""
    t = title.lower()
    for brand in TRUSTED_BRANDS['top']:
        if brand.lower() in t:
            return 0
    for brand in TRUSTED_BRANDS['good']:
        if brand.lower() in t:
            return 1
    return 2


def create_api():
    return AmazonCreatorsApi(
        credential_id=AMAZON_CREDENTIAL_ID,
        credential_secret=AMAZON_CREDENTIAL_SECRET,
        version="3.2", tag=AMAZON_PARTNER_TAG,
        country=Country.IT, throttling=1.0,
    )


def search_deals(api, keyword, max_results=10):
    try:
        results = api.search_items(
            keywords=keyword, item_count=max_results,
            condition=Condition.NEW,
            min_saving_percent=MIN_DISCOUNT_PERCENT,
        )
    except Exception as e:
        log("  [API_ERR] {}: {}".format(keyword, str(e)[:80]))
        return []
    if not results or not results.items:
        return []
    parsed = []
    for item in results.items:
        d = parse_item(item)
        if d:
            parsed.append(d)
    return parsed


def parse_item(item):
    try:
        asin = item.asin
        title = None
        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass
        if not asin or not title:
            return None
        if is_spam(title):
            return None
        title = clean_title(title)

        try:
            listing = item.offers_v2.listings[0]
            p = listing.price
            current = p.money.amount
            original = p.saving_basis.money.amount if p.saving_basis and p.saving_basis.money else None
            pct = p.savings.percentage if p.savings else None
            saving = p.savings.money.amount if p.savings and p.savings.money else None
            has_deal = bool(hasattr(listing, 'deal_details') and listing.deal_details)
        except (AttributeError, TypeError, IndexError):
            return None

        if not current or current < MIN_PRICE:
            return None
        if not original and pct and pct > 0:
            original = round(current / (1 - pct / 100), 2)
        if not pct and original and original > current:
            pct = round(((original - current) / original) * 100)
        if not original or original <= current:
            return None
        if not saving:
            saving = round(original - current, 2)
        if not pct or pct < MIN_DISCOUNT_PERCENT:
            return None

        img = None
        try:
            img = item.images.primary.large.url
        except (AttributeError, TypeError):
            pass

        rating = review_count = None
        try:
            if item.customer_reviews:
                if hasattr(item.customer_reviews, 'star_rating') and item.customer_reviews.star_rating:
                    rating = item.customer_reviews.star_rating.value
                if hasattr(item.customer_reviews, 'count') and item.customer_reviews.count:
                    review_count = item.customer_reviews.count
        except (AttributeError, TypeError):
            pass

        if rating:
            try:
                if float(rating) < MIN_RATING:
                    return None
            except (ValueError, TypeError):
                pass
        if review_count:
            try:
                if int(review_count) < MIN_REVIEWS:
                    return None
            except (ValueError, TypeError):
                pass
        if not rating and not review_count and current < NO_RATING_MIN_PRICE:
            return None

        return {
            "asin": asin, "title": title,
            "current_price": current, "original_price": original,
            "discount": saving, "discount_percent": pct,
            "image_url": img, "rating": rating, "review_count": review_count,
            "has_deal": has_deal,
            "brand_prio": brand_priority(title),
        }
    except Exception as e:
        log("  [PARSE_ERR] {}".format(str(e)[:80]))
        return None


def get_deal_category(title):
    t = title.lower()
    if any(w in t for w in ["caffe", "nespresso", "espresso", "friggitrice", "kitchenaid", "robot cucina", "pentole", "coltelli", "frullator", "impastatric", "tefal", "le creuset", "wmf"]): return "cucina"
    if any(w in t for w in ["aspira", "robot pulizia", "roomba", "roborock", "dreame", "dyson v", "kärcher", "karcher"]): return "casaarredo"
    if any(w in t for w in ["materass", "cuscin", "asciugamani", "copripiumino", "lenzuol", "piumino", "lampad", "candela", "tappeto", "phillips hue", "hue"]): return "casaarredo"
    if any(w in t for w in ["scarp", "sneaker", "stival", "ciabatt", "sandal", "birkenstock"]): return "scarpe"
    if any(w in t for w in ["jeans", "camicia", "magliett", "t-shirt", "felpa", "giacca", "pantalo", "vestit", "abito", "polo"]): return "abbigliamento"
    if any(w in t for w in ["borsa", "zaino", "trolley", "valigia"]): return "borse"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini", "pandora", "swarovski"]): return "gioielli"
    if any(w in t for w in ["profum", "trucco", "makeup", "cosmet", "siero", "shampoo", "crema viso", "crema corpo", "maschera", "palette", "rossetto"]): return "bellezza"
    if any(w in t for w in ["rasoio", "regolabarba", "spazzolino", "asciugacapelli", "piastra capelli", "ghd"]): return "curapersona"
    if any(w in t for w in ["running", "yoga", "palestra", "manubri", "bici", "tapis", "trekking", "borraccia"]): return "sport"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds", "airpods", "buds"]): return "audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes", "tracker", "garmin", "fitbit"]): return "wearable"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "cellulare"]): return "smartphone"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "laptop"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd", "ereader"]): return "tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "oled", "fire tv", "proiettor", "qled"]): return "tv"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji"]): return "foto"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming", "controller"]): return "gaming"
    if any(w in t for w in ["alexa", "echo", "nest", "ring videoc", "domotica", "tapo"]): return "smarthome"
    if any(w in t for w in ["lego", "barbie", "puzzle", "peluche", "passeggino", "seggiolino", "playmobil"]): return "bambini"
    if any(w in t for w in ["caricatore", "power bank", "cavo usb", "hub usb", "anker"]): return "accessori"
    return "altro"


def get_editorial_priority(deal):
    """Score editoriale: piu' basso = priorita' maggiore."""
    cat = get_deal_category(deal['title'])
    cat_prio = CATEGORY_PRIORITY.get(cat, 9)
    brand = deal.get('brand_prio', 2)
    # Componi: categoria (peso 10) + brand (peso 3) - has_deal (-5)
    score = cat_prio * 10 + brand * 3
    if deal.get('has_deal'):
        score -= 5
    if deal.get('_is_active_deal'):
        score -= 8
    # Bonus sconto alto
    if deal['discount_percent'] >= 50:
        score -= 5
    elif deal['discount_percent'] >= 30:
        score -= 3
    return score


def diversify_deals(deals):
    """Diversifica per categoria mantenendo l'ordine di priorita'."""
    if len(deals) <= 1:
        return deals
    result = []
    remaining = list(deals)
    last_cat = None
    while remaining:
        found = False
        for i, d in enumerate(remaining):
            cat = get_deal_category(d["title"])
            if cat != last_cat:
                result.append(d)
                last_cat = cat
                remaining.pop(i)
                found = True
                break
        if not found:
            result.append(remaining.pop(0))
            last_cat = get_deal_category(result[-1]["title"])
    return result


def get_category_emoji(title):
    cat = get_deal_category(title)
    emojis = {
        "cucina": "\U0001f373", "casaarredo": "\U0001f6cb",
        "scarpe": "\U0001f45f", "abbigliamento": "\U0001f455", "borse": "\U0001f45c",
        "gioielli": "\U0001f48d", "bellezza": "\U0001f484", "curapersona": "\U0001f488",
        "sport": "\U0001f3cb", "audio": "\U0001f3a7", "wearable": "\u231a",
        "smartphone": "\U0001f4f1", "laptop": "\U0001f4bb", "tablet": "\U0001f4f2",
        "tv": "\U0001f4fa", "foto": "\U0001f4f7", "gaming": "\U0001f3ae",
        "smarthome": "\U0001f3e0", "bambini": "\U0001f9f8",
        "accessori": "\U0001f50b",
        "altro": "\U0001f6cd",
    }
    return emojis.get(cat, "\U0001f4e6")


def get_category_hashtag(title):
    cat = get_deal_category(title)
    tags = {
        "cucina": "#cucina", "casaarredo": "#casa",
        "scarpe": "#scarpe", "abbigliamento": "#moda", "borse": "#borse",
        "gioielli": "#gioielli", "bellezza": "#bellezza", "curapersona": "#curapersona",
        "sport": "#sport", "audio": "#audio", "wearable": "#wearable",
        "smartphone": "#smartphone", "laptop": "#laptop", "tablet": "#tablet",
        "tv": "#tv", "foto": "#foto", "gaming": "#gaming",
        "smarthome": "#smarthome", "bambini": "#bambini",
        "accessori": "#tech",
        "altro": "#offerta",
    }
    return tags.get(cat, "#offerta")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text, image_url=None, reply_markup=None):
    base = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
    try:
        if image_url:
            pl = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text, "parse_mode": "HTML"}
            if reply_markup:
                pl["reply_markup"] = json.dumps(reply_markup)
            r = requests.post("{}/sendPhoto".format(base), json=pl, timeout=15)
            j = r.json()
            if j.get("ok"):
                return True
            log("  [TG_FAIL] photo: {}".format(j.get("description", "??")))
        pl = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_markup:
            pl["reply_markup"] = json.dumps(reply_markup)
        r = requests.post("{}/sendMessage".format(base), json=pl, timeout=15)
        r.raise_for_status()
        j = r.json()
        if not j.get("ok"):
            log("  [TG_FAIL] msg: {}".format(j.get("description", "??")))
            return False
        return True
    except Exception as e:
        log("  [TG_ERR] {}".format(e))
        return False


def make_share_button(asin):
    u = "https://t.me/share/url?url={}&text={}".format(
        requests.utils.quote("https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)),
        requests.utils.quote("Offerta su @sottocosto_oggi!"))
    return {"inline_keyboard": [[{"text": "\U0001f4e4 Condividi con un amico", "url": u}]]}


def fmt_stars(rating, rc):
    try:
        r = float(rating)
        return "{}{} {}/5{}".format(
            "\u2B50" * int(r), "\u2606" * (5 - int(r)),
            rating, " ({} recensioni)".format(rc) if rc else "")
    except (ValueError, TypeError):
        return ""


def fmt_saving(s):
    if s >= 100:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f4a5\n\n".format(s)
    if s >= 50:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f525\n\n".format(s)
    return "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(s)


def format_deal(deal, dn=0, special=None):
    pct = deal["discount_percent"]
    asin = deal["asin"]
    title = deal["title"]
    e = get_category_emoji(title)
    tag = get_category_hashtag(title)
    aff = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    cl = "https://www.amazon.it/dp/{}".format(asin)

    if special == "top":
        msg = "\U0001f3c6 <b>MIGLIOR OFFERTA DI OGGI</b> \U0001f3c6\n\n"
        ft = "#offertadelgiorno"
        fx = "Il top di oggi!"
    elif special == "flash" or deal.get("has_deal"):
        msg = "\u26a1 <b>OFFERTA LAMPO -{}%</b> \u26a1\n<i>Sconto a tempo! Potrebbe finire presto.</i>\n\n".format(pct)
        ft = "#offertalampo"
        fx = "Corri!"
    else:
        a = "\U0001f6a8" * (3 if pct >= 50 else 2 if pct >= 30 else 1)
        msg = "{} <b>SCONTO -{}%</b> {}\n\n".format(a, pct, a)
        ft = "#offerta"
        fx = random.choice(FOOTER_PHRASES)

    msg += "{} <b>{}</b>\n\n".format(e, title)
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(
        deal["original_price"], deal["current_price"])
    msg += fmt_saving(deal["discount"])

    if deal.get("rating"):
        st = fmt_stars(deal["rating"], deal.get("review_count"))
        if st:
            msg += "{}\n\n".format(st)

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(aff)
    msg += "{}\n\n".format(cl)
    msg += "\u2501" * 15 + "\n"
    if dn > 0:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerta #{} di oggi\n".format(dn)
    else:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 {}\n".format(fx)
    msg += "{} #amazon #sconto{} {}\n".format(ft, pct, tag)
    msg += "\u26a0\ufe0f <i>Prezzo soggetto a variazioni</i>"
    return msg


# ============================================================
# PROMO AFFILIATE
# ============================================================

def send_good_morning():
    send_telegram(random.choice(GOOD_MORNING))
    log("[OK] Buongiorno!")


def send_prime_promo(t):
    msgs = [
        "\U0001f4e6 <b>Amazon Prime \u2014 Prova gratuita 30 giorni</b>\n\nSpedizioni illimitate in 1 giorno, Prime Video, Prime Music, foto illimitate e accesso anticipato alle Offerte Lampo.\n\nGratis per 30 giorni. Cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva la prova gratuita</a>\n\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t),
    ]
    send_telegram(random.choice(msgs))
    log("[OK] Prime!")


def send_prime_video_promo(t):
    send_telegram("\U0001f3ac <b>Prime Video \u2014 30 giorni gratis</b>\n\nMigliaia di film e serie TV in streaming, incluse esclusive come <i>The Boys</i>, <i>The Grand Tour</i>, <i>Reacher</i> e <i>Fallout</i>.\n\nIncluso con Amazon Prime.\n\n\U0001f449 <a href=\"https://www.primevideo.com/?&tag={t}\">Attiva Prime Video gratis</a>\n\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t))
    log("[OK] Prime Video!")


def send_music_promo(t):
    send_telegram("\U0001f3b5 <b>Amazon Music Unlimited \u2014 30 giorni gratis</b>\n\n90 milioni di brani in HD, senza pubblicit\u00e0. Download offline.\n\n\U0001f449 <a href=\"https://www.amazon.it/gp/dmusic/promotions/AmazonMusicUnlimited?tag={t}\">Prova Music Unlimited</a>\n\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t))
    log("[OK] Music!")


def send_audible_promo(t):
    send_telegram("\U0001f4d6 <b>Audible \u2014 30 giorni gratis</b>\n\nMigliaia di audiolibri e podcast originali.\n\n\U0001f449 <a href=\"https://www.audible.it/?source_code=ASSORWS01219800B8&tag={t}\">Prova Audible gratis</a>\n\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t))
    log("[OK] Audible!")


def send_evening_recap(today):
    stats = load_stats()
    deals = stats.get(today, [])
    if not deals:
        return
    top3 = sorted(deals, key=lambda d: d["discount_percent"], reverse=True)[:3]
    msg = "\U0001f319 <b>TOP 3 offerte di oggi</b>\n\n"
    for i, d in enumerate(top3):
        e = get_category_emoji(d["title"])
        lk = "https://www.amazon.it/dp/{}?tag={}".format(d["asin"], AMAZON_PARTNER_TAG)
        msg += "{}. {} <a href=\"{}\">{}</a>\n   <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b> (-{}%)\n\n".format(
            i+1, e, lk, d["title"][:60], d["original_price"], d["current_price"], d["discount_percent"])
    msg += "Oggi: <b>{}</b> offerte pubblicate!\n\n".format(len(deals))
    msg += "\U0001f514 Non perderti quelle di domani!\n\U0001f4f2 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("[OK] Recap!")


# ============================================================
# PERSISTENZA con auto-clean
# ============================================================

def load_stats():
    try:
        return json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    except Exception:
        return {}


def save_deal_stat(deal):
    stats = load_stats()
    today = datetime.date.today().isoformat()
    if today not in stats:
        stats[today] = []
    stats[today].append({
        "asin": deal["asin"], "title": deal["title"],
        "current_price": deal["current_price"], "original_price": deal["original_price"],
        "discount_percent": deal["discount_percent"],
    })
    wa = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    STATS_FILE.write_text(json.dumps({k: v for k, v in stats.items() if k >= wa}))


def load_posted():
    """Mantiene memoria di ASIN posted. Auto-pulisce se troppo grande."""
    try:
        data = json.loads(POSTED_FILE.read_text()) if POSTED_FILE.exists() else {}
        if not isinstance(data, dict):
            return {}

        # Mantieni solo oggi + ieri
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        filtered = {k: v for k, v in data.items() if k >= yesterday}

        # CONTROLLO AUTO-CLEAN: se totale ASIN > MAX_MEMORY_SIZE, resetta IERI
        total_asins = sum(len(v) for v in filtered.values())
        if total_asins > MAX_MEMORY_SIZE:
            log("[CLEAN] Memoria piena ({} ASIN). Pulisco IERI.".format(total_asins))
            today = datetime.date.today().isoformat()
            filtered = {today: filtered.get(today, [])}

        return filtered
    except Exception as e:
        log("[ERR] load_posted: {}".format(e))
        return {}


def save_posted(p):
    POSTED_FILE.write_text(json.dumps(p))


def is_posted(p, k):
    for day_keys in p.values():
        if k in day_keys:
            return True
    return False


def mark_posted(p, k):
    today = datetime.date.today().isoformat()
    if today not in p:
        p[today] = []
    if k not in p[today]:
        p[today].append(k)


def count_deals(p):
    today = datetime.date.today().isoformat()
    return len([k for k in p.get(today, []) if not k.startswith("_")])


def is_special_posted(p, k):
    today = datetime.date.today().isoformat()
    return k in p.get(today, [])


# ============================================================
# MAIN con diagnostica completa
# ============================================================

def main():
    now = get_italy_now()
    hour = now.hour
    today = datetime.date.today().isoformat()
    wd = now.weekday()

    log("=" * 50)
    log("=== BOT {} ===".format(BOT_VERSION))
    log("=== UTC: {} | IT: {} ===".format(
        datetime.datetime.now().isoformat()[:19], now.strftime("%H:%M")))
    log("=" * 50)

    if not is_publish_time():
        log("[STOP] Notte. Hour={}, range={}-{}".format(hour, PUBLISH_START_HOUR, PUBLISH_END_HOUR))
        return

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
        "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"]
        if not os.environ.get(v)]
    if missing:
        log("[FATAL] Mancano variabili: {}".format(missing))
        return

    posted = load_posted()
    posted_count_today = count_deals(posted)
    seen_count = sum(len(v) for v in posted.values())
    log("[STATE] Memoria: {} ASIN totali | Oggi: {} pubblicati".format(seen_count, posted_count_today))

    # ===== PALINSESTO SPECIALI =====
    if hour == 7 and not is_special_posted(posted, "_am"):
        send_good_morning()
        mark_posted(posted, "_am")
        save_posted(posted)
        time.sleep(5)

    if hour == 11 and not is_special_posted(posted, "_pr"):
        send_prime_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_pr")
        save_posted(posted)
        time.sleep(5)

    if hour == 14 and not is_special_posted(posted, "_pv"):
        send_prime_video_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_pv")
        save_posted(posted)
        time.sleep(5)

    if hour == 17 and not is_special_posted(posted, "_ab"):
        send_audible_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_ab")
        save_posted(posted)
        time.sleep(5)

    if hour == 20 and not is_special_posted(posted, "_mu"):
        send_music_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_mu")
        save_posted(posted)
        time.sleep(5)

    if hour == 22 and not is_special_posted(posted, "_rc"):
        send_evening_recap(today)
        mark_posted(posted, "_rc")
        save_posted(posted)
        return

    # ===== RICERCA OFFERTE A 5 FASI ORDINATE PER PRIORITA' EDITORIALE =====
    api = create_api()
    all_deals = []
    seen = set()
    for day_keys in posted.values():
        for k in day_keys:
            if not k.startswith("_"):
                seen.add(k)
    log("[POOL] Skip lista: {} ASIN gia' visti".format(len(seen)))

    # Helper per cercare
    def search_phase(name, keywords, priority_filter=None):
        log("=== FASE {}: {} keyword ===".format(name, len(keywords)))
        for kw in keywords:
            if len(all_deals) >= MAX_DEALS_POOL:
                break
            deals_found = search_deals(api, kw)
            new_count = 0
            for d in deals_found:
                if d["asin"] in seen:
                    continue
                if priority_filter and priority_filter(d):
                    continue
                if len(all_deals) >= MAX_DEALS_POOL:
                    break
                seen.add(d["asin"])
                d["_kw"] = kw
                all_deals.append(d)
                new_count += 1
            if new_count > 0:
                log("  [{}] -> {} nuovi".format(kw[:30], new_count))

    # FASE 1: Deal attivi (priorita' max)
    log("=== FASE 1: Deal Amazon attivi ===")
    for kw in DEAL_KEYWORDS:
        if len(all_deals) >= MAX_DEALS_POOL:
            break
        deals_found = search_deals(api, kw)
        new_count = 0
        for d in deals_found:
            if d["asin"] in seen:
                continue
            if not d.get("has_deal"):  # solo deal attivi qui
                continue
            seen.add(d["asin"])
            d["_kw"] = kw
            d["_is_active_deal"] = True
            all_deals.append(d)
            new_count += 1
        if new_count > 0:
            log("  [DEAL: {}] -> {}".format(kw, new_count))
    log("[POOL] Dopo Fase 1: {} deal attivi".format(len(all_deals)))

    # FASE 2: CASA/CUCINA
    search_phase("2 CASA/CUCINA", HOUSE_KITCHEN_KEYWORDS)
    log("[POOL] Dopo Fase 2: {}".format(len(all_deals)))

    # FASE 3: MODA
    search_phase("3 MODA", FASHION_KEYWORDS)
    log("[POOL] Dopo Fase 3: {}".format(len(all_deals)))

    # FASE 4: SPORT
    search_phase("4 SPORT", SPORT_KEYWORDS)
    log("[POOL] Dopo Fase 4: {}".format(len(all_deals)))

    # FASE 5: BELLEZZA
    search_phase("5 BELLEZZA", BEAUTY_KEYWORDS)
    log("[POOL] Dopo Fase 5: {}".format(len(all_deals)))

    # FASE 6: ELETTRONICA
    search_phase("6 ELETTRONICA", TECH_KEYWORDS)
    log("[POOL] Dopo Fase 6: {}".format(len(all_deals)))

    # FASE 7: Sera o pool basso
    if hour >= 19 and len(all_deals) < MAX_POSTS_PER_CYCLE * 5:
        search_phase("7 EVENING FRESH", EVENING_KEYWORDS)
        log("[POOL] Dopo Fase 7: {}".format(len(all_deals)))

    log("=" * 50)
    log("[POOL FINALE] {} offerte candidate".format(len(all_deals)))

    if not all_deals:
        log("[STOP] Pool vuoto. Niente da pubblicare.")
        # AUTO-RECOVERY: se il pool e' vuoto per 3+ cicli, suggerisci reset memoria
        return

    # ===== ORDINAMENTO EDITORIALE =====
    all_deals.sort(key=get_editorial_priority)

    # Log top 5 candidati
    log("[TOP 5 candidati]:")
    for i, d in enumerate(all_deals[:5]):
        cat = get_deal_category(d["title"])
        score = get_editorial_priority(d)
        brand_lbl = ["TOP", "GOOD", "?"][d.get('brand_prio', 2)]
        log("  {}. score={} cat={} brand={} -{}% | {}".format(
            i+1, score, cat, brand_lbl, d["discount_percent"], d["title"][:45]))

    # Diversifica
    all_deals = diversify_deals(all_deals)

    # ===== OFFERTA DEL GIORNO (>= 9) =====
    if hour >= 9 and not is_special_posted(posted, "_top"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        log("[TOP DEL GIORNO] -{}% | {}".format(best["discount_percent"], best["title"][:50]))
        ok = send_telegram(format_deal(best, special="top"), best.get("image_url"), make_share_button(best["asin"]))
        if ok:
            mark_posted(posted, best["asin"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            log("[OK] Top pubblicato!")
            time.sleep(POST_INTERVAL_SECONDS)
        else:
            log("[FAIL] Top non pubblicato (Telegram error)")

    # ===== PUBBLICA OFFERTE NORMALI =====
    pub = 0
    log("[PUBLISH] Inizio loop pubblicazione (max {})".format(MAX_POSTS_PER_CYCLE))
    for d in all_deals:
        if pub >= MAX_POSTS_PER_CYCLE:
            log("[STOP] Limite ciclo raggiunto: {}".format(pub))
            break
        if not is_publish_time():
            log("[STOP] Fuori orario")
            break
        if is_posted(posted, d["asin"]):
            continue
        dn = count_deals(posted) + 1
        sp = "flash" if d.get("has_deal") or d["discount_percent"] >= FLASH_DEAL_PERCENT else None
        cat = get_deal_category(d["title"])
        log("[PUB #{}] {} -{}% | {}".format(dn, cat, d["discount_percent"], d["title"][:45]))
        ok = send_telegram(format_deal(d, dn, sp), d.get("image_url"), make_share_button(d["asin"]))
        if ok:
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            pub += 1
            log("  [OK] Pubblicato")
            time.sleep(POST_INTERVAL_SECONDS)
        else:
            log("  [FAIL] Non pubblicato (TG error)")
            # Non incrementare pub, prova prossimo

    log("=" * 50)
    log("[RIEPILOGO] Pubblicate {} in questo ciclo. Oggi totale: {}".format(pub, count_deals(posted)))
    log("=" * 50)


if __name__ == "__main__":
    main()
