"""
Sottocosto Oggi - Bot v35 ANTI-REPEAT + TECH PRIORITY
Novita' v35:
- ANTI-REPEAT con CHECK PREZZO: memoria estesa 14 giorni; se ASIN gia' pubblicato
  e prezzo NON cambiato (variazione <5%) -> SKIP. Se prezzo cambiato -> RIPROPOSTA
  con tag 💹PRICE-DROP nel log
- SMARTPHONE come fase dedicata garantita (era assente!)
  Keyword: iPhone 15/14, Galaxy S24/A55/Z, Pixel 8/9, Xiaomi, OnePlus...
- TECH premium garantita (audio/laptop/tablet/TV/gaming/wearable/foto)
  Keyword espanse: Sony WH-1000XM5, AirPods Pro, MacBook M3, iPad Pro,
  Apple Watch, PS5, Nintendo Switch OLED, GoPro, DJI...
- Pool aumentato a 160 (era 130) per dare spazio a tutte le fasi
- Fasi ricerca riorganizzate: 1=Deal, 2=Cucina, 3=Moda, 4=Sport, 5=Bellezza,
  6=Smartphone, 7=Tech, 8=Browse Nodes, 9=Generic, 10=Evening

Inerita da v34:
- Immagini brandate per Offerta del Giorno + offerte WOW (modulo opzionale)
- Intervallo 50s, peak/normal/low 8/6/4 + WOW boost +3
- BOOST WOW: sconto >=50% OPPURE brand TOP >=30%
- Brand premium PRIMA delle generic
- Lookup brand -> categoria
- 27 categorie, 22 browse nodes Amazon Italia
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

BOT_VERSION = "v35-ANTI-REPEAT-TECH"

# Modulo grafiche custom per offerte WOW (opzionale, fallback se non disponibile)
try:
    from post_image_module import generate_post_image
    BRANDED_IMAGES_ENABLED = True
except ImportError:
    BRANDED_IMAGES_ENABLED = False
    print("[WARN] post_image_module non trovato. Grafiche brandate disabilitate.")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

# ========== CONFIG v33 - BOOST DINAMICO ==========
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "10"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 9.0
MIN_RATING = 3.5
MIN_REVIEWS = 25
NO_RATING_MIN_PRICE = 20.0
MAX_DEALS_POOL = 160         # 160 (era 130) - spazio per tech+smartphone+browse+generic
POST_INTERVAL_SECONDS = 50   # 50s (era 60s) - copre piu' tempo per ciclo
MAX_MEMORY_SIZE = 2000   # aumentato da 500 a 2000 (memoria 14 giorni)
MEMORY_DAYS = 14         # giorni di storico ASIN+prezzo
PRICE_CHANGE_THRESHOLD = 5.0   # ripubblica se prezzo cambia di almeno 5%
MAX_PER_CATEGORY_POOL = 18   # 18 (era 15) - piu' offerte per categoria
WOW_DISCOUNT_THRESHOLD = 50  # sconto >= 50% = offerta WOW
WOW_TOP_BRAND_DISCOUNT = 30  # se brand TOP + sconto >= 30% = WOW
WOW_BOOST_PER_CYCLE = 3      # massimo 3 offerte WOW extra per ciclo

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
    """v33 OPZIONE B - BOOST DINAMICO.
    Tempo medio post: 50s, ciclo cron-job 10 min.

    Peak (8-9, 12-13, 20-22 IT): 8 base + fino a 3 WOW = max 11 post = 9 min coperti
    Normal (10-11, 14-15, 17-19): 6 base + fino a 3 WOW = max 9 post
    Low (7, 16, 23): 4 base + fino a 2 WOW = max 6 post

    Volume giornaliero atteso: ~210-230 post/giorno
    """
    if hour in (8, 9, 12, 13, 20, 21, 22):
        return 8  # peak
    if hour in (10, 11, 14, 15, 17, 18, 19):
        return 6  # normal
    return 4  # low (7, 16, 23)


def get_wow_boost(hour):
    """Quante offerte WOW extra puo' pubblicare oltre il limite normale."""
    if hour in (8, 9, 12, 13, 20, 21, 22):
        return 3  # peak: fino a +3 extra
    if hour in (10, 11, 14, 15, 17, 18, 19):
        return 3  # normal: fino a +3 extra
    return 2  # low: max +2 extra


def is_wow_deal(deal):
    """Identifica un'offerta WOW che merita boost di pubblicazione.
    Criteri:
    - Sconto >= 50% (offerte LAMPO)
    - OPPURE brand TOP con sconto >= 30%
    """
    pct = deal.get('discount_percent', 0)
    if pct >= WOW_DISCOUNT_THRESHOLD:
        return True
    if deal.get('brand_prio', 2) == 0 and pct >= WOW_TOP_BRAND_DISCOUNT:
        return True
    if deal.get('_is_active_deal'):  # Lightning Deal Amazon
        return True
    return False


# ============================================================
# REGOLE EDITORIALI - PRIORITA' CATEGORIE
# ============================================================

