"""
Sottocosto Oggi - Bot v30 HYBRID BROWSE NODES
Novita' v30:
- Browse nodes Amazon Italia (24 categorie) per catturare TUTTO il catalogo
- Keyword generiche senza brand-bias (44 keyword)
- Keyword brand premium shufflate per varieta'
- Fallback automatico su keyword se browse_node_id non supportato
- Cap stretto 1 offerta/categoria per ciclo
- Anti-ripetizione delle ultime 3 categorie
- Palinsesto orari peak (8-9, 12-13, 20-22)
- Countdown automatico Prime Day 23-26 giugno 2026
"""

import os
import json
import datetime
import time
import random
import re
import sys
import requests
from pathlib import Path

from amazon_creatorsapi import AmazonCreatorsApi, Country
from amazon_creatorsapi.models import Condition

BOT_VERSION = "v30-HYBRID-BROWSE-NODES"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

# ========== CONFIG ==========
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "10"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 9.0
MIN_RATING = 3.5
MIN_REVIEWS = 25
NO_RATING_MIN_PRICE = 20.0
MAX_DEALS_POOL = 200
POST_INTERVAL_SECONDS = 90
MAX_MEMORY_SIZE = 500

# Orari di pubblicazione: 7-23 IT
PUBLISH_START_HOUR = 7
PUBLISH_END_HOUR = 23
TIMEZONE_OFFSET = 2

# ========== PRIME DAY 2026 ==========
PRIME_DAY_START = datetime.date(2026, 6, 23)
PRIME_DAY_END = datetime.date(2026, 6, 26)

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"


def log(msg):
    print(msg, flush=True)


# ============================================================
# FASCE ORARIE EDITORIALI
# ============================================================

def get_peak_multiplier(hour):
    """Ritorna moltiplicatore offerte/ciclo per fascia oraria.
    Fasce peak (8-9, 12-13, 20-22): 7-8 offerte/ciclo
    Fasce normali: 4-5 offerte/ciclo
    Fasce basse: 2-3 offerte/ciclo
    """
    if hour in (8, 9, 12, 13, 20, 21, 22):
        return 7  # peak
    if hour in (10, 11, 14, 15, 17, 18, 19):
        return 5  # normale
    return 3  # bassa (7, 16, 23)


# ============================================================
# REGOLE EDITORIALI - PRIORITA' CATEGORIE
# ============================================================

CATEGORY_PRIORITY = {
    'casa_cucina': 1, 'cucina': 1, 'casaarredo': 1,
    'moda': 2, 'abbigliamento': 2, 'scarpe': 2, 'borse': 2, 'gioielli': 2,
    'sport': 3,
    'bellezza': 4, 'curapersona': 4,
    'audio': 5, 'smartphone': 5, 'tablet': 5, 'tv': 5,
    'wearable': 5, 'laptop': 5, 'gaming': 5, 'foto': 5, 'smarthome': 5,
    'accessori': 6,
    'altro': 9,
}

TRUSTED_BRANDS = {
    'top': ['Apple', 'Samsung', 'Sony', 'Bose', 'Dyson', 'Philips', 'Bosch',
            'LEGO', 'Levi\'s', 'Nike', 'Adidas', 'Ray-Ban', 'Garmin',
            'L\'Oreal', 'Estée Lauder', 'Chanel', 'Dior', 'Kerastase',
            'KitchenAid', 'De\'Longhi', 'Nespresso', 'Tefal', 'Le Creuset',
            'iRobot', 'Roomba', 'Roborock', 'Shark', 'Oral-B'],
    'good': ['Xiaomi', 'JBL', 'Logitech', 'Anker', 'Kindle', 'Echo',
             'Tommy Hilfiger', 'Calvin Klein', 'Puma', 'New Balance',
             'Maybelline', 'Clinique', 'Lancome', 'Pandora', 'Swarovski',
             'Ninja', 'Lavazza', 'Krups', 'WMF', 'Kenwood',
             'TP-Link', 'Netgear', 'Asus', 'HP', 'Lenovo', 'Dell',
             'GoPro', 'DJI', 'Canon', 'Fitbit', 'Amazfit', 'Braun', 'Remington'],
}


# ============================================================
# KEYWORD ORGANIZZATE
# ============================================================

DEAL_KEYWORDS = [
    "offerta del giorno", "offerta lampo",
    "deal today amazon", "offerte oggi",
    "sconto del giorno", "offerta limitata",
]

