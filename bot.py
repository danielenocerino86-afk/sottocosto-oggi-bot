"""
Sottocosto Oggi - Bot Telegram v13 (FINAL)
Tutte le feature: Buongiorno, Offerta del Giorno, Flash Deal, Riepilogo Serale,
Stats Settimanali, Condividi, Titoli puliti, Filtro qualita, Footer rotante,
38 categorie, Anti-duplicati giornaliero, Orario 07-00 Italia.
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

MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "20"))
FLASH_DEAL_PERCENT = 50
MIN_PRICE = 5.0
MAX_POSTS_PER_CATEGORY = 3
MAX_POSTS_TOTAL = 25
POST_INTERVAL_SECONDS = 60
FLASH_INTERVAL_SECONDS = 10

PUBLISH_START_HOUR = 7
TIMEZONE_OFFSET = 2

POSTED_FILE = Path(__file__).parent / "posted_deals.json"
STATS_FILE = Path(__file__).parent / "daily_stats.json"

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

GOOD_MORNING_MESSAGES = [
    "\u2600\ufe0f <b>Buongiorno!</b> Le offerte di oggi stanno arrivando...\n\n\U0001f514 Resta connesso, pubblichiamo sconti verificati fino a mezzanotte!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\u2615 <b>Buongiorno!</b> Pronti per una nuova giornata di sconti?\n\n\U0001f6a8 Le migliori offerte Amazon stanno per arrivare!\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
    "\U0001f31e <b>Buongiorno!</b> Oggi tante nuove offerte in arrivo!\n\n\U0001f4b0 Sconti reali, prezzi verificati, ogni giorno.\n\n\U0001f4f2 <b>@sottocosto_oggi</b>",
]


# ============================================================
# UTILITY
# ============================================================

def get_italy_now():
    utc_now = datetime.datetime.utcnow()
    return utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)


def is_publish_time():
    return get_italy_now().hour >= PUBLISH_START_HOUR


def clean_title(title):
    """Pulisce il titolo: tronca al primo punto logico dopo 80 char, rimuove keyword spam."""
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'[,/|]\s*(?:compatibile con|adatto per|per)\s+[\w\s/,]+$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\([^)]*compatib[^)]*\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\[[^\]]*\]', '', title)

    if len(title) > 120:
        cut_points = [
            title.find(', ', 70),
            title.find(' - ', 70),
            title.find('. ', 70),
            title.find(' | ', 70),
        ]
        cut_points = [p for p in cut_points if 70 < p < 150]
        if cut_points:
            title = title[:min(cut_points)]
    elif len(title) > 200:
        title = title[:200]

    return title.strip().rstrip(',').rstrip('-').strip()


def is_spam_title(title):
    if len(title) > 400:
        return True
    non_ascii = sum(1 for c in title if 0x4E00 < ord(c) < 0x9FFF)
    if non_ascii > 3:
        return True
    spam_words = ["clicca qui", "compra ora", "offerta limitata", "solo oggi", "gratis 100%", "act now", "buy now"]
    if any(w in title.lower() for w in spam_words):
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


# ============================================================
# RICERCA E PARSING
# ============================================================

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
    except Exception as e:
        print("[PARSE] Errore: {}".format(e))
        return None


# ============================================================
# EMOJI E HASHTAG
# ============================================================

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
    if any(w in t for w in ["cane", "gatto", "animale", "pet ", "guinzaglio", "crocchin", "antiparassit", "peli animali", "togli peli", "cuccia", "tiragraffi", "acquario", "mangiatoia"]): return "\U0001f43e"
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
    if any(w in t for w in ["cane", "gatto", "animale", "pet ", "guinzaglio", "crocchin", "antiparassit", "peli animali", "togli peli", "cuccia", "tiragraffi", "acquario", "mangiatoia"]): return "#animali"
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
    if any(w in t for w in ["auto", "moto", "automobile", "tergicristal", "dashcam", "caricatore auto"]): return "#auto"
    if any(w in t for w in ["alexa", "echo", "smart home", "domotica", "presa smart", "termostato"]): return "#smarthome"
    if any(w in t for w in ["neonat", "biberon", "pannolin", "passeggino", "seggiolino"]): return "#neonati"
    if any(w in t for w in ["mobil", "scrivania", "libreria", "armadio", "divano", "sedia", "tavol"]): return "#arredamento"
    if any(w in t for w in ["materass", "cuscin", "coperta", "lenzuol", "piumon", "trapunta"]): return "#casa"
    if any(w in t for w in ["chitarra", "pianola", "tastiera musicale", "ukulele", "batteria musicale"]): return "#musica"
    if any(w in t for w in ["penna", "quaderno", "zaino scuola", "matita", "cancelleria", "evidenziator"]): return "#cancelleria"
    if any(w in t for w in ["condizionator", "ventilator", "stufa", "radiator", "climatizza", "riscalda"]): return "#clima"
    return "#tech"


# ============================================================
# TELEGRAM
# ============================================================

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
            print("   Foto fallita, fallback testo...")
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post("{}/sendMessage".format(base_url), json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print("[TELEGRAM] Errore: {}".format(e))
        return False


def make_share_button(asin):
    share_url = "https://t.me/share/url?url={}&text={}".format(
        requests.utils.quote("https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)),
        requests.utils.quote("Guarda questa offerta su @sottocosto_oggi!")
    )
    return {"inline_keyboard": [[{"text": "\U0001f4e4 Condividi con un amico", "url": share_url}]]}


def format_stars(rating, review_count):
    try:
        r = float(rating)
        full = int(r)
        empty = 5 - full
        stars = "\u2B50" * full + "\u2606" * empty
        rc = review_count
        if rc:
            return "{} {}/5 ({} recensioni)".format(stars, rating, rc)
        return "{} {}/5".format(stars, rating)
    except (ValueError, TypeError):
        return ""


def format_saving_highlight(saving):
    if saving >= 100:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f4a5\n\n".format(saving)
    elif saving >= 50:
        return "\U0001f4b8 Risparmi: <b>{:.2f}\u20ac</b> \U0001f525\n\n".format(saving)
    return "\U0001f4b8 Risparmi: {:.2f}\u20ac\n\n".format(saving)


# ============================================================
# FORMATTAZIONE MESSAGGI
# ============================================================

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
    footer = random.choice(FOOTER_PHRASES)

    msg = "{alert} <b>SCONTO -{pct}%</b> {alert}\n\n".format(alert=alert, pct=pct)
    msg += "{emoji} <b>{title}</b>\n\n".format(emoji=cat_emoji, title=title[:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(deal["original_price"], deal["current_price"])
    msg += format_saving_highlight(deal["discount"])

    if deal.get("rating"):
        star_text = format_stars(deal["rating"], deal.get("review_count"))
        if star_text:
            msg += "{}\n\n".format(star_text)

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    if deal_number > 0:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerta #{} di oggi\n".format(deal_number)
    else:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 {}\n".format(footer)
    msg += "#offerta #amazon #sconto{} {}\n".format(pct, cat_tag)
    msg += "\u26a0\ufe0f <i>Prezzo soggetto a variazioni</i>"
    return msg


def format_top_deal(deal):
    pct = deal["discount_percent"]
    asin = deal["asin"]
    title = deal["title"]
    cat_emoji = get_category_emoji(title)
    cat_tag = get_category_hashtag(title)
    affiliate_link = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean_link = "https://www.amazon.it/dp/{}".format(asin)

    msg = "\U0001f3c6 <b>OFFERTA DEL GIORNO</b> \U0001f3c6\n\n"
    msg += "{emoji} <b>{title}</b>\n\n".format(emoji=cat_emoji, title=title[:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(deal["original_price"], deal["current_price"])
    msg += format_saving_highlight(deal["discount"])

    if deal.get("rating"):
        star_text = format_stars(deal["rating"], deal.get("review_count"))
        if star_text:
            msg += "{}\n\n".format(star_text)

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 La migliore offerta di oggi!\n"
    msg += "#offertadelgiorno #amazon #sconto{} {}".format(pct, cat_tag)
    return msg


def format_flash_deal(deal, deal_number=0):
    pct = deal["discount_percent"]
    asin = deal["asin"]
    title = deal["title"]
    cat_emoji = get_category_emoji(title)
    cat_tag = get_category_hashtag(title)
    affiliate_link = "https://www.amazon.it/dp/{}?tag={}".format(asin, AMAZON_PARTNER_TAG)
    clean_link = "https://www.amazon.it/dp/{}".format(asin)

    msg = "\u26a1 <b>FLASH DEAL -{pct}%</b> \u26a1\n".format(pct=pct)
    msg += "<i>Sconto superiore al 50%! Potrebbe finire presto.</i>\n\n"
    msg += "{emoji} <b>{title}</b>\n\n".format(emoji=cat_emoji, title=title[:200])
    msg += "\U0001f4b0 <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b>\n".format(deal["original_price"], deal["current_price"])
    msg += format_saving_highlight(deal["discount"])

    if deal.get("rating"):
        star_text = format_stars(deal["rating"], deal.get("review_count"))
        if star_text:
            msg += "{}\n\n".format(star_text)

    msg += "\U0001f449 <a href=\"{}\">SCOPRI L'OFFERTA SU AMAZON</a>\n\n".format(affiliate_link)
    msg += "{}\n\n".format(clean_link)
    msg += "\u2501" * 15 + "\n"
    if deal_number > 0:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Offerta #{} di oggi\n".format(deal_number)
    else:
        msg += "\U0001f4e3 <b>@sottocosto_oggi</b> \u2022 Flash deal!\n"
    msg += "#flashdeal #amazon #sconto{} {}".format(pct, cat_tag)
    return msg


# ============================================================
# MESSAGGI SPECIALI
# ============================================================

def send_good_morning():
    msg = random.choice(GOOD_MORNING_MESSAGES)
    send_telegram(msg)
    print("Buongiorno inviato!")


def send_evening_recap(today):
    stats = load_stats()
    today_deals = stats.get(today, [])
    if not today_deals:
        return

    top3 = sorted(today_deals, key=lambda d: d["discount_percent"], reverse=True)[:3]

    msg = "\U0001f319 <b>TOP 3 offerte di oggi</b>\n\n"
    for i, deal in enumerate(top3):
        cat_emoji = get_category_emoji(deal["title"])
        affiliate_link = "https://www.amazon.it/dp/{}?tag={}".format(deal["asin"], AMAZON_PARTNER_TAG)
        msg += "{}. {} <a href=\"{}\">{}</a>\n".format(i + 1, cat_emoji, affiliate_link, deal["title"][:60])
        msg += "   <s>{:.2f}\u20ac</s> \u27a1 <b>{:.2f}\u20ac</b> (-{}%)\n\n".format(
            deal["original_price"], deal["current_price"], deal["discount_percent"])

    msg += "Oggi abbiamo pubblicato <b>{}</b> offerte!\n\n".format(len(today_deals))
    msg += "Non perderti quelle di domani \U0001f514\n"
    msg += "\U0001f4f2 Attiva le notifiche per <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    print("Riepilogo serale inviato!")


def send_weekly_stats():
    stats = load_stats()
    total_deals = 0
    total_discount = 0
    best_deal = None
    categories = {}

    for day, deals in stats.items():
        for deal in deals:
            total_deals += 1
            total_discount += deal.get("discount_percent", 0)
            cat = get_category_hashtag(deal.get("title", ""))
            categories[cat] = categories.get(cat, 0) + 1
            if not best_deal or deal.get("discount_percent", 0) > best_deal.get("discount_percent", 0):
                best_deal = deal

    if total_deals == 0:
        return

    avg_discount = round(total_discount / total_deals)
    top_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = ", ".join([c[0] for c in top_cats])

    msg = "\U0001f4ca <b>La settimana in numeri</b>\n\n"
    msg += "\U0001f525 {} offerte pubblicate\n".format(total_deals)
    msg += "\U0001f4b0 Sconto medio: {}%\n".format(avg_discount)
    if best_deal:
        msg += "\U0001f3c6 Miglior sconto: {} (-{}%)\n".format(best_deal["title"][:50], best_deal["discount_percent"])
    msg += "\U0001f4e6 Top categorie: {}\n\n".format(top_cats_str)
    msg += "Buona settimana di sconti! \U0001f680\n"
    msg += "\U0001f4e3 <b>@sottocosto_oggi</b>"
    send_telegram(msg)
    print("Stats settimanali inviate!")


# ============================================================
# STATS E ANTI-DUPLICATI
# ============================================================

def load_stats():
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except (json.JSONDecodeError, TypeError):
            return {}
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


# ============================================================
# MAIN
# ============================================================

def main():
    italy_now = get_italy_now()
    italy_hour = italy_now.hour
    today = datetime.date.today().isoformat()
    weekday = italy_now.weekday()

    print("Sottocosto Oggi Bot v13 FINAL - {}".format(datetime.datetime.now().isoformat()))
    print("Ora italiana: {}".format(italy_now.strftime("%H:%M")))

    if not is_publish_time():
        print("Fuori orario. Stop.")
        return

    missing = []
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
                "AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print("Variabili mancanti: {}".format(", ".join(missing)))
        return

    posted = load_posted()

    # Buongiorno alle 7
    if italy_hour == 7 and not is_already_posted(posted, "GOOD_MORNING"):
        send_good_morning()
        mark_as_posted(posted, "GOOD_MORNING")
        save_posted(posted)
        time.sleep(5)

    # Stats settimanali: lunedi alle 9
    if weekday == 0 and italy_hour == 9 and not is_already_posted(posted, "WEEKLY_STATS"):
        send_weekly_stats()
        mark_as_posted(posted, "WEEKLY_STATS")
        save_posted(posted)
        time.sleep(5)

    # Riepilogo serale alle 23
    if italy_hour == 23 and not is_already_posted(posted, "EVENING_RECAP"):
        send_evening_recap(today)
        mark_as_posted(posted, "EVENING_RECAP")
        save_posted(posted)
        return

    # Cerca offerte
    api = create_api()
    already_today = len([k for k in posted.get(today, []) if not k.startswith(("GOOD_", "WEEKLY_", "EVENING_", "TOP_"))])
    print("Offerte gia pubblicate oggi: {}".format(already_today))

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
            print("  {} -> {}".format(keyword, new_count))

    print("\nNuove: {}".format(len(all_deals)))
    if not all_deals:
        print("Nessuna nuova.")
        return

    # Offerta del giorno alle 9+
    if italy_hour >= 9 and not is_already_posted(posted, "TOP_DEAL"):
        best = max(all_deals, key=lambda d: d["discount_percent"])
        print("  TOP DEAL: {}... (-{}%)".format(best["title"][:45], best["discount_percent"]))
        msg = format_top_deal(best)
        btn = make_share_button(best["asin"])
        if send_telegram(msg, best.get("image_url"), btn):
            mark_as_posted(posted, best["asin"])
            mark_as_posted(posted, "TOP_DEAL")
            save_posted(posted)
            save_deal_stat(best)
            all_deals.remove(best)
            time.sleep(POST_INTERVAL_SECONDS)

    # Separa flash deals
    flash_deals = [d for d in all_deals if d["discount_percent"] >= FLASH_DEAL_PERCENT]
    normal_deals = [d for d in all_deals if d["discount_percent"] < FLASH_DEAL_PERCENT]

    # Pubblica flash deals (intervallo ridotto)
    for deal in flash_deals:
        if not is_publish_time():
            break
        if is_already_posted(posted, deal["asin"]):
            continue
        dn = len([k for k in posted.get(today, []) if not k.startswith(("GOOD_", "WEEKLY_", "EVENING_", "TOP_"))]) + 1
        print("  FLASH #{} {}... (-{}%)".format(dn, deal["title"][:40], deal["discount_percent"]))
        msg = format_flash_deal(deal, dn)
        btn = make_share_button(deal["asin"])
        if send_telegram(msg, deal.get("image_url"), btn):
            mark_as_posted(posted, deal["asin"])
            save_posted(posted)
            save_deal_stat(deal)
            time.sleep(FLASH_INTERVAL_SECONDS)

    # Ordina normali: top prima, poi shuffle
    normal_deals.sort(key=lambda d: d["discount_percent"], reverse=True)
    top5 = normal_deals[:5]
    rest = normal_deals[5:]
    random.shuffle(rest)
    normal_deals = top5 + rest

    if len(normal_deals) > MAX_POSTS_TOTAL:
        normal_deals = normal_deals[:MAX_POSTS_TOTAL]

    for deal in normal_deals:
        if not is_publish_time():
            print("Orario scaduto. Stop.")
            break
        if is_already_posted(posted, deal["asin"]):
            continue
        dn = len([k for k in posted.get(today, []) if not k.startswith(("GOOD_", "WEEKLY_", "EVENING_", "TOP_"))]) + 1
        print("  #{} [{}] {}... (-{}%)".format(dn, deal["_category"], deal["title"][:40], deal["discount_percent"]))
        msg = format_deal_message(deal, dn)
        btn = make_share_button(deal["asin"])
        if send_telegram(msg, deal.get("image_url"), btn):
            mark_as_posted(posted, deal["asin"])
            save_posted(posted)
            save_deal_stat(deal)
            time.sleep(POST_INTERVAL_SECONDS)

    total = len([k for k in posted.get(today, []) if not k.startswith(("GOOD_", "WEEKLY_", "EVENING_", "TOP_"))])
    print("\nFatto! Totale offerte oggi: {}".format(total))


if __name__ == "__main__":
    main()