CATEGORY_PRIORITY = {
    # Priorita' 1 - massima (categorie hot, conversion alta)
    'casa_cucina': 1, 'cucina': 1, 'casaarredo': 1, 'faidate': 1,
    # Priorita' 2 - moda
    'moda': 2, 'abbigliamento': 2, 'scarpe': 2, 'borse': 2, 'gioielli': 2,
    # Priorita' 3 - sport
    'sport': 3,
    # Priorita' 4 - bellezza
    'bellezza': 4, 'curapersona': 4,
    # Priorita' 5 - elettronica e tech
    'audio': 5, 'smartphone': 5, 'tablet': 5, 'tv': 5,
    'wearable': 5, 'laptop': 5, 'gaming': 5, 'foto': 5, 'smarthome': 5,
    # Priorita' 6 - varie
    'bambini': 6, 'animali': 6,
    # Priorita' 7 - bassa
    'libri': 7, 'auto': 7, 'alimentari': 7, 'accessori': 7,
    # Default
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

SMARTPHONE_KEYWORDS = [
    # Smartphone Apple
    "iPhone 15", "iPhone 14", "iPhone 13", "iPhone 16",
    "iPhone Pro", "iPhone Plus", "iPhone Max",
    # Smartphone Samsung
    "Samsung Galaxy S24", "Samsung Galaxy S23", "Samsung Galaxy S25",
    "Samsung Galaxy A55", "Samsung Galaxy A35", "Samsung Galaxy A15",
    "Samsung Galaxy Z Flip", "Samsung Galaxy Z Fold",
    # Smartphone Google
    "Google Pixel 8", "Google Pixel 9", "Google Pixel 7",
    # Smartphone Xiaomi/Redmi (TOP cinesi piu' venduti)
    "Xiaomi 14", "Xiaomi 13", "Redmi Note 13", "Redmi Note 14",
    "Xiaomi Poco", "Xiaomi Mi",
    # OnePlus
    "OnePlus 12", "OnePlus 13", "OnePlus Nord",
    # Motorola / Honor
    "Motorola Edge", "Motorola Moto G",
    "Honor Magic", "Honor 200",
]

TECH_KEYWORDS = [
    # Audio brand TOP
    "Sony WH-1000XM5", "Sony WH-1000XM4", "Sony cuffie wireless",
    "Bose QuietComfort", "Bose Soundbar", "Bose cuffie",
    "Apple AirPods Pro", "AirPods Max", "AirPods 4",
    "Samsung Galaxy Buds", "JBL speaker bluetooth",
    "Sennheiser Momentum", "Beats Studio", "Marshall speaker",
    # Wearable
    "Apple Watch Series", "Apple Watch Ultra",
    "Samsung Galaxy Watch", "Garmin Forerunner", "Garmin Fenix",
    "Fitbit Versa", "Fitbit Charge",
    # Tablet / eReader
    "iPad Air", "iPad Pro", "iPad mini", "iPad 11",
    "Samsung Galaxy Tab S", "Samsung Galaxy Tab A",
    "Kindle Paperwhite", "Kindle Scribe", "Kindle Colorsoft",
    # Laptop
    "MacBook Air M3", "MacBook Pro M3", "MacBook M2",
    "Lenovo ThinkPad", "Lenovo IdeaPad", "Lenovo Legion",
    "HP Pavilion", "HP Envy", "HP Omen",
    "ASUS ZenBook", "ASUS ROG", "ASUS Vivobook",
    "Dell XPS", "Dell Inspiron",
    "Microsoft Surface", "Acer Aspire",
    # Smart home / TV
    "Echo Dot Alexa", "Echo Show", "Echo Hub",
    "Fire TV Stick 4K", "Fire TV Cube",
    "LG OLED 55", "LG OLED 65", "Samsung QLED 55", "Samsung QLED 65",
    "Sony Bravia OLED", "Hisense ULED",
    # Gaming
    "PlayStation 5 Slim", "PS5 controller", "DualSense",
    "Nintendo Switch OLED", "Xbox Series X", "Xbox Series S",
    # Foto/Video
    "GoPro Hero 12", "GoPro Hero 13", "DJI Mini 4", "DJI Osmo",
    "Insta360 X4",
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
    # ===== CASA, ARREDO, ELETTRODOMESTICI (priorita' editoriale 1) =====
    "Casa e cucina":                    "524015031",
    "Grandi elettrodomestici":          "412606031",
    "Illuminazione":                    "3155356031",

    # ===== FAI DA TE, GIARDINO (priorita' 1.5) =====
    "Fai da te":                        "524012031",
    "Giardino e giardinaggio":          "524013031",

    # ===== MODA, SCARPE, ACCESSORI (priorita' 2) =====
    "Moda":                             "524017031",
    "Scarpe e borse":                   "8463981031",
    "Valigeria":                        "1571282031",

    # ===== SPORT (priorita' 3) =====
    "Sport e tempo libero":             "524014031",

    # ===== BELLEZZA, SALUTE (priorita' 4) =====
    "Bellezza":                         "11962031",
    "Salute e cura della persona":      "524027031",

    # ===== INFANZIA, GIOCHI =====
    "Prima infanzia":                   "1571278031",
    "Giochi e giocattoli":              "412607031",

    # ===== ELETTRONICA (priorita' MENO alta, ne abbiamo gia' tanta) =====
    "Elettronica":                      "412609031",
    "Informatica":                      "412610031",
    "Videogiochi":                      "412603031",

    # ===== ANIMALI =====
    "Prodotti per animali":             "8606827031",

    # ===== LIBRI E MEDIA =====
    "Libri":                            "411663031",

    # ===== AUTO E MOTO =====
    "Auto e moto":                      "524011031",

    # ===== UFFICIO E CANCELLERIA =====
    "Cancelleria e prodotti per ufficio": "412602031",

    # ===== ALIMENTARI =====
    "Alimentari e cura della casa":     "6198082031",

    # ===== INDUSTRIA E SCIENZA =====
    "Commercio, Industria e Scienza":   "2454160031",
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


# ============================================================
# LOOKUP BRAND -> CATEGORIA (fallback per titoli ambigui)
# Esempio: "Vans Old Skool Rucksack" -> brand Vans = scarpe
#          "Tommy Hilfiger Pantaloncino" -> Tommy = abbigliamento
# ============================================================
BRAND_CATEGORY_LOOKUP = {
    # Scarpe sportive / casual
    "vans": "scarpe",
    "converse": "scarpe",
    "timberland": "scarpe",
    "doc martens": "scarpe",
    "dr. martens": "scarpe",
    "clarks": "scarpe",
    "geox": "scarpe",
    "crocs": "scarpe",
    "ugg": "scarpe",
    "birkenstock": "scarpe",
    "salomon": "scarpe",
    "asics": "scarpe",
    "brooks": "scarpe",
    "skechers": "scarpe",
    "diadora": "scarpe",

    # Abbigliamento brand
    "tommy hilfiger": "abbigliamento",
    "calvin klein": "abbigliamento",
    "ralph lauren": "abbigliamento",
    "polo ralph": "abbigliamento",
    "lacoste": "abbigliamento",
    "levi's": "abbigliamento",
    "levi ": "abbigliamento",
    "diesel": "abbigliamento",
    "hugo boss": "abbigliamento",
    "armani": "abbigliamento",
    "fred perry": "abbigliamento",
    "the north face": "abbigliamento",
    "patagonia": "abbigliamento",
    "columbia": "abbigliamento",
    "pinko": "abbigliamento",
    "liu jo": "abbigliamento",
    "guess uomo": "abbigliamento",
    "guess donna": "abbigliamento",
    "elisabetta franchi": "abbigliamento",

    # Borse / valigeria
    "michael kors": "borse",
    "furla": "borse",
    "coccinelle": "borse",
    "kipling": "borse",
    "samsonite": "borse",
    "american tourister": "borse",
    "eastpak": "borse",
    "roncato": "borse",
    "delsey": "borse",

    # Gioielli / orologi
    "pandora": "gioielli",
    "swarovski": "gioielli",
    "stroili": "gioielli",
    "fossil": "wearable",
    "cluse": "wearable",
    "casio": "wearable",
    "skagen": "wearable",
    "garmin": "wearable",
    "fitbit": "wearable",
    "amazfit": "wearable",
    "polar watch": "wearable",
    "huawei watch": "wearable",

    # Bellezza / profumi
    "kerastase": "bellezza",
    "loreal": "bellezza",
    "l'oreal": "bellezza",
    "olaplex": "bellezza",
    "garnier": "bellezza",
    "nivea": "bellezza",
    "estée lauder": "bellezza",
    "estee lauder": "bellezza",
    "lancôme": "bellezza",
    "lancome": "bellezza",
    "clinique": "bellezza",
    "biotherm": "bellezza",
    "vichy": "bellezza",
    "bioderma": "bellezza",
    "la roche posay": "bellezza",
    "maybelline": "bellezza",
    "nyx": "bellezza",
    "chanel": "bellezza",
    "dior": "bellezza",
    "mugler": "bellezza",
    "yves saint laurent": "bellezza",
    "versace profum": "bellezza",
    "calvin klein profum": "bellezza",
    "hugo boss profum": "bellezza",
    "ghd ": "curapersona",
    "babyliss": "curapersona",
    "remington": "curapersona",
    "philips sonicare": "curapersona",
    "oral-b": "curapersona",
    "oral b": "curapersona",

    # Cucina / casa
    "kitchenaid": "cucina",
    "de'longhi": "cucina",
    "delonghi": "cucina",
    "nespresso": "cucina",
    "tefal": "cucina",
    "le creuset": "cucina",
    "wmf": "cucina",
    "lagostina": "cucina",
    "russell hobbs": "cucina",
    "moulinex": "cucina",
    "kenwood": "cucina",
    "ninja foodi": "cucina",
    "ninja friggit": "cucina",
    "bialetti": "cucina",
    "smeg": "cucina",
    "krups": "cucina",

    # Casa/arredo brand
    "dyson": "casaarredo",
    "shark ": "casaarredo",
    "roborock": "casaarredo",
    "roomba": "casaarredo",
    "irobot": "casaarredo",
    "dreame": "casaarredo",
    "ecovacs": "casaarredo",
    "kärcher": "casaarredo",
    "karcher": "casaarredo",
    "rowenta": "casaarredo",
    "philips hue": "casaarredo",
    "yankee candle": "casaarredo",
    "emma materasso": "casaarredo",
    "tempur": "casaarredo",

    # Fai da te
    "bosch ": "faidate",
    "makita": "faidate",
    "dewalt": "faidate",
    "ryobi": "faidate",
    "einhell": "faidate",
    "stanley ": "faidate",
    "black & decker": "faidate",
    "black+decker": "faidate",

    # Sport
    "nike ": "sport",
    "adidas ": "sport",
    "puma ": "sport",
    "new balance": "sport",
    "under armour": "sport",
    "theragun": "sport",

    # Audio / cuffie
    "sony cuffi": "audio",
    "bose cuffi": "audio",
    "jbl ": "audio",
    "sennheiser": "audio",
    "airpods": "audio",
    "beats ": "audio",
    "marshall ": "audio",
    "skullcandy": "audio",
    "edifier": "audio",
    "anker soundcore": "audio",

    # Bambini / giocattoli
    "lego": "bambini",
    "playmobil": "bambini",
    "barbie": "bambini",
    "fisher price": "bambini",
    "fisher-price": "bambini",
    "chicco": "bambini",
    "philips avent": "bambini",
    "cybex": "bambini",
    "maxi cosi": "bambini",
    "inglesina": "bambini",
    "ravensburger": "bambini",
    "clementoni": "bambini",

    # Animali
    "royal canin": "animali",
    "hill's": "animali",
    "purina": "animali",
    "monge ": "animali",
    "schesir": "animali",
    "almo nature": "animali",

    # Foto / video
    "gopro": "foto",
    "dji ": "foto",
    "insta360": "foto",
    "canon eos": "foto",
    "sony alpha": "foto",
    "nikon ": "foto",

    # Gaming
    "playstation": "gaming",
    "nintendo switch": "gaming",
    "xbox ": "gaming",
    "razer ": "gaming",
    "steelseries": "gaming",
    "hyperx": "gaming",
    "elgato ": "gaming",

    # Smart home
    "echo dot": "smarthome",
    "echo show": "smarthome",
    "google nest": "smarthome",
    "ring videoc": "smarthome",
    "tp-link tapo": "smarthome",
    "fire tv stick": "tv",

    # Auto
    "michelin pneum": "auto",
    "nextbase": "auto",
}


def brand_to_category(title):
    """Cerca il brand nel titolo e ritorna la categoria associata.
    Ritorna None se nessun brand match."""
    t = title.lower()
    # Cerca brand piu' lungo prima (es. "tp-link tapo" prima di "tapo")
    sorted_brands = sorted(BRAND_CATEGORY_LOOKUP.keys(), key=len, reverse=True)
    for brand in sorted_brands:
        if brand in t:
            return BRAND_CATEGORY_LOOKUP[brand]
    return None


def create_api():
    return AmazonCreatorsApi(
        credential_id=AMAZON_CREDENTIAL_ID,
        credential_secret=AMAZON_CREDENTIAL_SECRET,
        version="3.2", tag=AMAZON_PARTNER_TAG,
        country=Country.IT, throttling=2.5,  # aumentato da 1.0 a 2.5 sec tra chiamate
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
    """Classificatore espanso per categorizzare correttamente i prodotti.
    Riduce drasticamente la categoria 'altro' dal 50% al 5-10%.
    """
    t = title.lower()

    # ===== SPORT / FITNESS / OUTDOOR (PRIMA del casaarredo per evitare collisioni "tappetin") =====
    if any(w in t for w in [
        "tappetino yoga", "yoga ", "running", "scarpe running", "scarpe corsa",
        "palestra", "manubri", "kettlebell", "elastici fitness",
        "panca fitness", "panca multifunzione",
        "bici ", "bicicletta", "casco bici", "luce bici",
        "tapis roulant", "ellittica", "cyclette",
        "trekking", "outdoor", "campeggio",
        "borraccia", "thermos sport", "ghiacciol sport",
        "pallone", "calcio pallone", "basket palla", "volley pallone",
        "racchett", "tennis ", "padel", "ping pong",
        "ski", "sci ", "snowboard",
        "monopattino", "scooter elettric", "hoverboard",
        "tenda campeggio", "sacco a pelo",
        "binocolo", "telescopio",
        "fascia elastic fitness", "barre fitness",
        "guantoni boxe", "guanti boxe", "pugilato",
        "salto corda", "elastico fitness",
    ]): return "sport"

    # ===== CUCINA / ELETTRODOMESTICI DA CUCINA =====
    if any(w in t for w in [
        "caffe", "caffè", "nespresso", "espresso", "moka", "bialetti",
        "friggitrice", "kitchenaid", "robot cucina", "pentole", "padell",
        "coltelli", "ceppo coltell", "frullator", "frullatore", "impastatric",
        "tefal", "le creuset", "wmf", "lagostina", "ballarini",
        "cuocipasta", "vaporier", "pentola pressione", "set posate",
        "mixer cucina", "spremiagrum", "centrifuga", "estrattore succh",
        "macchina pasta", "macinacaff", "tostapane", "bollitor",
        "robot multifunzione", "moulinex", "kenwood", "russell hobbs",
        "smeg", "delonghi", "de'longhi", "krups", "philips friggi",
        "ninja foodi", "ninja friggit", "magimix", "thermomix",
        "tagliere", "scolapasta", "ciotole", "stoviglie",
        "mestolo", "matterell", "mestoli",
    ]): return "cucina"

    # ===== CASA / ARREDO / PULIZIE =====
    if any(w in t for w in [
        "aspira", "aspirapolvere", "robot pulizia", "roomba", "roborock",
        "dreame", "dyson", "kärcher", "karcher", "shark", "rowenta",
        "scopa elettrica", "vapore", "vaporetto", "lavapavimenti",
        "lavavetri", "stiro", "stiratric", "ferro stiro",
        "deumidific", "umidific", "purificatore aria", "ionizzator",
        "ventilator", "climatizzator", "condizionator",
        "stuf", "termoventilator", "scaldabagno",
        "materass", "cuscin", "asciugamani", "copripiumino",
        "lenzuol", "piumino", "trapunt", "coperta", "plaid",
        "lampad", "candela", "tappeto", "passatoia",
        "hue", "lampadari", "applique", "led strip", "luci led",
        "tend", "tenda ", "bastone tend",
        "specchio", "porta-asciugamani",
        "organizer casa", "scaffal", "armadio", "cassettier", "comò",
        "comodino", "sedia ufficio", "sedia gaming", "poltrona",
        "divano", "tavolo", "tavolino",
        "letto", "rete letto", "doghe",
        "porta", "appendiabit", "attaccapanni",
        "bilancia cucina", "bilancia pesapersone",
        "pattumiera", "bidone", "spazzolone",
        "scopa", "secchio", "panno", "microfibr",
        "detersivo", "ammorbidente", "sapone piatti",
    ]): return "casaarredo"

    # ===== FAI DA TE / GIARDINO =====
    if any(w in t for w in [
        "trapano", "avvitatore", "smerigliatrice", "saldatric",
        "decespugliator", "tagliasiep", "tagliaerba", "soffiatore",
        "idropulitric", "compressor", "cassetta attrezz",
        "bosch professional", "makita", "dewalt", "ryobi", "einhell",
        "stihl", "fiskars",
        "viti ", "chiavi inglese", "tronchese", "pinz",
        "barbecue", "bbq", "weber",
        "annaffiatoi", "irrigazione", "tubo giardin",
        "concime", "vaso pianta", "vasi giardin",
        "fioriera",
    ]): return "faidate"

    # ===== SCARPE =====
    if any(w in t for w in [
        "scarp", "sneaker", "stival", "ciabatt", "sandal", "birkenstock",
        "decollet", "ballerin", "mocassini", "espadrillas",
        "scarponi", "anfibi", "infradito", "ugg", "crocs",
        "scarpetta",
    ]): return "scarpe"

    # ===== ABBIGLIAMENTO =====
    if any(w in t for w in [
        "jeans", "camicia", "camicie", "magliett", "t-shirt", "tshirt",
        "felpa", "felpe", "giacca", "giubbott", "cappott", "trench",
        "pantalo", "pantaloncin", "shorts",
        "vestit", "abito", "abiti donna", "abiti uomo",
        "gonna", "gonne",
        "maglion", "cardigan", "polo ", "polo da",
        "tuta sportiva", "tuta uomo", "tuta donna",
        "intim", "intimo", "boxer", "slip", "reggiseno", "perizoma",
        "calz", "calze", "calzin", "canottiera",
        "pigiama", "vestaglia", "accappatoi",
        "costume", "bikini", "trikini",
        "tommy hilfig", "calvin klein", "levi's", "levi",
        "polo ralph", "lacoste", "fred perry", "guess uomo", "guess donna",
        "diesel", "armani", "hugo boss", "boss uomo",
        "north face", "patagonia",
        "pinko", "liu jo", "elisabetta franchi",
    ]): return "abbigliamento"

    # ===== BORSE / VALIGIE / ACCESSORI =====
    if any(w in t for w in [
        "borsa", "borsetta", "borsone", "tracoll", "shopping bag",
        "zaino", "zainetto", "trolley", "valigia", "valigeria",
        "portafoglio", "portafogli", "porta carte",
        "cintura", "cinture",
        "guanti", "sciarp", "sciarpa", "cappell", "berretto",
        "ombrello",
        "samsonite", "american tourister", "eastpak",
        "michael kors", "furla", "coccinelle",
    ]): return "borse"

    # ===== GIOIELLI / OROLOGI =====
    if any(w in t for w in [
        "gioiell", "collana", "braccial", "anello", "orecchini",
        "pandora", "swarovski", "stroili",
        "argento 925", "oro 18kt", "oro giallo",
        "orologio donna", "orologio uomo", "fossil", "cluse",
        "casio", "skagen",
    ]): return "gioielli"

    # ===== BELLEZZA / COSMETICI =====
    if any(w in t for w in [
        "profum", "fragranza", "eau de parfum", "eau de toilette",
        "trucco", "makeup", "make up", "cosmet",
        "siero", "shampoo", "balsamo capell", "maschera capell",
        "crema viso", "crema corpo", "crema mani", "crema antiet",
        "maschera viso", "patch viso", "contorno occhi",
        "palette ombretti", "ombrett", "rossetto", "rossetti",
        "fondotint", "cipria", "blush", "correttor",
        "mascara", "eyeliner", "matita occhi", "matita labbr",
        "smalto unghie", "smalto", "lima unghie",
        "tonico viso", "detergente viso", "struccante",
        "acido ialuronico", "vitamina c siero", "retinolo",
        "olio corpo", "olio capell",
        "rasatura", "barber", "balsamo barba",
        "deodorante", "antitraspirante",
        "bagno schiuma", "doccia schiuma",
        "lacca capelli", "spray capell",
        "tinta capelli", "henn",
        "ciglia finte", "extension ciglia",
        "kerastase", "loreal", "l'oreal", "olaplex", "garnier",
        "nivea", "estée lauder", "estee lauder", "lancôme", "lancome",
        "clinique", "dior", "chanel", "yves saint laurent",
        "biotherm", "vichy", "bioderma", "la roche posay",
        "maybelline", "nyx", "mac cosmetics",
        "mugler", "calvin klein profum", "hugo boss profum",
    ]): return "bellezza"

    # ===== CURA PERSONA =====
    if any(w in t for w in [
        "rasoio elettric", "rasoio", "regolabarb", "tagliacapell",
        "spazzolino elettric", "oral-b", "oral b", "sonicare",
        "asciugacapell", "phon ", "piastra capell", "piastra per capell",
        "arricciacapelli", "ferro arriccia", "ghd",
        "epilator", "epilazione",
        "depilator", "ceretta", "rasoio donna",
        "termometro", "saturimetro", "misuratore pressione", "pulsoss",
        "bilancia digitale", "bilancia smart",
        "massaggi", "theragun", "pistola massagg",
        "spazzolino dent", "filo interdent", "collutorio",
        "dyson airwrap", "dyson supersonic",
        "babyliss", "remington",
        "panties", "pannolini",
    ]): return "curapersona"

    # ===== AUDIO / CUFFIE / SPEAKER =====
    if any(w in t for w in [
        "cuffi", "cuffia", "headphone",
        "speaker", "altoparlante", "altoparlanti",
        "auricolar", "auricolare",
        "audio bluetooth", "soundbar", "barra audio",
        "earbuds", "ear buds", "airpods", "buds",
        "subwoofer", "amplificator audio",
        "sony cuffi", "bose cuffi", "jbl ", "sennheiser",
        "marshall ", "beats ", "skullcandy",
        "anker soundcore", "edifier",
    ]): return "audio"

    # ===== SMARTWATCH / WEARABLE =====
    if any(w in t for w in [
        "smartwatch", "smart watch", "fitness tracker", "fitness band",
        "garmin", "fitbit", "amazfit", "huawei watch",
        "apple watch", "galaxy watch",
        "polar watch", "tomtom",
    ]): return "wearable"

    # ===== SMARTPHONE =====
    if any(w in t for w in [
        "iphone", "smartphone", "cellulare",
        "galaxy s2", "galaxy s1", "galaxy s9", "galaxy a5", "galaxy a3",
        "pixel ", "google pixel",
        "xiaomi redmi", "redmi note", "xiaomi mi ",
        "oneplus", "motorola moto",
        "honor smartphone", "realme",
    ]): return "smartphone"

    # ===== LAPTOP / COMPUTER =====
    if any(w in t for w in [
        "laptop", "notebook", "macbook", "portatil",
        "ultrabook", "chromebook",
        "pc desktop", "pc fisso", "tower gaming",
        "tastiera ", "mouse ", "webcam",
        "monitor pc", "monitor 24", "monitor 27", "monitor 32",
        "monitor curvo", "monitor gaming", "monitor 4k",
        "stampante", "scanner",
        "router", "wifi router", "mesh wifi", "extender wifi",
        "ssd ", "ssd nvme", "hard disk", "hdd ",
        "ram ", "memoria ram", "ddr4", "ddr5",
        "scheda video", "rtx", "geforce", "radeon",
        "cpu ", "processore ",
        "case pc", "ventol", "dissipator",
        "alimentator pc",
    ]): return "laptop"

    # ===== TABLET / EREADER =====
    if any(w in t for w in [
        "tablet", "ipad", "kindle paperwhite", "kindle scribe",
        "fire hd", "ereader", "e-reader",
        "lenovo tab", "samsung tab",
        "apple pencil", "stilo tablet",
    ]): return "tablet"

    # ===== TV / VIDEO =====
    if any(w in t for w in [
        "tv ", " tv,", "television", "televisor",
        "smart tv", "oled", "qled", "neo qled",
        "fire tv stick", "fire tv", "chromecast", "apple tv",
        "proiettor", "videoproiettor", "telo proiettore",
    ]): return "tv"

    # ===== FOTO / VIDEO =====
    if any(w in t for w in [
        "fotocamera", "macchina fotograf", "reflex",
        "gopro", "drone", "dji ", "insta360",
        "obiettiv", "ring light", "luce video",
        "treppiede", "treppiedi", "gimbal",
        "microfono streaming",
    ]): return "foto"

    # ===== GAMING / CONSOLE =====
    if any(w in t for w in [
        "playstation", "ps5 ", "ps4 ", "ps5,",
        "xbox", "nintendo switch", "switch oled",
        "controller wireless", "joypad", "joystick",
        "videogioco", "gioco ps5", "gioco xbox", "gioco nintendo",
        "gaming chair", "sedia gaming",
        "razer ", "logitech g", "steelseries", "hyperx",
        "elgato ", "stream deck",
        "mouse gaming", "tastiera gaming",
    ]): return "gaming"

    # ===== SMART HOME =====
    if any(w in t for w in [
        "alexa", "echo dot", "echo show", "echo studio",
        "google nest", "google home",
        "philips hue", "ring videoc", "domotica",
        "tapo ", "tp-link tapo", "smart plug", "presa smart",
        "videocamera sorveglianza", "telecamera ip",
        "videocitofono",
        "termostato smart", "nest thermostat",
        "campanello smart",
    ]): return "smarthome"

    # ===== BAMBINI / GIOCATTOLI =====
    if any(w in t for w in [
        "lego", "barbie", "puzzle ", "peluche", "playmobil",
        "passeggino", "seggiolino auto", "ovetto",
        "biberon", "tiralatte", "fasciatoi",
        "pannolin",
        "giocattol", "giocattolo", "gioco bambini",
        "monopoly", "risiko", "scarabeo", "gioco da tavolo",
        "trenino", "macchinina", "modellini",
        "puzzle 1000", "puzzle ravensb",
        "lego star wars", "lego harry potter", "lego friends",
        "fisher price", "chicco", "imaginarium", "clementoni",
        "hot wheels", "playmobil", "barbie",
    ]): return "bambini"

    # ===== ANIMALI =====
    if any(w in t for w in [
        "cane ", "cani ", "cucciol", "guinzaglio", "pettorina",
        "gatto ", "gatti", "tiragraffi", "lettiera",
        "crocchin", "crocchett", "royal canin", "hill's", "purina",
        "monge", "schesir", "almo nature",
        "pesci acquario", "acquario",
        "uccelli", "criceto", "tartaruga", "conigli",
        "cuccia", "trasportin animal",
        "antipulci", "anti zecche",
    ]): return "animali"

    # ===== LIBRI / CANCELLERIA =====
    if any(w in t for w in [
        "libro", "libri ", "romanzo", "saggio",
        "agenda ", "quaderno", "blocchetto",
        "penna", "penne ", "matita", "pennarell",
        "evidenziator", "gomma cancell",
        "raccoglitor", "classificator",
        "cartelletta", "porta document",
        "post-it", "post it",
        "calcolatrice", "calcolatori",
        "scotch", "nastro adesiv", "graffette", "punti metall",
    ]): return "libri"

    # ===== AUTO / MOTO =====
    if any(w in t for w in [
        "dashcam", "telecamera auto",
        "pneumatici", "gomme auto", "michelin pneum",
        "tergicristall", "lampadine auto",
        "compressor auto", "gonfiagomme",
        "tappetini auto", "copertura auto", "telone auto",
        "olio motore", "additiv",
        "supporto telefono auto", "caricatore auto",
        "casco moto", "guanti moto", "giacca moto",
    ]): return "auto"

    # ===== ALIMENTARI =====
    if any(w in t for w in [
        "caff in capsul", "capsule caff", "cialde caff",
        "tisana", "te in bustin", "tè verde",
        "pasta confezione", "riso ", "farina ",
        "olio oliva", "olio extraver",
        "biscotti", "cioccolato", "crema spalmabile",
        "miele ", "marmellata",
        "vino ", "spumante", "champagne",
        "birra ", "whisky", "vodka", "gin",
        "integrator", "proteine in polvere", "barrette proteic",
        "vitamine multi",
    ]): return "alimentari"

    # ===== ACCESSORI TECH =====
    if any(w in t for w in [
        "caricatore", "caricabatter", "alimentator",
        "power bank", "powerbank", "batteria esterna",
        "cavo usb", "cavo lightning", "cavo type-c", "cavo hdmi",
        "hub usb", "adattator", "docking station",
        "anker ", "ugreen ", "belkin",
        "custodia iphone", "custodia samsung", "cover smartphone",
        "vetro temperato", "pellicola schermo",
        "supporto telefono", "treppiede smartphone",
        "lettore sd", "lettore card",
        "microsd", "scheda sd",
        "ricetrasmittente", "walkie talkie",
        "telecomando universal",
    ]): return "accessori"

    # ===== FALLBACK BRAND LOOKUP =====
    # Se le keyword non hanno matchato, prova a classificare dal brand
    # Esempio: "Vans Old Skool Rucksack" -> Vans = scarpe (anche se rucksack non c'e' in nessuna keyword sopra)
    brand_cat = brand_to_category(title)
    if brand_cat:
        return brand_cat

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
        "cucina": "\U0001f373",         # 🍳
        "casaarredo": "\U0001f6cb",     # 🛋️
        "faidate": "\U0001f527",        # 🔧
        "scarpe": "\U0001f45f",         # 👟
        "abbigliamento": "\U0001f455",  # 👕
        "borse": "\U0001f45c",          # 👜
        "gioielli": "\U0001f48d",       # 💍
        "bellezza": "\U0001f484",       # 💄
        "curapersona": "\U0001f488",    # 💈
        "sport": "\U0001f3cb",          # 🏋️
        "audio": "\U0001f3a7",          # 🎧
        "wearable": "\u231a",           # ⌚
        "smartphone": "\U0001f4f1",     # 📱
        "laptop": "\U0001f4bb",         # 💻
        "tablet": "\U0001f4f2",         # 📲
        "tv": "\U0001f4fa",             # 📺
        "foto": "\U0001f4f7",           # 📷
        "gaming": "\U0001f3ae",         # 🎮
        "smarthome": "\U0001f3e0",      # 🏠
        "bambini": "\U0001f9f8",        # 🧸
        "animali": "\U0001f436",        # 🐶
        "libri": "\U0001f4d6",          # 📖
        "auto": "\U0001f697",           # 🚗
        "alimentari": "\U0001f96b",     # 🥫
        "accessori": "\U0001f50b",      # 🔋
        "altro": "\U0001f4e6",          # 📦
    }
    return emojis.get(cat, "\U0001f4e6")


def get_category_hashtag(title):
    cat = get_deal_category(title)
    tags = {
        "cucina": "#cucina",
        "casaarredo": "#casa",
        "faidate": "#faidate",
        "scarpe": "#scarpe",
        "abbigliamento": "#moda",
        "borse": "#borse",
        "gioielli": "#gioielli",
        "bellezza": "#bellezza",
        "curapersona": "#curapersona",
        "sport": "#sport",
        "audio": "#audio",
        "wearable": "#wearable",
        "smartphone": "#smartphone",
        "laptop": "#laptop",
        "tablet": "#tablet",
        "tv": "#tv",
        "foto": "#foto",
        "gaming": "#gaming",
        "smarthome": "#smarthome",
        "bambini": "#bambini",
        "animali": "#animali",
        "libri": "#libri",
        "auto": "#auto",
        "alimentari": "#alimentari",
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


def send_telegram_branded(text, deal, reply_markup=None):
    """Invia un post Telegram con immagine BRANDATA custom (per offerte WOW).
    Fallback automatico su send_telegram con image_url se la generazione fallisce.
    """
    if not BRANDED_IMAGES_ENABLED:
        return send_telegram(text, deal.get("image_url"), reply_markup)

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        success = generate_post_image(deal, tmp_path)
        if not success:
            log("  [BRAND_FAIL] fallback su immagine Amazon")
            return send_telegram(text, deal.get("image_url"), reply_markup)

        base = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
        with open(tmp_path, "rb") as f:
            files = {"photo": ("post.png", f, "image/png")}
            data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": text, "parse_mode": "HTML"}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            r = requests.post("{}/sendPhoto".format(base), data=data, files=files, timeout=30)
            j = r.json()

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if j.get("ok"):
            log("  [BRANDED] immagine custom inviata")
            return True
        log("  [TG_FAIL] branded: {}".format(j.get("description", "??")))
        return send_telegram(text, deal.get("image_url"), reply_markup)
    except Exception as e:
        log("  [BRAND_ERR] {} - fallback".format(e))
        return send_telegram(text, deal.get("image_url"), reply_markup)


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
    """Carica memoria pubblicazioni.

    Nuovo formato (v34.1+):
      { "2026-06-04": { "ASIN1": {"price": 29.99, "ts": "..."}, ... }, "_am": [...] }
    Formato vecchio (compat):
      { "2026-06-04": ["ASIN1", "ASIN2", ...] }
    """
    try:
        data = json.loads(POSTED_FILE.read_text()) if POSTED_FILE.exists() else {}
        if not isinstance(data, dict):
            return {}

        # Estende memoria a MEMORY_DAYS (era 1 giorno)
        cutoff = (datetime.date.today() - datetime.timedelta(days=MEMORY_DAYS)).isoformat()
        filtered = {k: v for k, v in data.items() if k >= cutoff}

        # CONTA ASIN totali (esclude marker speciali _am, _top, ecc)
        total_asins = 0
        for day_key, day_data in filtered.items():
            if isinstance(day_data, dict):
                total_asins += len([k for k in day_data.keys() if not k.startswith("_")])
            elif isinstance(day_data, list):
                total_asins += len([k for k in day_data if not k.startswith("_")])

        if total_asins > MAX_MEMORY_SIZE:
            # Tieni solo gli ultimi 7 giorni invece di MEMORY_DAYS
            cutoff_emergency = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            filtered = {k: v for k, v in filtered.items() if k >= cutoff_emergency}
            log("[CLEAN] Memoria piena ({} ASIN). Ridotta a 7 giorni.".format(total_asins))

        return filtered
    except Exception as e:
        log("[ERR] load_posted: {}".format(e))
        return {}


def save_posted(p):
    POSTED_FILE.write_text(json.dumps(p))


def get_posted_info(p, asin):
    """Cerca un ASIN nelle pubblicazioni recenti.
    Ritorna {price, ts, days_ago} o None se mai pubblicato.
    """
    today = datetime.date.today()
    for day_key in sorted(p.keys(), reverse=True):
        if day_key.startswith("_"):
            continue
        day_data = p[day_key]
        # Compat: se e' lista (vecchio formato), ritorna info senza prezzo
        if isinstance(day_data, list):
            if asin in day_data:
                try:
                    d = datetime.date.fromisoformat(day_key)
                    return {"price": None, "ts": day_key, "days_ago": (today - d).days}
                except Exception:
                    return {"price": None, "ts": day_key, "days_ago": 0}
        # Nuovo formato dict
        elif isinstance(day_data, dict):
            if asin in day_data and not asin.startswith("_"):
                info = day_data[asin]
                if isinstance(info, dict):
                    try:
                        d = datetime.date.fromisoformat(day_key)
                        days_ago = (today - d).days
                    except Exception:
                        days_ago = 0
                    return {
                        "price": info.get("price"),
                        "ts": info.get("ts", day_key),
                        "days_ago": days_ago,
                    }
                # Compat: se valore non e' dict (es. None)
                else:
                    return {"price": None, "ts": day_key, "days_ago": 0}
    return None


def is_posted(p, k):
    """Backwards-compat: check semplice se ASIN gia' pubblicato."""
    return get_posted_info(p, k) is not None


def should_skip_repost(p, deal):
    """Decide se l'offerta va saltata perche' gia' vista e prezzo non cambiato.

    Ritorna (skip: bool, reason: str)
    - True, "first_time" -> non e' mai stato pubblicato (NON skip)
    - True, "same_price_recent" -> stesso prezzo, gia' pubblicato di recente
    - True, "price_changed" -> prezzo cambiato significativamente, RIPROPOSTA
    """
    asin = deal["asin"]
    info = get_posted_info(p, asin)
    if info is None:
        return False, "first_time"

    # Se non abbiamo info sul prezzo (vecchio formato), skippa per sicurezza
    if info["price"] is None:
        # Se sono passati piu' di 7 giorni, ripropone
        if info["days_ago"] >= 7:
            return False, "old_post_no_price"
        return True, "no_price_data"

    # Calcola variazione prezzo
    old_price = float(info["price"])
    new_price = float(deal["current_price"])
    if old_price <= 0:
        return False, "invalid_old_price"

    price_change_pct = (old_price - new_price) / old_price * 100

    if price_change_pct >= PRICE_CHANGE_THRESHOLD:
        # Solo un ribasso significativo giustifica la ripubblicazione
        direction = "↓" if new_price < old_price else "↑"
        return False, "price_changed_{:.1f}pct_{}".format(price_change_pct, direction)
    else:
        # Stesso prezzo, gia' visto -> skip
        return True, "same_price_{}d_ago".format(info["days_ago"])


def mark_posted(p, k, price=None):
    """Salva un ASIN nelle pubblicazioni di oggi con timestamp e prezzo.

    Per i marker speciali (es. "_am", "_top") mantiene la struttura lista.
    Per gli ASIN reali usa dict {price, ts}.
    """
    today = datetime.date.today().isoformat()
    if today not in p:
        p[today] = {}

    # Compat: se oggi e' lista, convertila in dict
    if isinstance(p[today], list):
        new_today = {}
        for x in p[today]:
            if x.startswith("_"):
                new_today[x] = True  # marker speciale
            else:
                new_today[x] = {"price": None, "ts": today}
        p[today] = new_today

    if k.startswith("_"):
        p[today][k] = True  # marker speciale
    else:
        # ASIN reale: salva prezzo e timestamp
        p[today][k] = {
            "price": price,
            "ts": datetime.datetime.now().isoformat()[:19],
        }


def count_deals(p):
    today = datetime.date.today().isoformat()
    day_data = p.get(today, {})
    if isinstance(day_data, list):
        return len([k for k in day_data if not k.startswith("_")])
    elif isinstance(day_data, dict):
        return len([k for k in day_data.keys() if not k.startswith("_")])
    return 0


def is_special_posted(p, k):
    today = datetime.date.today().isoformat()
    day_data = p.get(today, {})
    if isinstance(day_data, list):
        return k in day_data
    elif isinstance(day_data, dict):
        return k in day_data
    return False


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
    seen = set()  # solo ASIN gia' visti in QUESTO ciclo (anti-duplicato fasi)
    log("[POOL] Memoria: {} giorni storici".format(MEMORY_DAYS))

    # Cap per categoria nel pool: evita squilibri come casaarredo=42 vs cucina=9
    cat_count_pool = {}
    skipped_same_price = 0  # contatore offerte saltate per stesso prezzo
    accepted_price_change = 0  # offerte accettate per prezzo cambiato

    def can_add_to_pool(d):
        """Verifica se l'offerta puo' entrare nel pool senza superare il cap di categoria."""
        cat = get_deal_category(d["title"])
        if cat_count_pool.get(cat, 0) >= MAX_PER_CATEGORY_POOL:
            return False
        return True

    def check_price_history(d):
        """Verifica se l'offerta va inclusa basandosi sul price history.

        Ritorna True se va inclusa, False se va skippata.
        """
        nonlocal skipped_same_price, accepted_price_change
        skip, reason = should_skip_repost(posted, d)
        if skip:
            skipped_same_price += 1
            return False
        if "price_changed" in reason:
            accepted_price_change += 1
            d["_price_changed"] = True  # marca per logging
        return True

    def add_to_pool(d, source_kw):
        cat = get_deal_category(d["title"])
        seen.add(d["asin"])
        d["_kw"] = source_kw
        all_deals.append(d)
        cat_count_pool[cat] = cat_count_pool.get(cat, 0) + 1

    def search_phase(name, keywords):
        log("=== FASE {}: {} kw ===".format(name, len(keywords)))
        for kw in keywords:
            if len(all_deals) >= MAX_DEALS_POOL:
                break
            deals_found = search_deals(api, keyword=kw)
            new_count = 0
            skipped_cap = 0
            skipped_repost = 0
            for d in deals_found:
                if d["asin"] in seen:
                    continue
                if len(all_deals) >= MAX_DEALS_POOL:
                    break
                # CHECK PREZZO: salta se gia' pubblicato di recente allo stesso prezzo
                if not check_price_history(d):
                    skipped_repost += 1
                    seen.add(d["asin"])  # evita ricontrollarlo nel ciclo
                    continue
                if not can_add_to_pool(d):
                    skipped_cap += 1
                    continue
                add_to_pool(d, kw)
                new_count += 1
            if new_count > 0:
                extras = []
                if skipped_cap > 0:
                    extras.append("cap:{}".format(skipped_cap))
                if skipped_repost > 0:
                    extras.append("repost:{}".format(skipped_repost))
                suffix = " ({})".format(", ".join(extras)) if extras else ""
                log("  [{}] -> {}{}".format(kw[:30], new_count, suffix))

    def search_browse_nodes_phase(name, nodes_dict, max_nodes_per_cycle=None):
        """Cerca per browse_node_id. Restituisce TUTTO il catalogo di una categoria.

        max_nodes_per_cycle: limita quanti nodi interrogare per ciclo
        (utile per evitare rate limit dell'API).
        """
        items = list(nodes_dict.items())
        random.shuffle(items)

        if max_nodes_per_cycle and len(items) > max_nodes_per_cycle:
            items = items[:max_nodes_per_cycle]

        log("=== FASE {}: {} browse nodes (di {} totali) ===".format(
            name, len(items), len(nodes_dict)))

        for cat_name, node_id in items:
            if len(all_deals) >= MAX_DEALS_POOL:
                break
            deals_found = search_deals(api, browse_node_id=node_id, max_results=10)
            new_count = 0
            skipped_cap = 0
            skipped_repost = 0
            for d in deals_found:
                if d["asin"] in seen:
                    continue
                if len(all_deals) >= MAX_DEALS_POOL:
                    break
                if not check_price_history(d):
                    skipped_repost += 1
                    seen.add(d["asin"])
                    continue
                if not can_add_to_pool(d):
                    skipped_cap += 1
                    continue
                add_to_pool(d, "BROWSE:{}".format(cat_name))
                new_count += 1
            if new_count > 0:
                log("  [BROWSE: {}] -> {}".format(cat_name[:30], new_count))

    # FASE 1: Deal attivi (NO cap categoria - i deal attivi hanno sempre priorita')
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
            # Check price history anche per deal attivi
            if not check_price_history(d):
                seen.add(d["asin"])
                continue
            seen.add(d["asin"])
            d["_kw"] = kw
            d["_is_active_deal"] = True
            all_deals.append(d)
            cat = get_deal_category(d["title"])
            cat_count_pool[cat] = cat_count_pool.get(cat, 0) + 1
            new_count += 1
        if new_count > 0:
            log("  [DEAL: {}] -> {}".format(kw, new_count))
    log("[POOL] Dopo F1: {}".format(len(all_deals)))

    # ===========================================
    # ===========================================
    # FASE 2-5: BRAND PREMIUM (prima di tutto, per pescare i top brand)
    # Cosi i brand TOP (KitchenAid, Tommy, Nike, L'Oreal...) sono SEMPRE nel pool
    # ===========================================
    house_shuffled = list(HOUSE_KITCHEN_KEYWORDS)
    random.shuffle(house_shuffled)
    # Limita a 10 keyword per fase (evita di saturare il pool con una sola categoria)
    search_phase("2 CASA/CUCINA brand premium", house_shuffled[:10])
    log("[POOL] Dopo F2: {}".format(len(all_deals)))

    fashion_shuffled = list(FASHION_KEYWORDS)
    random.shuffle(fashion_shuffled)
    search_phase("3 MODA brand premium", fashion_shuffled[:10])
    log("[POOL] Dopo F3: {}".format(len(all_deals)))

    sport_shuffled = list(SPORT_KEYWORDS)
    random.shuffle(sport_shuffled)
    search_phase("4 SPORT brand premium", sport_shuffled[:8])
    log("[POOL] Dopo F4: {}".format(len(all_deals)))

    beauty_shuffled = list(BEAUTY_KEYWORDS)
    random.shuffle(beauty_shuffled)
    search_phase("5 BELLEZZA brand premium", beauty_shuffled[:10])
    log("[POOL] Dopo F5: {}".format(len(all_deals)))

    # ===========================================
    # FASE 6: SMARTPHONE PREMIUM (esecuzione GARANTITA, prima dei browse)
    # iPhone, Galaxy S/A, Pixel, Xiaomi, OnePlus, Motorola, Honor
    # ===========================================
    smartphone_shuffled = list(SMARTPHONE_KEYWORDS)
    random.shuffle(smartphone_shuffled)
    search_phase("6 SMARTPHONE premium", smartphone_shuffled[:12])
    log("[POOL] Dopo F6 (smartphone): {}".format(len(all_deals)))

    # ===========================================
    # FASE 7: TECH PREMIUM (esecuzione GARANTITA - audio, wearable, laptop, tablet, TV, gaming)
    # Sony, Bose, AirPods, MacBook, iPad, PS5, Nintendo, Garmin
    # ===========================================
    tech_shuffled = list(TECH_KEYWORDS)
    random.shuffle(tech_shuffled)
    search_phase("7 TECH premium (audio/laptop/TV/gaming)", tech_shuffled[:14])
    log("[POOL] Dopo F7 (tech): {}".format(len(all_deals)))

    # ===========================================
    # FASE 8: BROWSE NODES - cattura il catalogo per categoria
    # Limitato a 10 nodi shufflati per ciclo (evita rate limit)
    # ===========================================
    search_browse_nodes_phase("8 BROWSE NODES (catalogo per categoria)",
                              AMAZON_IT_BROWSE_NODES, max_nodes_per_cycle=10)
    log("[POOL] Dopo F8 (browse): {}".format(len(all_deals)))

    # ===========================================
    # FASE 9: KEYWORD GENERICHE - prodotti senza brand-bias
    # Solo se il pool ha ancora spazio
    # ===========================================
    if len(all_deals) < MAX_DEALS_POOL:
        # Shuffla le generiche e prendi le prime 20 per non saturare
        generic_shuffled = list(GENERIC_KEYWORDS)
        random.shuffle(generic_shuffled)
        search_phase("9 GENERIC (prodotti senza brand bias)", generic_shuffled[:20])
        log("[POOL] Dopo F9 (generic): {}".format(len(all_deals)))

    # ===========================================
    # FASE 10: EVENING - se sera e pool basso
    # ===========================================
    if hour >= 19 and len(all_deals) < max_posts_cycle * 4:
        search_phase("10 EVENING", EVENING_KEYWORDS)

    log("=" * 60)
    log("[POOL FINALE] {} candidati | max post ciclo: {}".format(len(all_deals), max_posts_cycle))
    log("[ANTI-REPEAT] saltate {} offerte gia' pubblicate stesso prezzo | accettate {} per prezzo cambiato".format(
        skipped_same_price, accepted_price_change))

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

    # ===== TOP DEL GIORNO (con immagine BRANDATA) =====
    if hour >= 9 and not is_special_posted(posted, "_top"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        log("[TOP] -{}% | {}".format(best["discount_percent"], best["title"][:50]))
        ok = send_telegram_branded(
            format_deal(best, special="top"),
            best,
            make_share_button(best["asin"])
        )
        if ok:
            mark_posted(posted, best["asin"], price=best["current_price"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            log("[OK] Top pubblicato!")
            time.sleep(POST_INTERVAL_SECONDS)

    # ===== PUBBLICAZIONE CON BOOST WOW =====
    # Logica v33:
    # - Base: max N post per ciclo (peak=8, normal=6, low=4)
    # - Boost: fino a +3 post EXTRA se sono offerte WOW (>=50% sconto o brand TOP >=30%)
    # - Max assoluto: base + boost (peak=11, normal=9, low=6)
    pub = 0
    wow_pub = 0  # contatore offerte WOW gia' pubblicate (per limite boost)
    cat_count_cycle = {}
    MAX_PER_CAT_CYCLE = 1  # max 1 offerta stessa categoria per ciclo (per non spammare)
    wow_boost_max = get_wow_boost(hour)
    skipped_for_cat = []
    skipped_for_repeat = []

    # Recupera le ultime 3 categorie pubblicate oggi
    recent_categories = []
    try:
        today_stats = load_stats().get(today, [])
        for d in today_stats[-3:]:
            recent_categories.append(get_deal_category(d["title"]))
        log("[ULTIME 3 CATEGORIE PUBBLICATE OGGI]: {}".format(recent_categories))
    except Exception:
        pass

    log("[PUBLISH] base={} | wow_boost_max={} | totale max={} (peak hour={})".format(
        max_posts_cycle, wow_boost_max, max_posts_cycle + wow_boost_max, hour))

    for d in all_deals:
        # STOP se ho raggiunto base + tutto il boost WOW disponibile
        if pub >= max_posts_cycle + wow_boost_max:
            log("[STOP] Limite totale ciclo: {} (base {} + wow {}/{})".format(
                pub, max_posts_cycle, wow_pub, wow_boost_max))
            break

        if not is_publish_time():
            break

        if is_posted(posted, d["asin"]):
            continue

        cat = get_deal_category(d["title"])
        is_wow = is_wow_deal(d)

        # Se ho gia' raggiunto la base normale, accetto SOLO offerte WOW
        if pub >= max_posts_cycle:
            if not is_wow:
                continue  # skip silenzioso, le NON-WOW non passano il limite
            if wow_pub >= wow_boost_max:
                log("[STOP] Limite WOW raggiunto: {}".format(wow_pub))
                break

        # CAP per categoria nel ciclo (no piu' di 1 per categoria)
        if cat_count_cycle.get(cat, 0) >= MAX_PER_CAT_CYCLE:
            # Eccezione: se e' WOW e sono sotto wow_boost_max, lasciamo passare
            if is_wow and wow_pub < wow_boost_max and pub >= max_posts_cycle:
                pass  # passa, e' WOW e siamo in fase boost
            else:
                skipped_for_cat.append((cat, d["title"][:30]))
                continue

        # ANTI-RIPETIZIONE: skip se le ultime 3 erano della stessa categoria
        # (a meno che sia WOW)
        if not is_wow and recent_categories.count(cat) >= 2:
            remaining_cats = set()
            for other in all_deals:
                if not is_posted(posted, other["asin"]) and cat_count_cycle.get(get_deal_category(other["title"]), 0) == 0:
                    other_cat = get_deal_category(other["title"])
                    if other_cat != cat:
                        remaining_cats.add(other_cat)
            if remaining_cats:
                skipped_for_repeat.append((cat, d["title"][:30]))
                continue

        # Pubblica!
        # Pubblica!
        dn = count_deals(posted) + 1
        sp = "flash" if d.get("has_deal") or d["discount_percent"] >= FLASH_DEAL_PERCENT else None
        wow_tag = " 🔥WOW" if is_wow and pub >= max_posts_cycle else ""
        price_tag = " 💹PRICE-DROP" if d.get("_price_changed") else ""
        log("[PUB #{}{}{}] {} -{}% | {}".format(
            dn, wow_tag, price_tag, cat, d["discount_percent"], d["title"][:40]))

        # IMMAGINE BRANDATA SOLO per offerte WOW (sconto >=50% o brand TOP >=30%)
        if is_wow:
            ok = send_telegram_branded(format_deal(d, dn, sp), d, make_share_button(d["asin"]))
        else:
            ok = send_telegram(format_deal(d, dn, sp), d.get("image_url"), make_share_button(d["asin"]))
        if ok:
            mark_posted(posted, d["asin"], price=d["current_price"])
            save_posted(posted)
            save_deal_stat(d)
            pub += 1
            if pub > max_posts_cycle:
                wow_pub += 1
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
    if skipped_for_repeat:
        log("[SKIPPED per ripetizione]: {}".format(len(skipped_for_repeat)))

    log("=" * 60)
    log("[RIEPILOGO] Pubblicate {} | Totale oggi: {}".format(pub, count_deals(posted)))
    log("=" * 60)


if __name__ == "__main__":
    main()
