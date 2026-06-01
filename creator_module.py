"""
Modulo Creator per Sottocosto Oggi Bot v3
Design migliorato: font Poppins, glow effects, prezzi affiancati, spazio link in storia.
"""

import os
import re
import io
import math
import random
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Colori del brand (RGB)
COLORS = {
    'rosso': (211, 32, 39),
    'rosso_dark': (139, 20, 25),
    'oro': (244, 196, 48),
    'oro_bright': (255, 215, 0),
    'oro_glow': (255, 200, 50),
    'blu': (10, 22, 51),
    'blu_light': (26, 40, 81),
    'white': (255, 255, 255),
    'gray': (170, 170, 170),
}

# Font Poppins (Google Fonts) - moderno e d'impatto
# Fallback su DejaVu se non disponibile
FONT_PATHS = {
    'bold': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
    ],
    'regular': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ],
    'medium': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf',
        '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ],
}


def get_font(size, weight='bold'):
    """Carica font con fallback su font di sistema."""
    for path in FONT_PATHS.get(weight, FONT_PATHS['bold']):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def extract_asin(url):
    """Estrae ASIN da URL Amazon. Supporta anche link brevi (amzn.to, amzn.eu)
    risolvendoli con una HEAD request per ottenere l'URL finale."""
    # Cerca ASIN diretto in URL completo
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    if m:
        return m.group(1)
    m = re.search(r'/gp/product/([A-Z0-9]{10})', url)
    if m:
        return m.group(1)

    # Se e' un link breve, segui i redirect
    if 'amzn.to' in url or 'amzn.eu' in url or 'amzn.asia' in url or 'a.co/d/' in url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            resp = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
            final_url = resp.url
            # Cerca ASIN nell'URL finale
            m = re.search(r'/dp/([A-Z0-9]{10})', final_url)
            if m:
                return m.group(1)
            m = re.search(r'/gp/product/([A-Z0-9]{10})', final_url)
            if m:
                return m.group(1)
        except Exception:
            pass

    return None


def fmt_price(value):
    return "{:.2f}".format(value).replace('.', ',') + "€"


def get_product_data(api, asin, partner_tag):
    """Recupera dati prodotto usando search_items (metodo che funziona
    sicuramente in questa versione della libreria amazon_creatorsapi).
    Cerca l'ASIN come keyword e filtra il match esatto."""

    # search_items e' il metodo che gia' usa bot.py senza problemi
    # Cerco col solo ASIN come keyword (Amazon spesso lo trova)
    item = None
    try:
        # Disabilito min_saving_percent per accettare qualsiasi prodotto
        results = api.search_items(keywords=asin, item_count=10)
        if results and results.items:
            # Cerca il match esatto dell'ASIN tra i risultati
            for it in results.items:
                if it.asin == asin:
                    item = it
                    break
            # Se non trovato esatto, prendi il primo (Amazon ordina per rilevanza)
            if not item and results.items:
                item = results.items[0]
                # Verifica che almeno sia un prodotto reale
                if item.asin != asin:
                    print("[CREATOR] ASIN richiesto: {} ma trovato: {}".format(asin, item.asin), flush=True)
    except Exception as e:
        return None, "Errore API: {}".format(str(e)[:100])

    if not item:
        return None, "Prodotto non trovato su Amazon (ASIN: {})".format(asin)

    # Aggiorna l'ASIN con quello effettivamente trovato (per coerenza link)
    actual_asin = item.asin
    data = {'asin': actual_asin}

    try:
        data['title'] = item.item_info.title.display_value
    except (AttributeError, TypeError):
        return None, "Titolo non trovato"

    title = data['title']
    title = re.sub(r'\s+', ' ', title).strip()
    cut = title.find(', ')
    if 30 < cut < 100:
        title = title[:cut]
    if len(title) > 80:
        title = title[:80] + '...'
    data['title_short'] = title

    try:
        listing = item.offers_v2.listings[0]
        p = listing.price
        data['current_price'] = p.money.amount
        if p.saving_basis and p.saving_basis.money:
            data['original_price'] = p.saving_basis.money.amount
        else:
            data['original_price'] = data['current_price']
        if p.savings and p.savings.percentage:
            data['discount_percent'] = p.savings.percentage
        else:
            data['discount_percent'] = 0
            if data['original_price'] > data['current_price']:
                data['discount_percent'] = round(
                    ((data['original_price'] - data['current_price']) / data['original_price']) * 100
                )
    except (AttributeError, TypeError, IndexError):
        return None, "Prezzi non disponibili per questo prodotto"

    try:
        data['image_url'] = item.images.primary.large.url
    except (AttributeError, TypeError):
        data['image_url'] = None

    data['affiliate_url'] = "https://www.amazon.it/dp/{}?tag={}".format(actual_asin, partner_tag)
    return data, None


