"""
Sottocosto Oggi - Bot Telegram v22 NEVER IDLE
Ottimizzazione anti-inattivita: cron 10min, 4 offerte/ciclo, pool ampio.
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

# CONFIG
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "10"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 12.0
MIN_RATING = 3.5
MIN_REVIEWS = 50
NO_RATING_MIN_PRICE = 25.0
MAX_POSTS_PER_CYCLE = 4
MAX_DEALS_POOL = 50
POST_INTERVAL_SECONDS = 120

PUBLISH_START_HOUR = 7
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"

KEYWORD_GROUPS = {
    "smartphone": [
        "Smartphone offerta", "Smartphone 5G offerta",
        "Custodia smartphone", "Vetro temperato",
        "Caricatore rapido", "Supporto telefono auto",
    ],
    "audio": [
        "Cuffie wireless offerta", "Cuffie noise cancelling",
        "Auricolari bluetooth", "Speaker bluetooth portatile",
        "Soundbar TV", "Cuffie gaming",
    ],
    "computer": [
        "Laptop offerta", "Notebook portatile",
        "Monitor PC offerta", "Monitor gaming",
        "Tastiera meccanica", "Mouse ergonomico",
        "Webcam HD", "SSD esterno",
        "Hub USB-C", "Docking station laptop",
    ],
    "smart_home": [
        "Smart speaker", "Lampadine smart WiFi",
        "Videocamera sicurezza casa", "Robot aspirapolvere",
        "Aspirapolvere senza fili", "Videocitofono smart",
        "Presa smart WiFi", "Termostato smart",
    ],
    "wearable": [
        "Smartwatch offerta", "Fitness tracker",
        "Orologio sportivo GPS", "Bilancia smart",
    ],
    "gaming": [
        "Giochi PS5 offerta", "Giochi Nintendo Switch",
        "Controller wireless gaming", "Cuffie gaming offerta",
        "Sedia gaming", "Tappetino mouse gaming",
    ],
    "foto_video": [
        "Action camera 4K", "Drone con camera",
        "Fotocamera digitale", "Treppiede fotografico",
        "Ring light professionale", "Scheda SD veloce",
    ],
    "moda_uomo": [
        "Scarpe uomo offerta", "Sneaker uomo",
        "Giacca uomo offerta", "Jeans uomo",
        "Felpa uomo cotone", "T-shirt uomo cotone",
        "Cintura pelle uomo", "Orologio uomo classico",
    ],
    "moda_donna": [
        "Scarpe donna offerta", "Sneaker donna",
        "Borsa donna pelle", "Giacca donna",
        "Vestito donna offerta", "Stivali donna",
        "Orecchini argento", "Bracciale donna",
    ],
    "bellezza": [
        "Profumo donna offerta", "Profumo uomo offerta",
        "Siero viso vitamina C", "Crema viso antirughe",
        "Piastra capelli professionale", "Asciugacapelli ionico",
        "Palette ombretti", "Set pennelli trucco",
        "Crema corpo idratante", "Maschera viso",
    ],
    "casa_cucina": [
        "Macchina caffe espresso", "Friggitrice ad aria offerta",
        "Robot cucina multifunzione", "Set pentole offerta",
        "Set coltelli professionali", "Frullatore potente",
        "Impastatrice planetaria", "Bilancia cucina digitale",
        "Bollitore elettrico",
    ],
    "casa_arredo": [
        "Purificatore aria casa", "Deumidificatore",
        "Ventilatore silenzioso", "Set asciugamani cotone",
        "Copripiumino matrimoniale", "Materasso memory foam",
        "Cuscino cervicale", "Candele profumate",
        "Lampada da tavolo design", "Tappeto soggiorno",
    ],
    "fai_da_te": [
        "Trapano avvitatore", "Idropulitrice offerta",
        "Set attrezzi completo", "Avvitatore a impulsi",
        "Cassetta attrezzi", "Livella laser",
    ],
    "sport": [
        "Scarpe running offerta", "Tappetino yoga",
        "Manubri palestra", "Elastici fitness",
        "Bicicletta offerta", "Tapis roulant",
        "Borraccia termica", "Zaino trekking",
    ],
    "bambini": [
        "LEGO offerta", "Giochi tavolo bambini",
        "Puzzle 1000 pezzi", "Giocattoli educativi",
        "Passeggino leggero", "Seggiolino auto",
        "Monopattino bambini",
    ],
    "accessori_tech": [
        "Power bank 20000mAh", "Caricatore USB-C rapido",
        "Caricatore wireless", "Cavi USB-C",
        "Proiettore portatile", "Supporto laptop ergonomico",
    ],
    "tablet": [
        "Tablet offerta", "Tablet Android",
        "eReader Kindle", "Custodia tablet",
        "Penna stilo tablet",
    ],
    "networking": [
        "Router WiFi 6", "Ripetitore WiFi",
        "Sistema mesh WiFi", "Switch ethernet",
    ],
    "stampa_3d": [
        "Stampante 3D offerta", "Stampante 3D resina",
        "Filamento PLA 1.75", "Filamento PETG",
        "Accessori stampante 3D",
    ],
    "tv": [
        "Smart TV 4K offerta", "TV OLED",
        "Fire TV Stick", "Proiettore 4K",
        "Staffa TV parete",
    ],
    "animali": [
        "Cibo cane premium", "Cibo gatto premium",
        "Cuccia cane", "Tiragraffi gatto",
        "Guinzaglio retrattile", "Lettiera autopulente",
    ],
    "auto": [
        "Dashcam auto 4K", "Caricatore auto USB-C",
        "Aspirapolvere auto portatile", "Tappetini auto universali",
        "Compressore portatile auto",
    ],
    "salute": [
        "Rasoio elettrico offerta", "Regolabarba professionale",
        "Spazzolino elettrico", "Misuratore pressione",
        "Termometro digitale", "Massaggiatore cervicale",
    ],
    "valigie": [
        "Valigia rigida offerta", "Set valigie",
        "Zaino viaggio capiente", "Cuscino viaggio memory",
        "Adattatore universale",
    ],
}

BRAND_BLACKLIST = [
    "dmoao", "timu", "yestel", "teclast", "oscal", "oukitel",
    "blackview", "umidigi", "cubot", "doogee", "ulefone", "hotwav",
    "fossibot", "rugged king", "kalinco", "tozo", "qhot", "veatool",
    "topk", "iniu", "herilios", "lisen", "ailun", "wsky", "pikoy",
]

TITLE_BLACKLIST = [
    "generico", "no brand", "senza marca", "unbranded",
    "lotto di", "set 100 pezzi", "bulk", "all'ingrosso",
    "stile", "tipo", "simile a", "ispirato a",
    "usa e getta", "monouso",
]

FOOTER_PHRASES = [
    "Solo il meglio per te", "Offerte verificate ogni giorno",
    "Al miglior prezzo garantito", "Selezionati per te",
    "Affari imperdibili", "Qualita' al prezzo giusto",
    "Il risparmio quotidiano", "Solo offerte reali",
]

GOOD_MORNING = [
    "\u2600\ufe0f <b>Buongiorno!</b>\n\nUna nuova giornata di offerte sta iniziando.\n\nTech, moda, casa, bellezza, sport, gaming... Tutto verificato, niente robaccia.\n\n\U0001f514 Attiva le notifiche per non perdere nulla.\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b>\n\nIl team \u00e8 al lavoro per trovarti le migliori offerte di oggi.\n\nProdotti di qualit\u00e0, prezzi reali, sconti veri.\n\n\U0001f6a8 Stay tuned!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\U0001f31e <b>Buongiorno!</b>\n\nOggi nuove offerte su Amazon ti aspettano.\n\nElettronica, moda, casa, bellezza e tanto altro. Solo prodotti consigliati.\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]


def log(msg):
    print(msg, flush=True)


def get_italy_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    return get_italy_now().hour >= PUBLISH_START_HOUR


def select_keywords():
    selected = []
    groups = list(KEYWORD_GROUPS.keys())
    random.shuffle(groups)
    for g in groups:
        kws = KEYWORD_GROUPS[g]
        n = min(len(kws), random.randint(2, 3))
        selected.extend(random.sample(kws, n))
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
        log("[ERR] {}: {}".format(keyword, e))
        return []
    if not results or not results.items:
        return []
    return [d for item in results.items if (d := parse_item(item))]


def parse_item(item):
    try:
        asin = item.asin
        title = None
        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass
        if not asin or not title or is_spam(title):
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
        }
    except Exception:
        return None


def get_deal_category(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg"]): return "stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "soundbar", "earbuds"]): return "audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes", "tracker"]): return "wearable"
    if any(w in t for w in ["iphone", "smartphone", "galaxy s", "pixel", "cellulare"]): return "smartphone"
    if any(w in t for w in ["laptop", "notebook", "macbook", "portatil"]): return "laptop"
    if any(w in t for w in ["tablet", "ipad", "kindle", "fire hd", "ereader"]): return "tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "oled", "fire tv", "proiettor"]): return "tv"
    if any(w in t for w in ["fotocamera", "camera", "gopro", "drone", "dji", "ring light"]): return "foto"
    if any(w in t for w in ["aspira", "robot", "roomba", "roborock", "dreame", "scopa elettrica"]): return "smarthome"
    if any(w in t for w in ["caffe", "nespresso", "espresso", "friggitrice", "robot cucina", "pentole", "coltelli", "frullator", "impastatric"]): return "cucina"
    if any(w in t for w in ["playstation", "ps5", "xbox", "nintendo", "gaming", "controller"]): return "gaming"
    if any(w in t for w in ["alexa", "echo", "nest", "hue", "ring videoc", "domotica"]): return "smarthome"
    if any(w in t for w in ["rasoio", "regolabarba", "spazzolino", "asciugacapelli", "piastra capelli", "ghd"]): return "curapersona"
    if any(w in t for w in ["scarp", "sneaker", "stival", "ciabatt", "sandal"]): return "scarpe"
    if any(w in t for w in ["jeans", "camicia", "magliett", "t-shirt", "felpa", "giacca", "pantalo", "vestit", "abito"]): return "abbigliamento"
    if any(w in t for w in ["borsa", "zaino", "trolley"]): return "borse"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "gioielli"
    if any(w in t for w in ["profum", "trucco", "makeup", "cosmet", "siero", "shampoo", "crema viso", "crema corpo", "maschera", "palette"]): return "bellezza"
    if any(w in t for w in ["lego", "barbie", "puzzle", "peluche", "passeggino", "seggiolino"]): return "bambini"
    if any(w in t for w in ["samsonite", "valigia", "eastpak"]): return "valigie"
    if any(w in t for w in ["cane", "gatto", "animale", "guinzaglio", "crocchin", "tiragraffi", "lettiera"]): return "animali"
    if any(w in t for w in ["ssd", "hard disk", "nvme", "memoria", "microsd"]): return "storage"
    if any(w in t for w in ["caricatore", "power bank", "cavo usb", "hub usb"]): return "accessori"
    if any(w in t for w in ["tastiera", "mouse", "webcam"]): return "periferiche"
    if any(w in t for w in ["router", "wifi", "mesh", "ripetitor", "switch ethernet"]): return "networking"
    if any(w in t for w in ["running", "yoga", "palestra", "manubri", "bici", "tapis", "trekking", "borraccia"]): return "sport"
    if any(w in t for w in ["dashcam", "tappetini auto", "compressor"]): return "auto"
    if any(w in t for w in ["misuratore", "termometro", "massaggiator"]): return "salute"
    if any(w in t for w in ["trapano", "idropulitrice", "attrezz", "avvitator", "livella"]): return "faidate"
    if any(w in t for w in ["materass", "cuscin", "asciugamani", "copripiumino", "lenzuol"]): return "casaarredo"
    if any(w in t for w in ["lampad", "candela", "tappeto"]): return "casaarredo"
    if any(w in t for w in ["purificator", "deumidific", "ventilator", "climatizzator"]): return "clima"
    return "altro"


def diversify_deals(deals):
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


def get_category_emoji(title):
    cat = get_deal_category(title)
    emojis = {
        "stampa3d": "\U0001f5a8", "audio": "\U0001f3a7", "wearable": "\u231a",
        "smartphone": "\U0001f4f1", "laptop": "\U0001f4bb", "tablet": "\U0001f4f2",
        "tv": "\U0001f4fa", "foto": "\U0001f4f7", "smarthome": "\U0001f3e0",
        "cucina": "\U0001f373", "gaming": "\U0001f3ae", "curapersona": "\U0001f488",
        "scarpe": "\U0001f45f", "abbigliamento": "\U0001f455", "borse": "\U0001f45c",
        "gioielli": "\U0001f48d", "bellezza": "\U0001f484", "bambini": "\U0001f9f8",
        "valigie": "\U0001f9f3", "animali": "\U0001f43e", "storage": "\U0001f4be",
        "accessori": "\U0001f50b", "periferiche": "\u2328", "networking": "\U0001f4e1",
        "sport": "\U0001f3cb", "auto": "\U0001f697", "salute": "\u2695",
        "faidate": "\U0001f527", "casaarredo": "\U0001f6cb", "clima": "\u2744",
        "altro": "\U0001f4e6",
    }
    return emojis.get(cat, "\U0001f4e6")


def get_category_hashtag(title):
    cat = get_deal_category(title)
    tags = {
        "stampa3d": "#stampa3d", "audio": "#audio", "wearable": "#wearable",
        "smartphone": "#smartphone", "laptop": "#laptop", "tablet": "#tablet",
        "tv": "#tv", "foto": "#foto", "smarthome": "#smarthome",
        "cucina": "#cucina", "gaming": "#gaming", "curapersona": "#curapersona",
        "scarpe": "#scarpe", "abbigliamento": "#moda", "borse": "#borse",
        "gioielli": "#gioielli", "bellezza": "#bellezza", "bambini": "#bambini",
        "valigie": "#viaggio", "animali": "#animali", "storage": "#tech",
        "accessori": "#accessori", "periferiche": "#tech", "networking": "#tech",
        "sport": "#sport", "auto": "#auto", "salute": "#salute",
        "faidate": "#faidate", "casaarredo": "#casa", "clima": "#casa",
        "altro": "#offerta",
    }
    return tags.get(cat, "#offerta")


def send_telegram(text, image_url=None, reply_markup=None):
    base = "https://api.telegram.org/bot{}".format(TELEGRAM_BOT_TOKEN)
    try:
        if image_url:
            pl = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text, "parse_mode": "HTML"}
            if reply_markup:
                pl["reply_markup"] = json.dumps(reply_markup)
            r = requests.post("{}/sendPhoto".format(base), json=pl, timeout=15)
            if r.json().get("ok"):
                return True
        pl = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_markup:
            pl["reply_markup"] = json.dumps(reply_markup)
        r = requests.post("{}/sendMessage".format(base), json=pl, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        log("[TG] {}".format(e))
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
def extract_short_name(title):
    """Estrae nome prodotto sintetico (primi 40 char, taglio pulito)."""
    # Prendi prima parte fino a virgola, trattino o numero del modello lungo
    short = re.split(r'[,\-\|]', title)[0].strip()
    # Se troppo corto, prendi i primi 50 char
    if len(short) < 15:
        short = title[:50].rsplit(' ', 1)[0]
    elif len(short) > 50:
        short = short[:50].rsplit(' ', 1)[0]
    return short.strip()

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

    # Headline sintetica: estrai prodotto + prezzi
    short_title = extract_short_name(title)
    msg += "<b>{} a {:.0f}\u20ac invece di {:.0f}\u20ac</b>\n\n".format(
        short_title, deal["current_price"], deal["original_price"])
    msg += "{} {}\n\n".format(e, title)
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


def send_good_morning():
    send_telegram(random.choice(GOOD_MORNING))
    log("Buongiorno!")


def send_prime_promo(t):
    msgs = [
        "\U0001f4e6 <b>Amazon Prime \u2014 Prova gratuita 30 giorni</b>\n\nSpedizioni illimitate in 1 giorno, Prime Video, Prime Music, foto illimitate e accesso anticipato alle Offerte Lampo.\n\nGratis per 30 giorni. Cancelli quando vuoi, senza impegno.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Attiva la prova gratuita</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t),
        "\U0001f69a <b>Consegne gratuite in 1 giorno con Amazon Prime</b>\n\nPrime Video, Prime Music, foto illimitate e 30 minuti di anticipo sulle Offerte Lampo. Tutto incluso.\n\nProva 30 giorni gratis. Nessun vincolo.\n\n\U0001f449 <a href=\"https://www.amazon.it/provaprime?tag={t}\">Prova Prime gratis</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t),
    ]
    send_telegram(random.choice(msgs))
    log("Prime!")


def send_music_promo(t):
    msgs = [
        "\U0001f3b5 <b>Amazon Music Unlimited \u2014 30 giorni gratis</b>\n\n90 milioni di brani in alta qualita', senza pubblicita'. Scarica offline, ascolta ovunque.\n\nGratis per 30 giorni. Poi 9,99\u20ac/mese, cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/gp/dmusic/promotions/AmazonMusicUnlimited?tag={t}\">Prova Music Unlimited</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t),
        "\U0001f3a7 <b>90 milioni di brani, zero pubblicita'</b>\n\nMusica illimitata in HD, download offline, compatibile con Alexa.\n\n30 giorni gratis. Poi 9,99\u20ac/mese, cancelli quando vuoi.\n\n\U0001f449 <a href=\"https://www.amazon.it/gp/dmusic/promotions/AmazonMusicUnlimited?tag={t}\">Prova gratis</a>\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e3 <b>@sottocosto_oggi</b>".format(t=t),
    ]
    send_telegram(random.choice(msgs))
    log("Music!")


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
    log("Recap!")


def send_weekly_stats():
    stats = load_stats()
    if not stats:
        return
    all_d = [d for v in stats.values() for d in v]
    if not all_d:
        return
    avg = round(sum(d["discount_percent"] for d in all_d) / len(all_d))
    best = max(all_d, key=lambda d: d["discount_percent"])
    msg = "\U0001f4ca <b>Settimana in numeri</b>\n\n"
    msg += "\U0001f525 {} offerte pubblicate\n".format(len(all_d))
    msg += "\U0001f4b0 Sconto medio: {}%\n".format(avg)
    msg += "\U0001f3c6 Best: {} (-{}%)\n\n".format(best["title"][:50], best["discount_percent"])
    msg += "Buona settimana! \U0001f680\n\U0001f4e3 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Stats!")


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
        if isinstance(data, dict):
            today = datetime.date.today().isoformat()
            return {k: v for k, v in data.items() if k == today}
        return {}
    except Exception:
        return {}


def save_posted(p):
    POSTED_FILE.write_text(json.dumps(p))


def is_posted(p, k):
    return k in p.get(datetime.date.today().isoformat(), [])


def mark_posted(p, k):
    today = datetime.date.today().isoformat()
    if today not in p:
        p[today] = []
    if k not in p[today]:
        p[today].append(k)


def count_deals(p):
    return len([k for k in p.get(datetime.date.today().isoformat(), []) if not k.startswith("_")])


def main():
    now = get_italy_now()
    hour = now.hour
    today = datetime.date.today().isoformat()
    wd = now.weekday()

    log("=== v22 NEVER IDLE | {} | IT: {} ===".format(datetime.datetime.now().isoformat(), now.strftime("%H:%M")))

    if not is_publish_time():
        log("Notte. Stop.")
        return

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
        "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"]
        if not os.environ.get(v)]
    if missing:
        log("Mancano: {}".format(missing))
        return

    posted = load_posted()
    log("Oggi: {}".format(count_deals(posted)))

    if hour == 7 and not is_posted(posted, "_am"):
        send_good_morning()
        mark_posted(posted, "_am")
        save_posted(posted)
        time.sleep(5)

    if wd == 0 and hour == 9 and not is_posted(posted, "_wk"):
        send_weekly_stats()
        mark_posted(posted, "_wk")
        save_posted(posted)
        time.sleep(5)

    if hour == 12 and not is_posted(posted, "_pr"):
        send_prime_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_pr")
        save_posted(posted)
        time.sleep(5)

    if hour == 20 and not is_posted(posted, "_mu"):
        send_music_promo(AMAZON_PARTNER_TAG)
        mark_posted(posted, "_mu")
        save_posted(posted)
        time.sleep(5)

    if hour == 23 and not is_posted(posted, "_rc"):
        send_evening_recap(today)
        mark_posted(posted, "_rc")
        save_posted(posted)
        return

    api = create_api()
    kws = select_keywords()
    log("Kw: {}".format(len(kws)))

    all_deals = []
    seen = set(posted.get(today, []))

    for kw in kws:
        if len(all_deals) >= MAX_DEALS_POOL:
            break
        for d in search_deals(api, kw):
            if d["asin"] not in seen and len(all_deals) < MAX_DEALS_POOL:
                seen.add(d["asin"])
                d["_kw"] = kw
                all_deals.append(d)

    log("Pool: {}".format(len(all_deals)))
    if not all_deals:
        log("Zero. Fine.")
        return

    all_deals.sort(key=lambda d: (d.get("has_deal", False), d["discount_percent"]), reverse=True)
    all_deals = diversify_deals(all_deals)

    if hour >= 9 and not is_posted(posted, "_top"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        log("TOP: {}... (-{}%)".format(best["title"][:35], best["discount_percent"]))
        if send_telegram(format_deal(best, special="top"), best.get("image_url"), make_share_button(best["asin"])):
            mark_posted(posted, best["asin"])
            mark_posted(posted, "_top")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            time.sleep(POST_INTERVAL_SECONDS)

    pub = 0
    for d in all_deals:
        if pub >= MAX_POSTS_PER_CYCLE or not is_publish_time() or is_posted(posted, d["asin"]):
            continue
        dn = count_deals(posted) + 1
        sp = "flash" if d.get("has_deal") or d["discount_percent"] >= FLASH_DEAL_PERCENT else None
        cat = get_deal_category(d["title"])
        log("#{} [{}] {}... (-{}%)".format(dn, cat, d["title"][:30], d["discount_percent"]))
        if send_telegram(format_deal(d, dn, sp), d.get("image_url"), make_share_button(d["asin"])):
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            pub += 1
            time.sleep(POST_INTERVAL_SECONDS)

    log("=== Oggi: {} ===".format(count_deals(posted)))


if __name__ == "__main__":
    main()
