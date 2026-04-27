"""
Sottocosto Oggi — Bot Telegram
Recupera offerte da Amazon PA-API 5.0 e le pubblica su @sottocosto_oggi.
"""

import os
import json
import hashlib
import hmac
import datetime
import requests
from pathlib import Path

# ============================================================
# CONFIGURAZIONE (da GitHub Secrets o variabili d'ambiente)
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")  # es: @mio_canale o -100123456789

AMAZON_ACCESS_KEY = os.environ.get("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.environ.get("AMAZON_SECRET_KEY", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")  # es: miotag-21
AMAZON_MARKETPLACE = os.environ.get("AMAZON_MARKETPLACE", "www.amazon.it")
AMAZON_REGION = os.environ.get("AMAZON_REGION", "eu-west-1")

# Soglia minima di sconto (%) per pubblicare l'offerta
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "20"))

# File per tracciare offerte già pubblicate (evita duplicati)
POSTED_FILE = Path(__file__).parent / "posted_deals.json"

# Categorie da cercare (Browse Node IDs per Amazon.it)
# Puoi trovare i nodi su: https://www.amazon.it/gp/bestsellers/
SEARCH_CATEGORIES = [
    "Elettronica",
    "Informatica",
    "Casa e cucina",
    "Sport e tempo libero",
    "Videogiochi",
]


# ============================================================
# AMAZON PA-API 5.0 - Firma AWS v4
# ============================================================
def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, service)
    k_signing = sign(k_service, "aws4_request")
    return k_signing


def amazon_api_request(payload: dict) -> dict:
    """Esegue una richiesta firmata alla PA-API 5.0."""
    service = "ProductAdvertisingAPI"
    host = f"webservices.{AMAZON_MARKETPLACE}"
    endpoint = f"https://{host}/paapi5/searchitems"
    content_type = "application/json; charset=UTF-8"

    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Headers canonici
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems\n"
    )
    signed_headers = "content-type;host;x-amz-date;x-amz-target"

    payload_json = json.dumps(payload)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    canonical_request = (
        f"POST\n/paapi5/searchitems\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{AMAZON_REGION}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    signing_key = get_signature_key(AMAZON_SECRET_KEY, date_stamp, AMAZON_REGION, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={AMAZON_ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
        "Authorization": authorization,
    }

    response = requests.post(endpoint, headers=headers, data=payload_json, timeout=15)
    response.raise_for_status()
    return response.json()


# ============================================================
# RICERCA OFFERTE
# ============================================================
def search_deals(keyword: str, max_results: int = 10) -> list[dict]:
    """Cerca prodotti in offerta per una categoria/keyword."""
    payload = {
        "PartnerTag": AMAZON_PARTNER_TAG,
        "PartnerType": "Associates",
        "Keywords": keyword,
        "SearchIndex": "All",
        "ItemCount": max_results,
        "Resources": [
            "ItemInfo.Title",
            "Offers.Listings.Price",
            "Offers.Listings.SavingBasis",  # prezzo originale
            "Offers.Listings.MerchantInfo",
            "Images.Primary.Large",
            "ItemInfo.Features",
        ],
        "Marketplace": AMAZON_MARKETPLACE,
    }

    try:
        data = amazon_api_request(payload)
    except requests.exceptions.HTTPError as e:
        print(f"[ERRORE API] {keyword}: {e}")
        return []

    deals = []
    for item in data.get("SearchResult", {}).get("Items", []):
        deal = parse_item(item)
        if deal and deal["discount_percent"] >= MIN_DISCOUNT_PERCENT:
            deals.append(deal)

    return deals