HOUSE_KITCHEN_KEYWORDS = [
    "De'Longhi macchina caffe", "Nespresso offerta",
    "KitchenAid", "Kenwood robot cucina",
    "Ninja friggitrice aria", "Philips friggitrice",
    "Tefal padella", "Le Creuset",
    "WMF pentole", "Bialetti",
    "Russell Hobbs", "Smeg piccoli elettrodomestici",
    "Joseph Joseph cucina", "Brabantia",
    "Tempur cuscino", "Emma materasso",
    "Lenzuola raso cotone", "Kärcher idropulitrice",
    "iRobot Roomba", "Roborock", "Dreame robot",
    "Dyson aspirapolvere", "Philips Hue",
    "Shark aspirapolvere", "Vorwerk Folletto",
]

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

SPORT_KEYWORDS = [
    "Nike running", "Adidas running",
    "ASICS running", "Brooks running",
    "Garmin GPS", "Theragun",
    "Decathlon", "Columbia outdoor",
    "The North Face", "Salomon",
    "Under Armour",
]

BEAUTY_KEYWORDS = [
    "L'Oreal Paris", "Maybelline", "NYX Professional",
    "Clinique", "Estee Lauder", "Lancome crema",
    "La Roche Posay", "Vichy", "Bioderma",
    "Kerastase", "L'Oreal Professionnel",
    "GHD piastra", "Dyson Airwrap",
    "Oral-B elettrico", "Philips Sonicare",
    "Chanel profumo", "Dior profumo",
    "Babyliss", "Remington",
    "Garnier", "Olaplex",
]

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

EVENING_KEYWORDS = [
    "best seller offerta", "piu venduti",
    "Top rated", "amazon choice",
    "prezzo minimo", "novita Amazon",
    "appena uscito", "scopri Amazon",
]

# ============================================================
# BROWSE NODES AMAZON ITALIA (cattura TUTTO il catalogo per categoria)
# Questi ID sono stabili nel tempo per le categorie principali
# ============================================================

AMAZON_IT_BROWSE_NODES = {
    # Casa, cucina, arredo
    "Casa e cucina":           "524015031",
    "Elettrodomestici":        "412606031",
    "Bricolage e Fai da te":   "524012031",
    "Giardino e giardinaggio": "524013031",
    "Illuminazione":           "3155356031",

    # Moda e accessori
    "Moda":                    "524017031",
    "Scarpe":                  "8463981031",
    "Borse, scarpe":           "8463981031",
    "Gioielli":                "1571265031",
    "Orologi":                 "524023031",

    # Sport e tempo libero
    "Sport e tempo libero":    "524014031",

    # Bellezza e cura personale
    "Bellezza":                "11962031",
    "Salute e cura della persona": "524027031",

    # Elettronica (priorita' MENO alta visto che ne abbiamo tanta gia')
    "Elettronica":             "412609031",
    "Informatica":             "412610031",
    "Videogiochi":             "412603031",

    # Bambini e neonati
    "Prima infanzia":          "1571278031",
    "Giochi e giocattoli":     "412607031",

    # Animali, libri, cibo
    "Prodotti per animali":    "8606827031",
    "Libri":                   "411663031",
    "Alimentari e cura della casa": "5866074031",

    # Auto e moto
    "Auto e moto":             "524011031",

    # Cancelleria e ufficio
    "Cancelleria e ufficio":   "412602031",

    # Strumenti musicali
    "Strumenti musicali":      "412605031",
}

# Search Index Amazon (macro-categorie)
AMAZON_SEARCH_INDEXES = [
    "HomeAndKitchen",      # casa cucina
    "Fashion",              # moda
    "FashionWomen",         # moda donna
    "FashionMen",           # moda uomo
    "SportsAndOutdoors",    # sport
    "Beauty",               # bellezza
    "HealthPersonalCare",   # salute
    "Garden",               # giardinaggio
    "Toys",                 # giocattoli
    "PetSupplies",          # animali
    "Books",                # libri
    "Automotive",           # auto
    "Tools",                # fai-da-te
    "OfficeProducts",       # ufficio
    "GroceryAndGourmetFood", # alimentari
    "Appliances",           # elettrodomestici
]

