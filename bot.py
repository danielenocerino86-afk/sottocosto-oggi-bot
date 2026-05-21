"""
Sottocosto Oggi - Bot Telegram v15
Fix timeout: meno keyword per ciclo, max 10 offerte, log dettagliato.
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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

AMAZON_CREDENTIAL_ID = os.environ.get("AMAZON_CREDENTIAL_ID", "")
AMAZON_CREDENTIAL_SECRET = os.environ.get("AMAZON_CREDENTIAL_SECRET", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")

MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "20"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 5.0
MAX_POSTS_PER_CATEGORY = 2
MAX_POSTS_TOTAL = 10
POST_INTERVAL_SECONDS = 300   # 5 minuti tra offerte normali
FLASH_INTERVAL_SECONDS = 120  # 2 minuti per flash deal

PUBLISH_START_HOUR = 7
PUBLISH_END_HOUR = 23
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"

KEYWORD_GROUPS = {
    "moda": [
        "Abbigliamento uomo estate",
        "Abbigliamento donna",
        "Scarpe uomo",
        "Scarpe donna",
        "Borse donna pelle",
        "Gioielli donna",
        "Orologi uomo",
        "Occhiali da sole",
    ],
    "bellezza": [
        "Bellezza cosmetica offerta",
        "Cura della persona",
        "Profumi donna",
        "Profumi uomo",
        "Crema viso",
        "Shampoo professionale",
    ],
    "tech": [
        "Smartphone offerta",
        "Cuffie bluetooth",
        "Smartwatch",
        "Tablet Android",
        "Laptop portatile",
        "Monitor PC",
        "Power bank",
        "Caricatore USB-C",
    ],
    "casa": [
        "Casa cucina offerta",
        "Robot aspirapolvere",
        "Friggitrice ad aria",
        "Macchina caffe",
        "Smart home Alexa",
        "Illuminazione LED",
        "Ventilatore silenzioso",
    ],
    "tempo_libero": [
        "Sport fitness",
        "Videogiochi PS5",
        "Videogiochi Nintendo Switch",
        "Giocattoli bambini",
        "Giardino giardinaggio",
        "Bicicletta",
    ],
    "altro": [
        "Animali domestici cane",
        "Auto accessori",
        "Valigia viaggio",
        "Stampante 3D",
        "Mobili arredamento",
        "Materasso memory",
        "Prodotti neonati",
    ],
}

FOOTER_PHRASES = [
    "Offerte ogni giorno",
    "Sconti verificati",
    "Risparmia ogni giorno",
    "Solo offerte vere",
    "Prezzi al minimo",
    "Affari imperdibili",
    "Scelti per te",
    "Il risparmio e' qui",
]

GOOD_MORNING = [
    "\u2600\ufe0f <b>Buongiorno!</b> Le offerte di oggi stanno arrivando...\n\n\U0001f514 Pubblichiamo sconti verificati fino a mezzanotte!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b> Pronti per nuovi sconti?\n\n\U0001f6a8 Le migliori offerte Amazon stanno per arrivare!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\U0001f31e <b>Buongiorno!</b> Oggi tante nuove offerte in arrivo!\n\n\U0001f4b0 Sconti reali, prezzi verificati, ogni giorno.\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]


def log(msg):
    print(msg, flush=True)


def get_italy_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    h = get_italy_now().hour
    return PUBLISH_START_HOUR <= h <= PUBLISH_END_HOUR


def select_keywords():
    selected = []
    for group_name, keywords in KEYWORD_GROUPS.items():
        n = min(len(keywords), random.randint(1, 2))
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


def is_spam_title(title):
    if len(title) > 400:
        return True
    if sum(1 for c in title if 0x4E00 < ord(c) < 0x9FFF) > 3:
        return True
    if any(w in title.lower() for w in ["clicca qui", "compra ora", "gratis 100%", "buy now"]):
        return True
    return False


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

        try:
            title = item.item_info.title.display_value
        except (AttributeError, TypeError):
            pass
        if not asin or not title or is_spam_title(title):
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
    except Exception:
        return None


def get_category_emoji(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg", "resina 3d", "ugello"]): return "\U0001f5a8"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon", "soundbar"]): return "\U0001f3a7"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "\u231a"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel", "custodia telefono", "cover telefono"]): return "\U0001f4f1"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "\U0001f4bb"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "\U0001f4f2"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo", "fire tv"]): return "\U0001f4fa"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro", "drone"]): return "\U0001f4f7"
    if any(w in t for w in ["cane", "gatto", "animale", "pet ", "guinzaglio", "crocchin", "antiparassit", "peli animali", "togli peli", "cuccia", "tiragraffi"]): return "\U0001f43e"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal", "mocassin", "ciabatt"]): return "\U0001f45f"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito", "gonna", "shorts"]): return "\U0001f455"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone", "trolley"]): return "\U0001f45c"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "\U0001f48d"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo"]): return "\U0001f484"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat", "caffettier", "friggitrice"]): return "\U0001f373"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia", "scopa"]): return "\U0001f9f9"
    if any(w in t for w in ["lampad", "luce", "led", "illumin"]): return "\U0001f4a1"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller", "gaming"]): return "\U0001f3ae"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis", "yoga"]): return "\U0001f3cb"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "barbecue"]): return "\U0001f331"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "\U0001f4da"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego"]): return "\U0001f9f8"
    if any(w in t for w in ["auto", "moto", "dashcam", "caricatore auto"]): return "\U0001f697"
    if any(w in t for w in ["alexa", "echo", "smart home", "domotica"]): return "\U0001f3e0"
    if any(w in t for w in ["neonat", "biberon", "pannolin", "passeggino"]): return "\U0001f476"
    if any(w in t for w in ["mobil", "scrivania", "armadio", "divano", "sedia"]): return "\U0001fa91"
    if any(w in t for w in ["materass", "cuscin", "coperta", "lenzuol"]): return "\U0001f6cf"
    if any(w in t for w in ["chitarra", "pianola", "ukulele"]): return "\U0001f3b8"
    if any(w in t for w in ["penna", "quaderno", "cancelleria"]): return "\u270f"
    if any(w in t for w in ["condizionator", "ventilator", "stufa", "climatizza"]): return "\u2744"
    if any(w in t for w in ["occhial", "sunglasses"]): return "\U0001f576"
    if any(w in t for w in ["power bank", "caricatore", "usb-c", "cavo"]): return "\U0001f50b"
    if any(w in t for w in ["ssd", "hard disk", "nvme", "memoria"]): return "\U0001f4be"
    return "\U0001f4e6"


def get_category_hashtag(title):
    t = title.lower()
    if any(w in t for w in ["stampant", "3d", "filament", "pla", "petg", "resina 3d", "ugello"]): return "#stampa3d"
    if any(w in t for w in ["cuffi", "speaker", "auricol", "audio", "microfon", "soundbar"]): return "#audio"
    if any(w in t for w in ["smartwatch", "orologio", "watch", "fitnes"]): return "#orologi"
    if any(w in t for w in ["telefon", "smartphone", "cellulare", "iphone", "samsung galaxy", "pixel", "custodia telefono", "cover telefono"]): return "#smartphone"
    if any(w in t for w in ["laptop", "notebook", "computer", "portatil", "macbook"]): return "#computer"
    if any(w in t for w in ["tablet", "ipad", "kindle"]): return "#tablet"
    if any(w in t for w in ["tv ", "television", "monitor", "schermo", "fire tv"]): return "#tv"
    if any(w in t for w in ["fotocamera", "camera", "obiettiv", "gopro", "drone"]): return "#fotografia"
    if any(w in t for w in ["cane", "gatto", "animale", "pet ", "guinzaglio", "crocchin", "antiparassit", "peli animali", "togli peli", "cuccia", "tiragraffi"]): return "#animali"
    if any(w in t for w in ["scarp", "sneaker", "stival", "sandal", "mocassin", "ciabatt"]): return "#scarpe"
    if any(w in t for w in ["magliett", "t-shirt", "camicia", "felpa", "giacca", "pantalo", "jeans", "vestit", "abito", "gonna", "shorts"]): return "#abbigliamento"
    if any(w in t for w in ["borsa", "zaino", "valig", "borsone", "trolley"]): return "#borse"
    if any(w in t for w in ["gioiell", "collana", "braccial", "anello", "orecchini"]): return "#gioielli"
    if any(w in t for w in ["profum", "crema", "trucco", "makeup", "cosmet", "siero", "shampoo"]): return "#bellezza"
    if any(w in t for w in ["cucina", "pentol", "padell", "forno", "mixer", "frullat", "caffettier", "friggitrice"]): return "#cucina"
    if any(w in t for w in ["aspira", "robot", "lavapaviment", "pulizia", "scopa"]): return "#casa"
    if any(w in t for w in ["lampad", "luce", "led", "illumin"]): return "#casa"
    if any(w in t for w in ["gioco", "videogioc", "playstation", "xbox", "nintendo", "controller", "gaming"]): return "#gaming"
    if any(w in t for w in ["sport", "palestra", "fitness", "bici", "tapis", "yoga"]): return "#sport"
    if any(w in t for w in ["giardino", "giardinaggio", "tosaerba", "barbecue"]): return "#giardino"
    if any(w in t for w in ["libro", "romanzo", "manuale"]): return "#libri"
    if any(w in t for w in ["bambin", "giocattol", "peluche", "lego"]): return "#giocattoli"
    if any(w in t for w in ["auto", "moto", "dashcam", "caricatore auto"]): return "#auto"
    if any(w in t for w in ["alexa", "echo", "smart home", "domotica"]): return "#smarthome"
    if any(w in t for w in ["neonat", "biberon", "pannolin", "passeggino"]): return "#neonati"
    if any(w in t for w in ["mobil", "scrivania", "armadio", "divano", "sedia"]): return "#arredamento"
    if any(w in t for w in ["materass", "cuscin", "coperta", "lenzuol"]): return "#casa"
    if any(w in t for w in ["chitarra", "pianola", "ukulele"]): return "#musica"
    if any(w in t for w in ["penna", "quaderno", "cancelleria"]): return "#cancelleria"
    if any(w in t for w in ["condizionator", "ventilator", "stufa", "climatizza"]): return "#clima"
    if any(w in t for w in ["occhial", "sunglasses"]): return "#moda"
    if any(w in t for w in ["power bank", "caricatore", "usb-c", "cavo"]): return "#accessoritech"
    if any(w in t for w in ["ssd", "hard disk", "nvme", "memoria"]): return "#storage"
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
        requests.utils.quote("Guarda questa offerta su @sottocosto_oggi!"))
    return {"inline_keyboard": [[{"text": "\U0001f4e4 Condividi con un amico", "url": url}]]}


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
        msg = "\U0001f3c6 <b>OFFERTA DEL GIORNO</b> \U0001f3c6\n\n"
        ftag = "#offertadelgiorno"
        ftxt = "La migliore offerta di oggi!"
    elif special == "flash":
        msg = "\u26a1 <b>FLASH DEAL -{pct}%</b> \u26a1\n<i>Oltre il 50%! Potrebbe finire presto.</i>\n\n".format(pct=pct)
        ftag = "#flashdeal"
        ftxt = "Flash deal!"
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
    log("Buongiorno inviato!")


def send_evening_recap(today):
    stats = load_stats()
    deals = stats.get(today, [])
    if not deals:
        return
    top3 = sorted(deals, key=lambda d: d["discount_percent"], reverse=True)[:3]
    msg = "\U0001f319 <b>TOP 3 offerte di oggi</b>\n\n"
    for i, d in enumerate(top3):
        e = get_category_emoji(d["title"])
        link = "https://www.amazon.it/dp/{}?tag={}".format(d["asin"], AMAZON_PARTNER_TAG)
        msg += "{}. {} <a href=\"{}\">{}</a>\n   <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b> (-{}%)\n\n".format(
            i+1, e, link, d["title"][:60], d["original_price"], d["current_price"], d["discount_percent"])
    msg += "Oggi: <b>{}</b> offerte pubblicate!\n\n".format(len(deals))
    msg += "\U0001f514 Non perderti quelle di domani!\n\U0001f4f2 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Riepilogo serale inviato!")


def send_weekly_stats():
    stats = load_stats()
    if not stats:
        return
    all_d = [d for deals in stats.values() for d in deals]
    if not all_d:
        return
    avg = round(sum(d["discount_percent"] for d in all_d) / len(all_d))
    best = max(all_d, key=lambda d: d["discount_percent"])
    cats = {}
    for d in all_d:
        c = get_category_hashtag(d["title"])
        cats[c] = cats.get(c, 0) + 1
    top_c = ", ".join([c[0] for c in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]])

    msg = "\U0001f4ca <b>La settimana in numeri</b>\n\n"
    msg += "\U0001f525 {} offerte pubblicate\n".format(len(all_d))
    msg += "\U0001f4b0 Sconto medio: {}%\n".format(avg)
    msg += "\U0001f3c6 Miglior sconto: {} (-{}%)\n".format(best["title"][:50], best["discount_percent"])
    msg += "\U0001f4e6 Top: {}\n\n".format(top_c)
    msg += "Buona settimana! \U0001f680\n\U0001f4e3 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    log("Stats settimanali inviate!")


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

    log("=== Bot v15 | {} | IT: {} ===".format(datetime.datetime.now().isoformat(), now.strftime("%H:%M")))

    if not is_publish_time():
        log("Fuori orario ({}-{}). Stop.".format(PUBLISH_START_HOUR, PUBLISH_END_HOUR))
        return

    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
        "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"] if not os.environ.get(v)]
    if missing:
        log("Mancano: {}".format(missing))
        return

    posted = load_posted()
    log("Gia oggi: {}".format(count_deals(posted)))

    # Buongiorno (7:00-7:59)
    if hour == 7 and not is_posted(posted, "_morning"):
        send_good_morning()
        mark_posted(posted, "_morning")
        save_posted(posted)
        time.sleep(5)
        log("OK buongiorno")

    # Stats settimanali (lunedi 9:00-9:59)
    if weekday == 0 and hour == 9 and not is_posted(posted, "_weekly"):
        send_weekly_stats()
        mark_posted(posted, "_weekly")
        save_posted(posted)
        time.sleep(5)
        log("OK stats")

    # Riepilogo serale (23:00-23:59)
    if hour == 23 and not is_posted(posted, "_recap"):
        send_evening_recap(today)
        mark_posted(posted, "_recap")
        save_posted(posted)
        log("OK recap")
        return

    # Cerca offerte
    log("Cerco offerte...")
    api = create_api()
    keywords = select_keywords()
    log("Keywords: {} ({})".format(len(keywords), ", ".join(keywords[:5]) + "..."))

    all_deals = []
    seen = set(posted.get(today, []))

    for kw in keywords:
        deals = search_deals(api, kw)
        n = 0
        for d in deals:
            if n >= MAX_POSTS_PER_CATEGORY:
                break
            if d["asin"] in seen:
                continue
            seen.add(d["asin"])
            d["_kw"] = kw
            all_deals.append(d)
            n += 1
        if n > 0:
            log("  {} -> {}".format(kw, n))

    log("Nuove: {}".format(len(all_deals)))
    if not all_deals:
        log("Nessuna nuova. Fine.")
        return

    # Offerta del giorno (9+)
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
            log("  TOP pubblicata!")
            time.sleep(POST_INTERVAL_SECONDS)

    # Flash deals (>=50%)
    flash = [d for d in all_deals if d["discount_percent"] >= FLASH_DEAL_PERCENT]
    normal = [d for d in all_deals if d["discount_percent"] < FLASH_DEAL_PERCENT]

    for d in flash:
        if not is_publish_time() or is_posted(posted, d["asin"]):
            continue
        dn = count_deals(posted) + 1
        log("FLASH #{}: {}... (-{}%)".format(dn, d["title"][:40], d["discount_percent"]))
        msg = format_deal(d, dn, special="flash")
        btn = make_share_button(d["asin"])
        if send_telegram(msg, d.get("image_url"), btn):
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            time.sleep(FLASH_INTERVAL_SECONDS)

    # Normali: top 5 prima poi shuffle
    normal.sort(key=lambda d: d["discount_percent"], reverse=True)
    top = normal[:5]
    rest = normal[5:]
    random.shuffle(rest)
    normal = top + rest
    if len(normal) > MAX_POSTS_TOTAL:
        normal = normal[:MAX_POSTS_TOTAL]

    for d in normal:
        if not is_publish_time() or is_posted(posted, d["asin"]):
            continue
        dn = count_deals(posted) + 1
        log("#{}: {}... (-{}%)".format(dn, d["title"][:40], d["discount_percent"]))
        msg = format_deal(d, dn)
        btn = make_share_button(d["asin"])
        if send_telegram(msg, d.get("image_url"), btn):
            mark_posted(posted, d["asin"])
            save_posted(posted)
            save_deal_stat(d)
            time.sleep(POST_INTERVAL_SECONDS)

    log("=== Fine. Oggi: {} ===".format(count_deals(posted)))


if __name__ == "__main__":
    main()