def download_image(url):
    if not url:
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return Image.open(io.BytesIO(resp.content)).convert('RGBA')
    except Exception:
        pass
    return None


def draw_centered_text(draw, text, x, y, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Offset per centratura verticale (bbox include il padding del font)
    draw.text((x - tw // 2, y - th // 2 - bbox[1] // 2), text, font=font, fill=fill)


def draw_text_with_glow(draw, text, x, y, font, fill, glow_color, glow_size=8, img=None):
    """Disegna testo con effetto glow (alone luminoso)."""
    if img is None:
        # Fallback: solo testo senza glow
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw // 2, y - th // 2 - bbox[1] // 2), text, font=font, fill=fill)
        return

    # Crea layer per glow
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    bbox = gd.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Disegna testo glow color
    gd.text((x - tw // 2, y - th // 2 - bbox[1] // 2), text, font=font,
            fill=glow_color + (180,))
    # Blur per effetto bagliore
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_size))
    img.paste(glow, (0, 0), glow)
    # Testo principale sopra
    draw.text((x - tw // 2, y - th // 2 - bbox[1] // 2), text, font=font, fill=fill)


def draw_text_wrapped(draw, text, x, y, font, fill, max_width, line_height, max_lines=None):
    """Disegna testo a capo automatico (centrato sull'asse X)."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while True:
            bbox = draw.textbbox((0, 0), last + '...', font=font)
            if bbox[2] - bbox[0] <= max_width or len(last) <= 3:
                break
            last = last[:-1]
        lines[-1] = last + '...'

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw // 2, y), line, font=font, fill=fill)
        y += line_height
    return y


def draw_text_wrapped_left(draw, text, x, y, font, fill, max_width, line_height, max_lines=None):
    """Allineato a sinistra."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while True:
            bbox = draw.textbbox((0, 0), last + '...', font=font)
            if bbox[2] - bbox[0] <= max_width or len(last) <= 3:
                break
            last = last[:-1]
        lines[-1] = last + '...'

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def draw_radial_background(img, center_x, center_y, max_radius):
    draw = ImageDraw.Draw(img)
    for r in range(max_radius, 0, -8):
        t = r / max_radius
        color = tuple(
            int(COLORS['blu_light'][i] * (1 - t) + COLORS['blu'][i] * t)
            for i in range(3)
        )
        draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=color)


def draw_rays(img, center_x, center_y, num_rays=24, alpha=20):
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_dist = max(img.size) * 1.5
    half_angle = math.pi / num_rays / 2
    for i in range(num_rays):
        if i % 2 == 1:
            continue
        angle = (math.pi * 2 / num_rays) * i
        x1 = center_x + math.cos(angle - half_angle) * max_dist
        y1 = center_y + math.sin(angle - half_angle) * max_dist
        x2 = center_x + math.cos(angle + half_angle) * max_dist
        y2 = center_y + math.sin(angle + half_angle) * max_dist
        draw.polygon([(center_x, center_y), (x1, y1), (x2, y2)],
                     fill=(255, 215, 0, alpha))
    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


def add_sparkles(img, count=40):
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(count):
        x = random.randint(0, img.width)
        y = random.randint(0, img.height)
        r = random.randint(2, 5)
        alpha = random.randint(120, 220)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 215, 0, alpha))
    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


def add_glow_layer(img, x, y, w, h, color, blur=30):
    """Aggiunge un alone luminoso intorno a un'area."""
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rectangle([x, y, x + w, y + h], fill=color + (100,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=blur))
    return Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')


def draw_placeholder_box(draw, x, y, w, h, text="IMMAGINE NON DISPONIBILE"):
    draw.rectangle([x, y, x + w, y + h], fill=COLORS['white'])
    font = get_font(28)
    draw_centered_text(draw, text, x + w // 2, y + h // 2, font, COLORS['gray'])


def paste_product_image(img, prod_img, box_x, box_y, box_w, box_h):
    if not prod_img:
        return
    ratio = min(box_w / prod_img.width, box_h / prod_img.height) * 0.92
    new_w = int(prod_img.width * ratio)
    new_h = int(prod_img.height * ratio)
    prod_img = prod_img.resize((new_w, new_h), Image.LANCZOS)
    cx = box_x + box_w // 2
    cy = box_y + box_h // 2
    img.paste(prod_img, (cx - new_w // 2, cy - new_h // 2),
              prod_img if prod_img.mode == 'RGBA' else None)


def draw_brand_header(draw, x, y, scale=1.0):
    """Logo brand SOTTOCOSTO OGGI come header testuale stilizzato."""
    # SOTTOCOSTO grande in oro
    font_big = get_font(int(56 * scale))
    draw_centered_text(draw, "SOTTOCOSTO", x, y, font_big, COLORS['oro_bright'])
    # OGGI piu piccolo, sotto, in bianco/oro
    font_med = get_font(int(38 * scale))
    draw_centered_text(draw, "OGGI", x, y + int(55 * scale), font_med, COLORS['white'])


# ============================================================
# STORIA INSTAGRAM 1080x1920
# ============================================================

def generate_story(data):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), COLORS['blu'])

    draw_radial_background(img, W // 2, H // 2, 1300)
    img = draw_rays(img, W // 2, H // 2, num_rays=24, alpha=18)
    img = add_sparkles(img, count=60)

    draw = ImageDraw.Draw(img)

    # ============ LOGO BRAND IN ALTO ============
    draw_brand_header(draw, W // 2, 70)

    # Divisore decorativo oro
    draw.line([(280, 200), (800, 200)], fill=COLORS['oro_bright'], width=3)
    # Diamantino centrale
    cx_d, cy_d = W // 2, 200
    draw.polygon([(cx_d, cy_d - 10), (cx_d + 10, cy_d), (cx_d, cy_d + 10), (cx_d - 10, cy_d)],
                 fill=COLORS['oro_bright'])

    # ============ STRISCIONE OFFERTA AMAZON ============
    draw.polygon([(60, 240), (1020, 240), (1020, 350), (540, 395), (60, 350)],
                 fill=COLORS['rosso'], outline=COLORS['oro_bright'], width=5)
    font_title = get_font(64)
    draw_centered_text(draw, "OFFERTA AMAZON", W // 2, 300, font_title, COLORS['oro_bright'])

    # ============ BADGE SCONTO CIRCOLARE ============
    cx, cy, cr = W // 2, 540, 145
    img = add_glow_layer(img, cx - cr - 30, cy - cr - 30, cr * 2 + 60, cr * 2 + 60,
                         COLORS['rosso'], blur=40)
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                 fill=COLORS['rosso'], outline=COLORS['oro_bright'], width=10)
    pct_text = "-{}%".format(data['discount_percent'])
    font_pct = get_font(95)
    draw_centered_text(draw, pct_text, cx, cy, font_pct, COLORS['oro_bright'])

    # ============ CORNICE IMMAGINE PRODOTTO ============
    img_x, img_y, img_w, img_h = 165, 740, 750, 750
    draw.rectangle([img_x, img_y, img_x + img_w, img_y + img_h], fill=COLORS['oro_bright'])
    pad = 18
    draw.rectangle([img_x + pad, img_y + pad, img_x + img_w - pad, img_y + img_h - pad],
                   fill=COLORS['white'])

    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product_image(img, prod_img, img_x + pad, img_y + pad, img_w - 2*pad, img_h - 2*pad)
        draw = ImageDraw.Draw(img)
    else:
        draw_placeholder_box(draw, img_x + pad, img_y + pad, img_w - 2*pad, img_h - 2*pad)

    # ============ NOME PRODOTTO ============
    font_name = get_font(42)
    draw_text_wrapped(draw, data['title_short'], W // 2, 1530,
                      font_name, COLORS['white'], 1000, 52, max_lines=3)

    # ============ PREZZI AFFIANCATI ============
    # Layout: PREZZO_ORIGINALE_BARRATO  ➜  PREZZO_NUOVO
    saving = data['original_price'] - data['current_price']

    orig_text = fmt_price(data['original_price'])
    sc_text = fmt_price(data['current_price'])

    # Misura larghezze
    font_orig = get_font(50, 'regular')
    font_sc = get_font(100)
    bbox_orig = draw.textbbox((0, 0), orig_text, font=font_orig)
    w_orig = bbox_orig[2] - bbox_orig[0]
    h_orig = bbox_orig[3] - bbox_orig[1]
    bbox_sc = draw.textbbox((0, 0), sc_text, font=font_sc)
    w_sc = bbox_sc[2] - bbox_sc[0]
    h_sc = bbox_sc[3] - bbox_sc[1]

    # Larghezza freccia
    arrow_w = 60
    gap = 35
    total_w = w_orig + gap + arrow_w + gap + w_sc
    start_x = (W - total_w) // 2

    # Baseline comune (centro verticale del prezzo scontato)
    y_baseline = 1760
    sc_y = y_baseline - h_sc // 2
    # Prezzo originale piu' piccolo, centrato verticalmente sulla stessa baseline
    orig_y = y_baseline - h_orig // 2

    # Prezzo originale barrato
    draw.text((start_x, orig_y), orig_text, font=font_orig, fill=COLORS['gray'])
    line_y = orig_y + h_orig // 2 + 5
    draw.line([(start_x - 8, line_y), (start_x + w_orig + 8, line_y)],
              fill=COLORS['rosso'], width=5)

    # Freccia oro
    arrow_x = start_x + w_orig + gap
    arrow_y = y_baseline
    draw.line([(arrow_x, arrow_y), (arrow_x + arrow_w - 18, arrow_y)],
              fill=COLORS['oro_bright'], width=6)
    draw.polygon([(arrow_x + arrow_w, arrow_y),
                  (arrow_x + arrow_w - 20, arrow_y - 14),
                  (arrow_x + arrow_w - 20, arrow_y + 14)],
                 fill=COLORS['oro_bright'])

    # Prezzo scontato con glow
    sc_x = arrow_x + arrow_w + gap
    img = add_glow_layer(img, sc_x - 20, sc_y - 15, w_sc + 40, h_sc + 30,
                         COLORS['oro_bright'], blur=30)
    draw = ImageDraw.Draw(img)
    draw.text((sc_x, sc_y), sc_text, font=font_sc, fill=COLORS['oro_bright'])

    # ============ SPAZIO VUOTO PER LINK INSTAGRAM ============
    # Lasciamo libero y 1870-1920 per il sticker link IG

    return img


# ============================================================
# POST QUADRATO 1080x1080
# ============================================================

def generate_post(data):
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), COLORS['blu'])

    draw_radial_background(img, W // 2, H // 2, 900)
    img = draw_rays(img, W // 2, H // 2, num_rays=20, alpha=16)
    img = add_sparkles(img, count=35)

    draw = ImageDraw.Draw(img)

    # ============ HEADER BRAND CENTRATO IN ALTO ============
    draw_brand_header(draw, W // 2, 40, scale=0.65)

    # Divisore decorativo
    draw.line([(380, 130), (700, 130)], fill=COLORS['oro_bright'], width=2)

    # ============ PANNELLO IMMAGINE SINISTRO ============
    img_x, img_y, img_w, img_h = 40, 240, 460, 620
    draw.rectangle([img_x, img_y, img_x + img_w, img_y + img_h], fill=COLORS['oro_bright'])
    pad = 14
    draw.rectangle([img_x + pad, img_y + pad, img_x + img_w - pad, img_y + img_h - pad],
                   fill=COLORS['white'])

    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product_image(img, prod_img, img_x + pad, img_y + pad, img_w - 2*pad, img_h - 2*pad)
        draw = ImageDraw.Draw(img)
    else:
        draw_placeholder_box(draw, img_x + pad, img_y + pad, img_w - 2*pad, img_h - 2*pad,
                            text="NO IMG")

    # ============ BADGE SCONTO sopra immagine ============
    img = add_glow_layer(img, 20, 145, 500, 100, COLORS['rosso'], blur=25)
    draw = ImageDraw.Draw(img)
    draw.polygon([(40, 160), (500, 160), (500, 245), (270, 270), (40, 245)],
                 fill=COLORS['rosso'], outline=COLORS['oro_bright'], width=4)
    font_pct = get_font(75)
    pct_text = "-{}%".format(data['discount_percent'])
    draw_centered_text(draw, pct_text, 270, 205, font_pct, COLORS['oro_bright'])

    # ============ HANDLE CANALE in basso a sinistra ============
    font_chan = get_font(28)
    draw_centered_text(draw, "@sottocosto_oggi", 270, 905, font_chan, COLORS['oro_bright'])
    font_sm = get_font(20, 'regular')
    draw_centered_text(draw, "su Telegram", 270, 945, font_sm, COLORS['white'])

    # ============ PANNELLO DESTRO ============
    # Striscione titolo
    img = add_glow_layer(img, 540, 145, 500, 100, COLORS['rosso'], blur=20)
    draw = ImageDraw.Draw(img)
    draw.rectangle([560, 160, 1040, 250], fill=COLORS['rosso'],
                   outline=COLORS['oro_bright'], width=3)
    font_h = get_font(36)
    draw_centered_text(draw, "OFFERTA AMAZON", 800, 205, font_h, COLORS['oro_bright'])

    # Nome prodotto (allineato a sinistra)
    font_name = get_font(34)
    draw_text_wrapped_left(draw, data['title_short'], 570, 290,
                           font_name, COLORS['white'], 460, 46, max_lines=4)

    # ============ PREZZI AFFIANCATI ============
    # Box prezzi con glow
    img = add_glow_layer(img, 540, 530, 500, 200, COLORS['oro_bright'], blur=20)
    draw = ImageDraw.Draw(img)
    draw.rectangle([560, 550, 1040, 730], fill=(0, 0, 0),
                   outline=COLORS['oro_bright'], width=4)

    saving = data['original_price'] - data['current_price']
    orig_text = fmt_price(data['original_price'])
    sc_text = fmt_price(data['current_price'])

    font_orig_p = get_font(32, 'regular')
    font_sc_p = get_font(64)
    bbox_orig_p = draw.textbbox((0, 0), orig_text, font=font_orig_p)
    w_orig_p = bbox_orig_p[2] - bbox_orig_p[0]
    h_orig_p = bbox_orig_p[3] - bbox_orig_p[1]
    bbox_sc_p = draw.textbbox((0, 0), sc_text, font=font_sc_p)
    w_sc_p = bbox_sc_p[2] - bbox_sc_p[0]
    h_sc_p = bbox_sc_p[3] - bbox_sc_p[1]

    # Layout: orig ➜ scont, centrato nel box (560 - 1040, box center = 800)
    arrow_w_p = 40
    gap_p = 25
    total_w_p = w_orig_p + gap_p + arrow_w_p + gap_p + w_sc_p
    box_center = 800
    start_x_p = box_center - total_w_p // 2

    # Baseline al centro del box prezzi (box va da y=550 a y=730, centro=640)
    y_baseline_p = 640
    sc_y_p = y_baseline_p - h_sc_p // 2
    orig_y_p = y_baseline_p - h_orig_p // 2

    # Prezzo originale
    draw.text((start_x_p, orig_y_p), orig_text, font=font_orig_p, fill=COLORS['gray'])
    line_y_p = orig_y_p + h_orig_p // 2 + 4
    draw.line([(start_x_p - 5, line_y_p), (start_x_p + w_orig_p + 5, line_y_p)],
              fill=COLORS['rosso'], width=4)

    # Freccia
    ax = start_x_p + w_orig_p + gap_p
    ay = y_baseline_p
    draw.line([(ax, ay), (ax + arrow_w_p - 13, ay)], fill=COLORS['oro_bright'], width=5)
    draw.polygon([(ax + arrow_w_p, ay),
                  (ax + arrow_w_p - 15, ay - 10),
                  (ax + arrow_w_p - 15, ay + 10)],
                 fill=COLORS['oro_bright'])

    # Prezzo scontato
    sc_x_p = ax + arrow_w_p + gap_p
    draw.text((sc_x_p, sc_y_p), sc_text, font=font_sc_p, fill=COLORS['oro_bright'])

    # Risparmi
    if saving > 0:
        font_rsp = get_font(22)
        rsp_text = "RISPARMI {}".format(fmt_price(saving))
        draw_centered_text(draw, rsp_text, 800, 710, font_rsp, COLORS['white'])

    # CTA bottone con glow
    img = add_glow_layer(img, 540, 800, 500, 130, COLORS['oro_bright'], blur=20)
    draw = ImageDraw.Draw(img)
    draw.rectangle([560, 820, 1040, 940], fill=COLORS['oro_bright'])
    font_cta = get_font(34)
    draw_centered_text(draw, "LINK IN BIO", 800, 855, font_cta, COLORS['blu'])
    font_cta2 = get_font(22, 'regular')
    draw_centered_text(draw, "per altre offerte", 800, 905, font_cta2, COLORS['blu'])

    return img


# ============================================================
# CAPTION
# ============================================================

def generate_caption(data):
    saving = data['original_price'] - data['current_price']
    return (
        "🔥 OFFERTA AMAZON -{pct}%\n\n"
        "{title}\n\n"
        "💰 Da {orig} a {sc}\n"
        "💸 Risparmi {sv}\n\n"
        "⚡ Su Amazon ora!\n\n"
        "Altre offerte come questa ogni giorno sul mio canale Telegram:\n"
        "👉 t.me/sottocosto_oggi\n\n"
        "#offerte #amazon #sconti #risparmio #shopping #affari #deal #sottocostoOggi #italia"
    ).format(
        pct=data['discount_percent'],
        title=data['title_short'],
        orig=fmt_price(data['original_price']),
        sc=fmt_price(data['current_price']),
        sv=fmt_price(saving),
    )


def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


def handle_creator_command(api, url, partner_tag):
    asin = extract_asin(url)
    if not asin:
        return None, None, None, ("❌ Link Amazon non valido o non risolvibile.\n\n"
                                   "Formati supportati:\n"
                                   "• https://www.amazon.it/dp/CODICE\n"
                                   "• https://amzn.to/CODICE\n"
                                   "• https://amzn.eu/d/CODICE")

    # Log dell'ASIN estratto per debug
    print("[CREATOR] ASIN estratto: {}".format(asin), flush=True)

    data, err = get_product_data(api, asin, partner_tag)
    if err:
        return None, None, None, "❌ {}".format(err)

    # Nota: NON blocchiamo se non c'e' sconto - il creator e' utile anche
    # per generare grafiche di prodotti a prezzo pieno
    if data.get('discount_percent', 0) == 0:
        # Imposto discount minimo per non avere divisioni per zero nei layout
        data['discount_percent'] = 0
        # Se non c'e' un prezzo originale > corrente, lo settiamo uguale
        if data.get('original_price', 0) <= data.get('current_price', 0):
            data['original_price'] = data['current_price']

    try:
        storia = generate_story(data)
        post = generate_post(data)
        caption = generate_caption(data)
        return image_to_bytes(storia), image_to_bytes(post), caption, None
    except Exception as e:
        return None, None, None, "❌ Errore generazione: {}".format(str(e)[:100])