# Keyword GENERICHE che catturano molti prodotti senza brand-bias
GENERIC_KEYWORDS = [
    # Casa cucina
    "set pentole acciaio", "tappeto cucina antiscivolo", "tovaglia rettangolare",
    "lenzuola matrimoniali", "asciugamani spugna", "tende camera letto",
    "vasi piante interno", "portacandele design",

    # Moda generico
    "scarpe donna eleganti", "scarpe uomo casual", "borsa lavoro donna",
    "zaino scuola", "occhiali da sole donna", "occhiali sole uomo",
    "cappello estivo", "costume mare donna", "costume mare uomo",

    # Sport
    "tappetino yoga", "manubri palestra", "fascia elastica fitness",
    "borraccia termica", "scarpe trekking", "zaino escursionismo",
    "racchetta tennis", "pallone calcio",

    # Bellezza
    "crema solare viso", "siero vitamina c", "balsamo labbra",
    "trousse beauty case", "set pennelli trucco", "smalto unghie",

    # Bambini giochi
    "puzzle 1000 pezzi", "gioco da tavolo strategia",
    "passeggino leggero", "biberon neonato",

    # Animali
    "crocchette cane premium", "tiragraffi gatto",
    "collare cane", "lettiera gatto",

    # Libri/cancelleria/casa
    "agenda 2026", "quaderno spirale", "penne stilografiche",
    "stampante multifunzione", "scaffale libreria",
]

# ============================================================
# BLACKLIST
# ============================================================

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


def days_until_prime_day():
    today = get_italy_now().date()
    delta = (PRIME_DAY_START - today).days
    return delta


def is_prime_day_active():
    today = get_italy_now().date()
    return PRIME_DAY_START <= today <= PRIME_DAY_END


def is_prime_day_countdown_phase():
    """Countdown phase: 14 giorni prima dell'inizio."""
    d = days_until_prime_day()
    return 0 < d <= 14


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


def search_deals(api, keyword=None, browse_node_id=None, search_index=None, max_results=10):
    """Cerca offerte usando una delle 3 strategie:
    - keyword: search testuale (es. 'iPhone offerta')
    - browse_node_id: ricerca per categoria Amazon (es. '524015031' = Casa e cucina)
    - search_index: ricerca in macro categoria (es. 'HomeAndKitchen', 'Fashion')
    Almeno uno tra keyword/browse_node_id deve essere specificato.
    """
    try:
        kwargs = {
            'item_count': max_results,
            'condition': Condition.NEW,
            'min_saving_percent': MIN_DISCOUNT_PERCENT,
        }
        if keyword:
            kwargs['keywords'] = keyword
        if browse_node_id:
            kwargs['browse_node_id'] = browse_node_id
        if search_index:
            kwargs['search_index'] = search_index

        # Se solo browse_node_id senza keyword, forziamo una keyword generica
        # (l'API spesso richiede almeno una keyword)
        if browse_node_id and not keyword:
            kwargs['keywords'] = "offerta"

        results = api.search_items(**kwargs)
    except TypeError as e:
        # Se il parametro non esiste in questa versione, fallback su keyword
        log("  [API_PARAM_ERR] {} - fallback keyword".format(str(e)[:60]))
        if keyword:
            try:
                results = api.search_items(
                    keywords=keyword, item_count=max_results,
                    condition=Condition.NEW,
                    min_saving_percent=MIN_DISCOUNT_PERCENT,
                )
            except Exception as e2:
                log("  [API_ERR] fallback failed: {}".format(str(e2)[:80]))
                return []
        else:
            return []
    except Exception as e:
        identifier = keyword or browse_node_id or search_index
        log("  [API_ERR] {}: {}".format(identifier, str(e)[:80]))
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
    if any(w in t for w in ["aspira", "robot pulizia", "roomba", "roborock", "dreame", "dyson v", "kärcher", "karcher", "shark"]): return "casaarredo"
    if any(w in t for w in ["materass", "cuscin", "asciugamani", "copripiumino", "lenzuol", "piumino", "lampad", "candela", "tappeto", "hue"]): return "casaarredo"
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
    if any(w in t for w in ["caricatore", "power bank", "cavo usb", "hub usb", "anker"]): return "accessori"
    return "altro"


def get_editorial_priority(deal):
    cat = get_deal_category(deal['title'])
    cat_prio = CATEGORY_PRIORITY.get(cat, 9)
    brand = deal.get('brand_prio', 2)
    score = cat_prio * 10 + brand * 3
    if deal.get('has_deal'):
        score -= 5
    if deal.get('_is_active_deal'):
        score -= 8
    if deal['discount_percent'] >= 50:
        score -= 5
    elif deal['discount_percent'] >= 30:
        score -= 3
    return score