def parse_item(item: dict) -> dict | None:
    """Estrae le informazioni utili da un item della PA-API."""
    try:
        asin = item["ASIN"]
        title = item["ItemInfo"]["Title"]["DisplayValue"]
        url = item["DetailPageURL"]

        listing = item["Offers"]["Listings"][0]
        current_price = listing["Price"]["Amount"]
        currency = listing["Price"]["Currency"]

        # Prezzo originale (SavingBasis)
        original_price = None
        if "SavingBasis" in listing:
            original_price = listing["SavingBasis"]["Amount"]

        if not original_price or original_price <= current_price:
            return None

        discount = original_price - current_price
        discount_percent = round((discount / original_price) * 100)

        image_url = None
        try:
            image_url = item["Images"]["Primary"]["Large"]["URL"]
        except (KeyError, TypeError):
            pass

        return {
            "asin": asin,
            "title": title,
            "url": url,
            "current_price": current_price,
            "original_price": original_price,
            "discount": discount,
            "discount_percent": discount_percent,
            "currency": currency,
            "image_url": image_url,
        }
    except (KeyError, IndexError, TypeError) as e:
        print(f"[PARSE] Errore parsing item: {e}")
        return None


# ============================================================
# TELEGRAM
# ============================================================
def send_telegram_message(text: str, photo_url: str | None = None) -> bool:
    """Invia un messaggio (con foto opzionale) al canale Telegram."""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    try:
        if photo_url:
            resp = requests.post(
                f"{base_url}/sendPhoto",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "photo": photo_url,
                    "caption": text,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
        else:
            resp = requests.post(
                f"{base_url}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )

        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"[TELEGRAM] Errore invio: {e}")
        return False


def format_deal_message(deal: dict) -> str:
    """Formatta il messaggio Telegram per un'offerta."""
    # Emoji in base allo sconto
    if deal["discount_percent"] >= 50:
        fire = "🔥🔥🔥"
    elif deal["discount_percent"] >= 30:
        fire = "🔥🔥"
    else:
        fire = "🔥"

    msg = (
        f"{fire} <b>-{deal['discount_percent']}%</b> {fire}\n\n"
        f"📦 <b>{deal['title'][:200]}</b>\n\n"
        f"💰 <s>{deal['original_price']:.2f}€</s> ➜ <b>{deal['current_price']:.2f}€</b>\n"
        f"💸 Risparmi: {deal['discount']:.2f}€\n\n"
        f'🛒 <a href="{deal["url"]}">VAI ALL\'OFFERTA</a>\n\n'
        f"━━━━━━━━━━━━━━━\n"
        f"📣 @sottocosto_oggi\n"
        f"#offerta #amazon #sconto{deal['discount_percent']}"
    )
    return msg


# ============================================================
# GESTIONE DUPLICATI
# ============================================================
def load_posted() -> set:
    """Carica gli ASIN già pubblicati."""
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text())
            return set(data)
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_posted(posted: set):
    """Salva gli ASIN pubblicati. Mantiene solo gli ultimi 500."""
    recent = list(posted)[-500:]
    POSTED_FILE.write_text(json.dumps(recent))


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"🏷️ Sottocosto Oggi Bot - Avvio {datetime.datetime.now().isoformat()}")
    print(f"📢 Canale: {TELEGRAM_CHANNEL_ID}")
    print(f"🏷️ Partner Tag: {AMAZON_PARTNER_TAG}")
    print(f"📉 Sconto minimo: {MIN_DISCOUNT_PERCENT}%")

    # Validazione configurazione
    missing = []
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "AMAZON_ACCESS_KEY",
                "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"❌ Variabili mancanti: {', '.join(missing)}")
        return

    posted = load_posted()
    new_deals_count = 0

    for category in SEARCH_CATEGORIES:
        print(f"\n🔍 Cerco offerte: {category}")
        deals = search_deals(category)
        print(f"   Trovate {len(deals)} offerte con sconto >= {MIN_DISCOUNT_PERCENT}%")

        for deal in deals:
            if deal["asin"] in posted:
                print(f"   ⏭️ Già pubblicata: {deal['asin']}")
                continue

            print(f"   📤 Pubblico: {deal['title'][:60]}... (-{deal['discount_percent']}%)")
            message = format_deal_message(deal)
            success = send_telegram_message(message, deal.get("image_url"))

            if success:
                posted.add(deal["asin"])
                new_deals_count += 1
                print(f"   ✅ Pubblicata!")
            else:
                print(f"   ❌ Errore invio")

            # Pausa per evitare rate limiting Telegram (max 20 msg/min per canale)
            import time
            time.sleep(3)

    save_posted(posted)
    print(f"\n✅ Completato! {new_deals_count} nuove offerte pubblicate.")


if __name__ == "__main__":
    main()