def diversify_deals(deals):
    """Randomizza l'ordine delle offerte mescolando le categorie.

    Strategia: round-robin tra le categorie con shuffle interno.
    1. Raggruppa per categoria
    2. Shuffla le offerte dentro ogni categoria
    3. Shuffla l'ordine delle categorie stesse
    4. Estrae a turno una offerta da ogni categoria (round-robin)

    Risultato: pubblicazione varia, nessuna categoria consecutiva ripetuta,
    ma con ordine totalmente imprevedibile.
    """
    if len(deals) <= 1:
        return deals

    # 1. Raggruppa per categoria
    by_category = {}
    for d in deals:
        cat = get_deal_category(d["title"])
        by_category.setdefault(cat, []).append(d)

    # 2. Shuffla ogni gruppo (le offerte dentro la categoria sono in ordine random)
    for cat in by_category:
        random.shuffle(by_category[cat])

    # 3. Ordine delle categorie randomizzato MA con bias verso le priorita' editoriali
    # Categorie con piu' offerte hanno piu' chance di essere "estratte"
    category_order = list(by_category.keys())
    random.shuffle(category_order)

    # 4. Round-robin: estrai una offerta per volta da categorie diverse
    result = []
    while any(by_category.values()):
        # Re-shuffla l'ordine ogni giro per varieta'
        random.shuffle(category_order)
        for cat in category_order:
            if by_category[cat]:
                result.append(by_category[cat].pop(0))
                # Evita 3+ categorie identiche di fila (improbabile ma controllo extra)

    return result


def shuffle_within_priority(deals):
    """Shuffla le offerte mantenendo solo i 'tier' di priorita' editoriale.

    Tier 1 (score 0-15): brand TOP in categoria HOT (casa, moda)
    Tier 2 (score 16-30): brand GOOD oppure media priorita'
    Tier 3 (score 31+): tutto il resto

    Le offerte vengono shufflate DENTRO il loro tier, ma i tier piu' alti
    restano sopra. Questo evita ordinamento sempre uguale per priorita'.
    """
    if len(deals) <= 1:
        return deals

    tier1 = []
    tier2 = []
    tier3 = []

    for d in deals:
        score = get_editorial_priority(d)
        if score <= 15:
            tier1.append(d)
        elif score <= 30:
            tier2.append(d)
        else:
            tier3.append(d)

    # Shuffla entro ogni tier
    random.shuffle(tier1)
    random.shuffle(tier2)
    random.shuffle(tier3)

    return tier1 + tier2 + tier3


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
# MESSAGGI SPECIALI
# ============================================================

def send_good_morning():
    send_telegram(random.choice(GOOD_MORNING))
    log("[OK] Buongiorno!")


def send_prime_promo(t):
    msg = "\U0001f4e6 <b>Amazon Prime \u2014 Prova gratuita 30 giorni</b>\n\nSpedizioni illimitate in 1 giorno, Prime Video, Prime Music, foto illimitate e accesso anticipato alle Offerte Lampo.\n\nGratis per 30 giorni. Cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva la prova gratuita</a>\n\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t)
    send_telegram(msg)
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


# ========== PRIME DAY ==========

def send_prime_day_countdown(t):
    """Countdown automatico Prime Day."""
    days = days_until_prime_day()
    partner = t

    if days <= 0:
        return

    if days == 14:
        msg = (
            "\U0001f525 <b>14 GIORNI AL PRIME DAY 2026!</b> \U0001f525\n\n"
            "Dal 23 al 26 giugno: 4 giorni di sconti esclusivi su Amazon.\n\n"
            "\U0001f389 Migliaia di offerte su:\n"
            "\u2022 Casa e cucina\n"
            "\u2022 Tech ed elettronica\n"
            "\u2022 Moda e bellezza\n"
            "\u2022 Sport e tempo libero\n\n"
            "\u26a0\ufe0f <b>Solo per membri Prime!</b>\n\n"
            "\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva la prova gratuita 30 giorni</a>\n\n"
            "Resta connesso sul canale per il countdown e le anteprime!\n\U0001f4f2 <b>@sottocosto_oggi</b>"
        ).format(t=partner)
    elif days == 7:
        msg = (
            "\u23f3 <b>1 SETTIMANA AL PRIME DAY!</b>\n\n"
            "Dal 23 al 26 giugno scopri le offerte piu' incredibili dell'anno!\n\n"
            "\U0001f4dd Categorie da tenere d'occhio:\n"
            "\U0001f3e0 Casa e cucina (KitchenAid, De'Longhi, Nespresso)\n"
            "\U0001f4f1 Tech (Apple, Samsung, Sony)\n"
            "\U0001f484 Bellezza (L'Oreal, Estee Lauder, GHD)\n"
            "\U0001f455 Moda (Levi's, Nike, Adidas)\n\n"
            "\u26a0\ufe0f Le offerte sono solo per membri Prime.\n\n"
            "\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Non hai ancora Prime? Provalo gratis 30 giorni</a>\n\n"
            "\U0001f4f2 <b>@sottocosto_oggi</b>"
        ).format(t=partner)
    elif days == 3:
        msg = (
            "\U0001f6a8 <b>3 GIORNI AL PRIME DAY!</b> \U0001f6a8\n\n"
            "Pronto per 4 giorni di shopping selvaggio?\n\n"
            "\U0001f4cb Checklist Pre-Prime Day:\n"
            "\u2705 Membership Prime attiva\n"
            "\u2705 Lista desideri aggiornata\n"
            "\u2705 App Amazon installata\n"
            "\u2705 Notifiche @sottocosto_oggi attive\n\n"
            "\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva Prime se non ce l'hai</a>\n\n"
            "\U0001f4f2 <b>@sottocosto_oggi</b>"
        ).format(t=partner)
    elif days == 1:
        msg = (
            "\U0001f525 <b>DOMANI INIZIA IL PRIME DAY 2026!</b> \U0001f525\n\n"
            "Le migliori offerte dell'anno stanno per arrivare.\n\n"
            "\U0001f4c5 Quando: dal 23 al 26 giugno\n"
            "\U0001f3af A chi: solo membri Prime\n\n"
            "\u26a1 Le offerte vanno a ruba in pochi minuti!\n\n"
            "Pubblicheremo SOLO le migliori, in tempo reale.\n\U0001f514 Attiva le notifiche del canale!\n\n"
            "\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Ultimo momento per attivare Prime</a>\n\n"
            "\U0001f4f2 <b>@sottocosto_oggi</b>"
        ).format(t=partner)
    else:
        # Countdown generico (es. 13, 12, 11... giorni)
        msg = (
            "\u23f3 <b>-{n} GIORNI AL PRIME DAY 2026</b>\n\n"
            "Mancano sempre meno giorni alle migliori offerte dell'anno!\n\n"
            "\U0001f4c5 23-26 giugno - solo membri Prime\n\n"
            "\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva Prime gratis 30 giorni</a>\n\n"
            "\U0001f4f2 <b>@sottocosto_oggi</b>"
        ).format(n=days, t=partner)

    send_telegram(msg)
    log("[OK] Countdown PD! ({} giorni)".format(days))


def send_prime_day_live(t):
    """Messaggio durante Prime Day attivo."""
    today = get_italy_now().date()
    day_num = (today - PRIME_DAY_START).days + 1
    total_days = 4

    msg = (
        "\U0001f525 <b>PRIME DAY GIORNO {n}/{tot}</b> \U0001f525\n\n"
        "Le offerte piu' calde dell'anno sono ATTIVE ORA!\n\n"
        "\u26a1 Le migliori vanno via in pochi minuti\n"
        "\U0001f514 Attiva le notifiche per non perdere nulla\n\n"
        "\U0001f449 <a href=\"https://www.amazon.it/primeday?tag={t}\">Esplora Prime Day su Amazon</a>\n\n"
        "Stiamo pubblicando le migliori offerte in tempo reale!\n\U0001f4f2 <b>@sottocosto_oggi</b>"
    ).format(n=day_num, tot=total_days, t=t)
    send_telegram(msg)
    log("[OK] Prime Day live!")


# ============================================================
# PERSISTENZA
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
    try:
        data = json.loads(POSTED_FILE.read_text()) if POSTED_FILE.exists() else {}
        if not isinstance(data, dict):
            return {}
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        filtered = {k: v for k, v in data.items() if k >= yesterday}
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
# MAIN
# ============================================================

def main():
    now = get_italy_now()
    hour = now.hour
    today = datetime.date.today().isoformat()
    wd = now.weekday()
    pd_days = days_until_prime_day()
    pd_active = is_prime_day_active()

    log("=" * 60)
    log("=== BOT {} ===".format(BOT_VERSION))
    log("=== UTC: {} | IT: {} ===".format(
        datetime.datetime.now().isoformat()[:19], now.strftime("%H:%M")))
    log("=== Prime Day: {} | Days: {} ===".format(
        "ATTIVO" if pd_active else "FUTURO", pd_days))
    log("=" * 60)

    if not is_publish_time():
        log("[STOP] Notte. Hour={}".format(hour))
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
    max_posts_cycle = get_peak_multiplier(hour)
    log("[STATE] Memoria: {} ASIN | Oggi: {} pubblicati | Max/ciclo: {}".format(
        seen_count, posted_count_today, max_posts_cycle))

    # ===== PALINSESTO SPECIALI =====
    if hour == 7 and not is_special_posted(posted, "_am"):
        send_good_morning()
        mark_posted(posted, "_am")
        save_posted(posted)
        time.sleep(5)

    # PRIME DAY: countdown automatici
    if pd_days in [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]:
        key = "_pd_cd_{}".format(pd_days)
        # Pubblica countdown alle 9:00 nei giorni di countdown
        if hour == 9 and not is_special_posted(posted, key):
            send_prime_day_countdown(AMAZON_PARTNER_TAG)
            mark_posted(posted, key)
            save_posted(posted)
            time.sleep(5)

    # PRIME DAY ATTIVO: messaggio live
    if pd_active:
        # Messaggio live alle 9:00 e 14:00 e 20:00
        for h, suffix in [(9, "am"), (14, "pm"), (20, "ev")]:
            key = "_pd_live_{}_{}".format(today, suffix)
            if hour == h and not is_special_posted(posted, key):
                send_prime_day_live(AMAZON_PARTNER_TAG)
                mark_posted(posted, key)
                save_posted(posted)
                time.sleep(5)

    # PROMO REGOLARI (saltate durante Prime Day per non sovrapporsi)
    if not pd_active:
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
        if hour == 19 and not is_special_posted(posted, "_mu"):
            send_music_promo(AMAZON_PARTNER_TAG)
            mark_posted(posted, "_mu")
            save_posted(posted)
            time.sleep(5)

    if hour == 22 and not is_special_posted(posted, "_rc"):
        send_evening_recap(today)
        mark_posted(posted, "_rc")
        save_posted(posted)
        return

    # ===== RICERCA OFFERTE =====
    api = create_api()
    all_deals = []
    seen = set()
    for day_keys in posted.values():
        for k in day_keys:
            if not k.startswith("_"):
                seen.add(k)
    log("[POOL] Skip: {} ASIN gia' visti".format(len(seen)))

    def search_phase(name, keywords):
        log("=== FASE {}: {} kw ===".format(name, len(keywords)))
        for kw in keywords:
            if len(all_deals) >= MAX_DEALS_POOL:
                break
            deals_found = search_deals(api, keyword=kw)
            new_count = 0
            for d in deals_found:
                if d["asin"] in seen:
                    continue
                if len(all_deals) >= MAX_DEALS_POOL:
                    break
                seen.add(d["asin"])
                d["_kw"] = kw
                all_deals.append(d)
                new_count += 1
            if new_count > 0:
                log("  [{}] -> {}".format(kw[:35], new_count))

    def search_browse_nodes_phase(name, nodes_dict):
        """Cerca per browse_node_id. Restituisce TUTTO il catalogo di una categoria."""
        log("=== FASE {}: {} browse nodes ===".format(name, len(nodes_dict)))
        # Shuffla l'ordine delle categorie per varieta'
        items = list(nodes_dict.items())
        random.shuffle(items)
        for cat_name, node_id in items:
            if len(all_deals) >= MAX_DEALS_POOL:
                break
            deals_found = search_deals(api, browse_node_id=node_id, max_results=10)
            new_count = 0
            for d in deals_found:
                if d["asin"] in seen:
                    continue
                if len(all_deals) >= MAX_DEALS_POOL:
                    break
                seen.add(d["asin"])
                d["_kw"] = "BROWSE:{}".format(cat_name)
                all_deals.append(d)
                new_count += 1
            if new_count > 0:
                log("  [BROWSE: {}] -> {}".format(cat_name[:30], new_count))

    # FASE 1: Deal attivi
    log("=== FASE 1: Deal Amazon attivi ===")
    for kw in DEAL_KEYWORDS:
        if len(all_deals) >= MAX_DEALS_POOL:
            break
        deals_found = search_deals(api, keyword=kw)
        new_count = 0
        for d in deals_found:
            if d["asin"] in seen:
                continue
            if not d.get("has_deal"):
                continue
            seen.add(d["asin"])
            d["_kw"] = kw
            d["_is_active_deal"] = True
            all_deals.append(d)
            new_count += 1
        if new_count > 0:
            log("  [DEAL: {}] -> {}".format(kw, new_count))
    log("[POOL] Dopo F1: {}".format(len(all_deals)))

    # ===========================================
    # FASE 2: BROWSE NODES - cattura TUTTO il catalogo per categoria
    # Questa e' la fase chiave: pesca da TUTTE le categorie senza keyword bias
    # ===========================================
    search_browse_nodes_phase("2 BROWSE NODES (catalogo per categoria)", AMAZON_IT_BROWSE_NODES)
    log("[POOL] Dopo F2 (browse): {}".format(len(all_deals)))

    # ===========================================
    # FASE 3: KEYWORD GENERICHE - prodotti senza brand-bias
    # ===========================================
    search_phase("3 GENERIC (prodotti senza brand bias)", GENERIC_KEYWORDS)
    log("[POOL] Dopo F3 (generic): {}".format(len(all_deals)))

    # ===========================================
    # FASE 4-8: KEYWORD BRAND TOP (qualita' premium, manteniamo per garantire brand riconosciuti)
    # Le carichiamo SHUFFLATE per varieta'
    # ===========================================
    house_shuffled = list(HOUSE_KITCHEN_KEYWORDS)
    random.shuffle(house_shuffled)
    search_phase("4 CASA/CUCINA premium", house_shuffled)
    log("[POOL] {}".format(len(all_deals)))

    fashion_shuffled = list(FASHION_KEYWORDS)
    random.shuffle(fashion_shuffled)
    search_phase("5 MODA premium", fashion_shuffled)
    log("[POOL] {}".format(len(all_deals)))

    sport_shuffled = list(SPORT_KEYWORDS)
    random.shuffle(sport_shuffled)
    search_phase("6 SPORT premium", sport_shuffled)
    log("[POOL] {}".format(len(all_deals)))

    beauty_shuffled = list(BEAUTY_KEYWORDS)
    random.shuffle(beauty_shuffled)
    search_phase("7 BELLEZZA premium", beauty_shuffled)
    log("[POOL] {}".format(len(all_deals)))

    # Tech LAST (gia' ne abbiamo tanta nelle browse nodes)
    if len(all_deals) < MAX_DEALS_POOL // 2:
        tech_shuffled = list(TECH_KEYWORDS)
        random.shuffle(tech_shuffled)
        search_phase("8 ELETTRONICA premium", tech_shuffled[:15])  # solo 15, no overload tech
        log("[POOL] {}".format(len(all_deals)))

    if hour >= 19 and len(all_deals) < max_posts_cycle * 4:
        search_phase("9 EVENING", EVENING_KEYWORDS)

    log("=" * 60)
    log("[POOL FINALE] {} candidati | max post ciclo: {}".format(len(all_deals), max_posts_cycle))

    if not all_deals:
        log("[STOP] Pool vuoto.")
        return

    # ORDINAMENTO RANDOMIZZATO:
    # 1. Shuffla entro tier di priorita' (tier1 sopra, ma randomizzati)
    # 2. Diversifica round-robin tra categorie con shuffle ogni giro
    # 3. CAP per categoria: max 2 offerte stessa categoria per ciclo
    all_deals = shuffle_within_priority(all_deals)

    log("[TOP 5] (dopo shuffle nei tier):")
    for i, d in enumerate(all_deals[:5]):
        cat = get_deal_category(d["title"])
        score = get_editorial_priority(d)
        bp = ["TOP", "GOOD", "?"][d.get('brand_prio', 2)]
        log("  {}. s={} {} {} -{}% | {}".format(
            i+1, score, cat[:8], bp, d["discount_percent"], d["title"][:40]))

    # Conta offerte per categoria
    cat_counts_pool = {}
    for d in all_deals:
        c = get_deal_category(d["title"])
        cat_counts_pool[c] = cat_counts_pool.get(c, 0) + 1
    log("[POOL CATEGORIE]: {}".format(
        ", ".join(["{}={}".format(k, v) for k, v in sorted(cat_counts_pool.items(), key=lambda x: -x[1])[:8]])))

    # Round-robin tra categorie con randomizzazione
    all_deals = diversify_deals(all_deals)

    log("[ORDINE PUBBLICAZIONE] (primi 8 dopo diversify):")
    for i, d in enumerate(all_deals[:8]):
        cat = get_deal_category(d["title"])
        log("  {}. {} | {}".format(i+1, cat[:10], d["title"][:50]))

    # ===== TOP DEL GIORNO =====
    if hour >= 9 and not is_special_posted(posted, "_top"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        log("[TOP] -{}% | {}".format(best["discount_percent"], best["title"][:50]))
        ok = send_telegram(format_deal(best, special="top"), best.get("image_url"), make_share_button(best["asin"]))
        if ok:
            mark_posted(posted, best["asin"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            log("[OK] Top pubblicato!")
            time.sleep(POST_INTERVAL_SECONDS)

    # CAP per categoria: max 1 stessa categoria nel ciclo corrente
    # + Anti-ripetizione: skip se le ultime 3 offerte pubblicate oggi erano della stessa categoria
    pub = 0
    cat_count_cycle = {}  # categoria -> quante volte pubblicata in questo ciclo
    MAX_PER_CAT_CYCLE = 1  # massimo 1 offerta stessa categoria per ciclo
    skipped_for_cat = []

    # Recupera le ultime 3 categorie pubblicate oggi (dalle stats)
    recent_categories = []
    try:
        today_stats = load_stats().get(today, [])
        for d in today_stats[-3:]:
            recent_categories.append(get_deal_category(d["title"]))
        log("[ULTIME 3 CATEGORIE PUBBLICATE OGGI]: {}".format(recent_categories))
    except Exception:
        pass

    log("[PUBLISH] max {} per ciclo (peak hour={}) | max {} per categoria".format(
        max_posts_cycle, hour, MAX_PER_CAT_CYCLE))

    for d in all_deals:
        if pub >= max_posts_cycle:
            log("[STOP] Limite ciclo: {}".format(pub))
            break
        if not is_publish_time():
            break
        if is_posted(posted, d["asin"]):
            continue

        cat = get_deal_category(d["title"])

        # CAP per categoria in QUESTO ciclo
        if cat_count_cycle.get(cat, 0) >= MAX_PER_CAT_CYCLE:
            skipped_for_cat.append((cat, d["title"][:30]))
            continue

        # ANTI-RIPETIZIONE: skip se le ultime 3 erano della stessa categoria
        # (e ho ancora altre categorie da provare nel pool)
        if recent_categories.count(cat) >= 2:
            # Verifica se ci sono altre categorie disponibili nel resto del pool
            remaining_cats = set()
            for other in all_deals:
                if not is_posted(posted, other["asin"]) and cat_count_cycle.get(get_deal_category(other["title"]), 0) == 0:
                    other_cat = get_deal_category(other["title"])
                    if other_cat != cat:
                        remaining_cats.add(other_cat)
            if remaining_cats:
                log("[SKIP-REPEAT] {} (ultime 3 erano: {})".format(cat, recent_categories))
                skipped_for_cat.append((cat, d["title"][:30]))
                continue

        dn = count_deals(posted) + 1
        sp = "flash" if d.get("has_deal") or d["discount_percent"] >= FLASH_DEAL_PERCENT else None
        log("[PUB #{}] {} -{}% | {}".format(dn, cat, d["discount_percent"], d["title"][:40]))
        ok = send_telegram(format_deal(d, dn, sp), d.get("image_url"), make_share_button(d["asin"]))
        if ok:
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            pub += 1
            cat_count_cycle[cat] = cat_count_cycle.get(cat, 0) + 1
            recent_categories.append(cat)
            if len(recent_categories) > 3:
                recent_categories.pop(0)
            log("  [OK]")
            time.sleep(POST_INTERVAL_SECONDS)
        else:
            log("  [FAIL]")

    if skipped_for_cat:
        log("[SKIPPED per cap categoria]: {}".format(len(skipped_for_cat)))

    log("=" * 60)
    log("[RIEPILOGO] Pubblicate {} | Totale oggi: {}".format(pub, count_deals(posted)))
    log("=" * 60)


if __name__ == "__main__":
    main()
