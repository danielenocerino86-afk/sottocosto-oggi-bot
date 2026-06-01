"""
Modulo Creator per Sottocosto Oggi Bot v5 PRO
Design corretto: allineamenti, gerarchia, compattezza.
"""

CREATOR_VERSION = "v5.0-PRO"

import os
import re
import io
import math
import random
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Palette
C = {
    'bg_dark': (8, 14, 35),
    'bg_mid': (18, 28, 60),
    'bg_light': (28, 42, 80),
    'accent': (255, 71, 87),
    'accent_dark': (200, 35, 50),
    'gold': (255, 200, 60),
    'gold_bright': (255, 220, 100),
    'white': (255, 255, 255),
    'off_white': (240, 240, 245),
    'gray': (140, 145, 160),
    'gray_dark': (80, 85, 100),
}

FONT_PATHS = {
    'bold': ['/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
    'medium': ['/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf',
               '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
               '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
    'regular': ['/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
    'light': ['/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf',
              '/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
}


def get_font(size, weight='bold'):
    for path in FONT_PATHS.get(weight, FONT_PATHS['bold']):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def extract_asin(url):
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    if m:
        return m.group(1)
    m = re.search(r'/gp/product/([A-Z0-9]{10})', url)
    if m:
        return m.group(1)
    if 'amzn.to' in url or 'amzn.eu' in url or 'amzn.asia' in url or 'a.co/d/' in url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            resp = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
            final_url = resp.url
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
    return "{:.2f}".format(value).replace('.', ',') + " €"


def get_product_data(api, asin, partner_tag):
    item = None
    try:
        items = api.get_items([asin])
        if items and len(items) > 0:
            item = items[0]
            if item is None or (hasattr(item, 'asin') and item.asin is None):
                return None, "Prodotto non disponibile su Amazon (ASIN: {})".format(asin)
    except Exception as e:
        return None, "Errore API get_items: {}".format(str(e)[:120])

    if not item:
        return None, "Prodotto non trovato (ASIN: {})".format(asin)

    actual_asin = item.asin if hasattr(item, 'asin') else asin
    data = {'asin': actual_asin}

    try:
        data['title'] = item.item_info.title.display_value
    except (AttributeError, TypeError):
        return None, "Titolo non trovato"

    title = data['title']
    title = re.sub(r'\s+', ' ', title).strip()
    # Rimuovi marchi registrati e parentesi
    title = re.sub(r'®|™|©', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    cut = title.find(', ')
    if 30 < cut < 90:
        title = title[:cut]
    if len(title) > 65:
        title = title[:65].rstrip() + '...'
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
        try:
            listing = item.offers.listings[0]
            data['current_price'] = listing.price.amount
            data['original_price'] = data['current_price']
            data['discount_percent'] = 0
        except (AttributeError, TypeError, IndexError):
            return None, "Prezzi non disponibili"

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


# ===== HELPERS RENDERING =====

def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered(draw, text, cx, cy, font, fill):
    """Disegna testo PERFETTAMENTE centrato in (cx, cy)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    # bbox[1] e' il top offset (sopra la baseline)
    x = cx - w // 2 - bbox[0]
    y = cy - h // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def draw_left(draw, text, x, y, font, fill):
    """Disegna testo allineato a sinistra. y = top del testo."""
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((x - bbox[0], y - bbox[1]), text, font=font, fill=fill)


def wrap_text(draw, text, font, max_w, max_lines=3):
    """Wrappa testo. Ritorna lista righe."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        w, _ = text_size(draw, test, font)
        if w > max_w and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while text_size(draw, last + '...', font)[0] > max_w and len(last) > 3:
            last = last[:-1]
        lines[-1] = last + '...'
    return lines


def line_height(font):
    """Altezza riga consigliata per il font (1.2x ascender)."""
    return int(font.size * 1.25)


# ===== BACKGROUND EFFECTS =====

def make_background(W, H):
    """Sfondo blu radiale + raggi + glow angolari + noise."""
    img = Image.new('RGB', (W, H), C['bg_dark'])
    draw = ImageDraw.Draw(img)

    # Radiale dal centro
    cx, cy = W // 2, H // 2
    max_r = int(max(W, H) * 0.7)
    for r in range(max_r, 0, -6):
        t = r / max_r
        col = tuple(int(C['bg_light'][i] * (1 - t) + C['bg_dark'][i] * t) for i in range(3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # Raggi morbidi
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    max_d = max(W, H) * 1.5
    num = 18
    for i in range(0, num, 2):
        ang = (math.pi * 2 / num) * i
        ha = math.pi / num / 3
        x1 = cx + math.cos(ang - ha) * max_d
        y1 = cy + math.sin(ang - ha) * max_d
        x2 = cx + math.cos(ang + ha) * max_d
        y2 = cy + math.sin(ang + ha) * max_d
        od.polygon([(cx, cy), (x1, y1), (x2, y2)],
                   fill=(C['gold'][0], C['gold'][1], C['gold'][2], 10))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    # Glow angolari
    for pos, color, sz in [
        ('tl', C['accent'], 0.5),
        ('br', C['gold'], 0.4),
    ]:
        overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        ox = 0 if pos == 'tl' else W
        oy = 0 if pos == 'tl' else H
        radius = int(max(W, H) * sz)
        for r in range(radius, 0, -10):
            t = r / radius
            a = int(70 * (1 - t) ** 2)
            if a < 1:
                continue
            od.ellipse([ox - r, oy - r, ox + r, oy + r],
                       fill=(color[0], color[1], color[2], a))
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=50))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    # Noise sottile
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for _ in range(int(W * H / 2500)):
        x = random.randint(0, W)
        y = random.randint(0, H)
        col = random.choice([
            (255, 255, 255, 8),
            (255, 200, 60, 12),
        ])
        od.point((x, y), fill=col)
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    return img


def draw_glow_text(img, text, cx, cy, font, fill, glow_color, glow_size=12):
    """Testo centrato con glow morbido sotto. cx, cy = centro del testo."""
    W, H = img.size
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    bbox = gd.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]
    gd.text((x, y), text, font=font,
            fill=(glow_color[0], glow_color[1], glow_color[2], 200))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_size))
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img)
    draw.text((x, y), text, font=font, fill=fill)


def paste_product(img, prod, cx, cy, max_size):
    """Centra prodotto in (cx, cy) ridimensionando a max_size lato."""
    if not prod:
        return
    ratio = min(max_size / prod.width, max_size / prod.height)
    nw = int(prod.width * ratio)
    nh = int(prod.height * ratio)
    prod = prod.resize((nw, nh), Image.LANCZOS)
    img.paste(prod, (cx - nw // 2, cy - nh // 2),
              prod if prod.mode == 'RGBA' else None)


def rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    x1, y1, x2, y2 = xy
    if fill:
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.pieslice([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=fill)
        draw.pieslice([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=fill)
        draw.pieslice([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=fill)
        draw.pieslice([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=fill)
    if outline:
        draw.arc([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=outline, width=width)
        draw.arc([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=outline, width=width)
        draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=width)
        draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=width)
        draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=width)
        draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=width)


def draw_brand_header(img, cx, cy, scale=1.0):
    """Logo SOTTOCOSTO + OGGI (box rosso). cy = centro verticale del logo."""
    draw = ImageDraw.Draw(img)
    font_main = get_font(int(48 * scale))
    font_sub = get_font(int(20 * scale))

    sotto = "SOTTOCOSTO"
    oggi = "OGGI"

    sw, sh = text_size(draw, sotto, font_main)
    ow, oh = text_size(draw, oggi, font_sub)

    pad_h = int(12 * scale)
    pad_v = int(7 * scale)
    box_w = ow + pad_h * 2
    box_h = oh + pad_v * 2 + 6

    gap = int(16 * scale)
    total_w = sw + gap + box_w
    start_x = cx - total_w // 2

    # SOTTOCOSTO con glow - cx del testo = start_x + sw/2
    sotto_cx = start_x + sw // 2
    draw_glow_text(img, sotto, sotto_cx, cy, font_main,
                   C['gold_bright'], C['gold'], glow_size=8)
    draw = ImageDraw.Draw(img)

    # Box OGGI - centrato sulla stessa cy
    bx1 = start_x + sw + gap
    bx2 = bx1 + box_w
    by1 = cy - box_h // 2
    by2 = cy + box_h // 2
    rounded_rect(draw, (bx1, by1, bx2, by2), int(5 * scale), fill=C['accent'])
    # OGGI centrato nel box
    draw_centered(draw, oggi, (bx1 + bx2) // 2, cy, font_sub, C['white'])


def draw_separator(draw, cx, y, length=200, with_diamond=True):
    """Linea decorativa con diamantino centrale."""
    half = length // 2
    if with_diamond:
        # Linee con gap
        draw.line([(cx - half, y), (cx - 10, y)], fill=C['gold'], width=2)
        draw.line([(cx + 10, y), (cx + half, y)], fill=C['gold'], width=2)
        # Diamantino oro
        draw.polygon([(cx, y - 5), (cx + 5, y), (cx, y + 5), (cx - 5, y)],
                     fill=C['gold_bright'])
    else:
        draw.line([(cx - half, y), (cx + half, y)], fill=C['gold'], width=2)


def draw_discount_badge(img, cx, cy, percent, radius=80):
    """Badge sconto circolare premium."""
    if percent <= 0:
        return
    W, H = img.size

    # Glow
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - radius - 25, cy - radius - 25, cx + radius + 25, cy + radius + 25],
               fill=(C['accent'][0], C['accent'][1], C['accent'][2], 90))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=25))
    img.paste(glow, (0, 0), glow)

    draw = ImageDraw.Draw(img)
    # Anello oro
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=C['gold'])
    # Cerchio rosso interno
    inner = radius - 7
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=C['accent'])
    # Linea sottile interna
    inner2 = inner - 6
    draw.ellipse([cx - inner2, cy - inner2, cx + inner2, cy + inner2],
                 outline=C['gold_bright'], width=2)

    # Testo
    font_pct = get_font(int(radius * 0.55))
    draw_centered(draw, "-{}%".format(percent), cx, cy, font_pct, C['white'])


def draw_price_inline(img, cx, cy, orig, current, discount_pct,
                     orig_font_size=42, current_font_size=110, arrow_size=40,
                     show_arrow=True, gap=30):
    """Disegna prezzi affiancati: ORIG_BARRATO  →  CURRENT_BIG
    Centrato perfettamente in (cx, cy)."""
    draw = ImageDraw.Draw(img)

    orig_text = fmt_price(orig)
    curr_text = fmt_price(current)

    font_orig = get_font(orig_font_size, 'medium')
    font_curr = get_font(current_font_size, 'bold')

    ow, oh = text_size(draw, orig_text, font_orig)
    cw, ch = text_size(draw, curr_text, font_curr)

    show_orig = discount_pct > 0 and orig > current

    if show_orig:
        total_w = ow + gap + arrow_size + gap + cw
        start_x = cx - total_w // 2

        # Prezzo originale (allineato sulla baseline del prezzo corrente)
        # cy = centro del prezzo grande
        orig_y_center = cy
        # disegna orig centrato verticalmente su cy
        bbox_o = draw.textbbox((0, 0), orig_text, font=font_orig)
        ox = start_x
        oy = orig_y_center - (bbox_o[3] - bbox_o[1]) // 2 - bbox_o[1]
        draw.text((ox, oy), orig_text, font=font_orig, fill=C['gray'])
        # Barratura
        bar_y = orig_y_center + 2
        draw.line([(ox - 5, bar_y), (ox + ow + 5, bar_y)],
                  fill=C['accent'], width=3)

        # Freccia
        ax = start_x + ow + gap
        ay = orig_y_center
        draw.line([(ax, ay), (ax + arrow_size - 15, ay)], fill=C['gold_bright'], width=4)
        draw.polygon([(ax + arrow_size, ay),
                      (ax + arrow_size - 15, ay - 10),
                      (ax + arrow_size - 15, ay + 10)],
                     fill=C['gold_bright'])

        # Prezzo corrente con glow
        sc_x_center = start_x + ow + gap + arrow_size + gap + cw // 2
        draw_glow_text(img, curr_text, sc_x_center, cy, font_curr,
                       C['gold_bright'], C['gold'], glow_size=14)
    else:
        # Solo prezzo corrente, centrato
        draw_glow_text(img, curr_text, cx, cy, font_curr,
                       C['gold_bright'], C['gold'], glow_size=14)


# ============================================================
# STORIA 1080x1920
# ============================================================

def generate_story(data):
    W, H = 1080, 1920
    img = make_background(W, H)
    draw = ImageDraw.Draw(img)

    # ===== HEADER LOGO =====
    draw_brand_header(img, W // 2, 100, scale=1.3)
    draw = ImageDraw.Draw(img)

    # Separator
    draw_separator(draw, W // 2, 175, length=180)

    # ===== TAG "OFFERTA SU AMAZON" =====
    tag_y = 240
    tag_text = "OFFERTA SU AMAZON"
    font_tag = get_font(26, 'medium')
    tw, th = text_size(draw, tag_text, font_tag)
    pad = 20
    bh = 50
    bx1 = W // 2 - (tw // 2 + pad)
    bx2 = W // 2 + (tw // 2 + pad)
    by1 = tag_y - bh // 2
    by2 = tag_y + bh // 2
    rounded_rect(draw, (bx1, by1, bx2, by2), bh // 2,
                 outline=C['gold'], width=2)
    draw_centered(draw, tag_text, W // 2, tag_y, font_tag, C['gold_bright'])

    # ===== IMMAGINE PRODOTTO (gigante, centro) =====
    img_cy = 750
    img_size = 720

    # Glow morbido dietro
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - img_size // 2 - 30, img_cy - img_size // 2 - 30,
                W // 2 + img_size // 2 + 30, img_cy + img_size // 2 + 30],
               fill=(255, 255, 255, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=80))
    img.paste(glow, (0, 0), glow)

    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product(img, prod_img, W // 2, img_cy, img_size)
        draw = ImageDraw.Draw(img)
    else:
        # Placeholder
        rect_x1 = W // 2 - img_size // 2
        rect_y1 = img_cy - img_size // 2
        rounded_rect(draw, (rect_x1, rect_y1, rect_x1 + img_size, rect_y1 + img_size), 30,
                     fill=C['bg_mid'])
        font_ph = get_font(36, 'light')
        draw_centered(draw, "[ Immagine ]", W // 2, img_cy, font_ph, C['gray'])

    # ===== BADGE SCONTO sovrapposto top-right immagine =====
    if data['discount_percent'] > 0:
        badge_x = W // 2 + img_size // 2 - 60
        badge_y = img_cy - img_size // 2 + 40
        draw_discount_badge(img, badge_x, badge_y, data['discount_percent'], radius=105)
        draw = ImageDraw.Draw(img)

    # ===== NOME PRODOTTO =====
    name_y = 1230  # top della prima riga
    font_name = get_font(44, 'bold')
    lines = wrap_text(draw, data['title_short'], font_name, 980, max_lines=3)
    lh = 56
    for i, line in enumerate(lines):
        draw_centered(draw, line, W // 2, name_y + i * lh + lh // 2, font_name, C['white'])

    # Separator dopo nome
    sep_y = name_y + len(lines) * lh + 25
    draw_separator(draw, W // 2, sep_y, length=200)

    # ===== ETICHETTE DA / ORA SOLO =====
    if data['discount_percent'] > 0:
        font_lbl = get_font(24, 'light')
        draw_centered(draw, "DA  •  ORA SOLO", W // 2, sep_y + 50, font_lbl, C['gray'])

    # ===== PREZZI AFFIANCATI =====
    price_y = sep_y + 150
    draw_price_inline(img, W // 2, price_y,
                      data['original_price'], data['current_price'],
                      data['discount_percent'],
                      orig_font_size=46, current_font_size=130, arrow_size=44, gap=30)
    draw = ImageDraw.Draw(img)

    # Risparmi sotto
    if data['discount_percent'] > 0:
        saving = data['original_price'] - data['current_price']
        font_rsp = get_font(28, 'medium')
        rsp_y = price_y + 100
        draw_centered(draw, "Risparmi {}".format(fmt_price(saving)),
                      W // 2, rsp_y, font_rsp, C['gold'])

    # ===== FOOTER MINIMAL =====
    # Spazio vuoto a 1830+ per sticker link IG
    footer_y = 1835
    font_handle = get_font(28, 'medium')
    draw_centered(draw, "@sottocosto_oggi", W // 2, footer_y, font_handle, C['gold'])
    font_sub = get_font(18, 'light')
    draw_centered(draw, "scopri tutte le offerte su Telegram",
                  W // 2, footer_y + 35, font_sub, C['gray'])

    # Watermark versione
    font_v = get_font(9, 'light')
    draw.text((W - 60, H - 14), CREATOR_VERSION, font=font_v, fill=(50, 55, 70))

    return img


# ============================================================
# POST 1080x1080
# ============================================================

def generate_post(data):
    W, H = 1080, 1080
    img = make_background(W, H)
    draw = ImageDraw.Draw(img)

    # ===== HEADER LOGO =====
    draw_brand_header(img, W // 2, 70, scale=0.75)
    draw = ImageDraw.Draw(img)
    draw_separator(draw, W // 2, 130, length=220)

    # ===== LAYOUT 2 COLONNE =====
    # COLONNA SINISTRA: immagine prodotto (520x620)
    # COLONNA DESTRA: info (480px wide)

    left_cx = 280
    left_cy = 540
    left_size = 480

    # Glow dietro immagine
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([left_cx - left_size // 2 - 20, left_cy - left_size // 2 - 20,
                left_cx + left_size // 2 + 20, left_cy + left_size // 2 + 20],
               fill=(255, 255, 255, 25))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img.paste(glow, (0, 0), glow)

    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product(img, prod_img, left_cx, left_cy, left_size)
        draw = ImageDraw.Draw(img)
    else:
        x1 = left_cx - left_size // 2
        y1 = left_cy - left_size // 2
        rounded_rect(draw, (x1, y1, x1 + left_size, y1 + left_size), 20, fill=C['bg_mid'])
        font_ph = get_font(28, 'light')
        draw_centered(draw, "Img", left_cx, left_cy, font_ph, C['gray'])

    # Badge sconto top-left
    if data['discount_percent'] > 0:
        draw_discount_badge(img, 100, 250, data['discount_percent'], radius=78)
        draw = ImageDraw.Draw(img)

    # ===== COLONNA DESTRA =====
    right_x = 580
    right_w = 460

    # Tag "OFFERTA SU AMAZON"
    tag_y = 220
    font_tag = get_font(20, 'medium')
    tag_text = "OFFERTA SU AMAZON"
    tw, th = text_size(draw, tag_text, font_tag)
    pad = 14
    bh = 38
    bx1 = right_x
    bx2 = right_x + tw + pad * 2
    by1 = tag_y - bh // 2
    by2 = tag_y + bh // 2
    rounded_rect(draw, (bx1, by1, bx2, by2), bh // 2, outline=C['gold'], width=2)
    draw_left(draw, tag_text, bx1 + pad, tag_y - th // 2 + 2, font_tag, C['gold_bright'])

    # Nome prodotto
    name_y = tag_y + 50
    font_name = get_font(34, 'bold')
    lines = wrap_text(draw, data['title_short'], font_name, right_w, max_lines=4)
    lh = 44
    for i, line in enumerate(lines):
        draw_left(draw, line, right_x, name_y + i * lh, font_name, C['white'])
    name_bottom = name_y + len(lines) * lh

    # Linea decorativa
    div_y = name_bottom + 12
    draw.line([(right_x, div_y), (right_x + 60, div_y)], fill=C['gold'], width=3)

    # Etichette + Prezzi
    if data['discount_percent'] > 0:
        # Etichetta DA
        lbl_y = div_y + 30
        font_lbl = get_font(18, 'light')
        # Ottieni bbox per allineamento orizzontale corretto
        bbox_lbl = draw.textbbox((0, 0), "DA", font=font_lbl)
        draw.text((right_x - bbox_lbl[0], lbl_y - bbox_lbl[1]), "DA",
                  font=font_lbl, fill=C['gray'])

        # Prezzo originale barrato (a destra del "DA")
        font_orig = get_font(28, 'medium')
        orig_text = fmt_price(data['original_price'])
        bbox_o = draw.textbbox((0, 0), orig_text, font=font_orig)
        ow = bbox_o[2] - bbox_o[0]
        oh = bbox_o[3] - bbox_o[1]
        # Allineato sulla stessa baseline visiva del "DA"
        orig_x = right_x + 55
        orig_y_top = lbl_y - 8  # leggermente sopra per visuale
        draw.text((orig_x - bbox_o[0], orig_y_top - bbox_o[1]), orig_text,
                  font=font_orig, fill=C['gray'])
        # Barra - centrata verticalmente sul testo
        bar_y = orig_y_top + oh // 2 + 4
        draw.line([(orig_x - 4, bar_y), (orig_x + ow + 4, bar_y)],
                  fill=C['accent'], width=3)

        # Etichetta ORA SOLO
        ora_y = lbl_y + 50
        bbox_ora = draw.textbbox((0, 0), "ORA SOLO", font=font_lbl)
        draw.text((right_x - bbox_ora[0], ora_y - bbox_ora[1]), "ORA SOLO",
                  font=font_lbl, fill=C['gold'])

        # Prezzo grande
        big_y_center = ora_y + 55
        font_big = get_font(72, 'bold')
        big_text = fmt_price(data['current_price'])
        bbox_b = draw.textbbox((0, 0), big_text, font=font_big)
        bw = bbox_b[2] - bbox_b[0]
        # Glow + testo centrato verticalmente in big_y_center, allineato a sinistra a right_x
        draw_glow_text(img, big_text, right_x + bw // 2, big_y_center,
                       font_big, C['gold_bright'], C['gold'], glow_size=14)
        draw = ImageDraw.Draw(img)

        # Risparmi
        saving = data['original_price'] - data['current_price']
        font_sv = get_font(18, 'medium')
        rsp_y = big_y_center + 55
        bbox_rsp = draw.textbbox((0, 0), "Risparmi {}".format(fmt_price(saving)), font=font_sv)
        draw.text((right_x - bbox_rsp[0], rsp_y - bbox_rsp[1]),
                  "Risparmi {}".format(fmt_price(saving)), font=font_sv, fill=C['off_white'])
    else:
        # Solo prezzo
        big_y_center = div_y + 70
        font_big = get_font(72, 'bold')
        big_text = fmt_price(data['current_price'])
        bbox_b = draw.textbbox((0, 0), big_text, font=font_big)
        bw = bbox_b[2] - bbox_b[0]
        draw_glow_text(img, big_text, right_x + bw // 2, big_y_center,
                       font_big, C['gold_bright'], C['gold'], glow_size=14)
        draw = ImageDraw.Draw(img)

    # ===== FOOTER =====
    footer_y = 970
    # Linea sopra footer (con fade)
    draw.line([(120, footer_y - 10), (W - 120, footer_y - 10)], fill=C['gold'], width=1)

    font_cta = get_font(30, 'bold')
    draw_centered(draw, "LINK IN BIO", W // 2, footer_y + 15, font_cta, C['gold_bright'])
    font_handle = get_font(20, 'light')
    draw_centered(draw, "@sottocosto_oggi   ·   su Telegram",
                  W // 2, footer_y + 55, font_handle, C['gray'])

    # Watermark
    font_v = get_font(9, 'light')
    draw.text((W - 60, H - 14), CREATOR_VERSION, font=font_v, fill=(50, 55, 70))

    return img


# ============================================================
# CAPTION
# ============================================================

def generate_caption(data):
    saving = data['original_price'] - data['current_price']
    if data['discount_percent'] > 0:
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
            pct=data['discount_percent'], title=data['title_short'],
            orig=fmt_price(data['original_price']), sc=fmt_price(data['current_price']),
            sv=fmt_price(saving),
        )
    return (
        "🛒 PRODOTTO AMAZON\n\n"
        "{title}\n\n"
        "💰 {sc}\n\n"
        "⚡ Disponibile ora!\n\n"
        "Altre offerte ogni giorno: t.me/sottocosto_oggi\n\n"
        "#amazon #shopping #sottocostoOggi"
    ).format(title=data['title_short'], sc=fmt_price(data['current_price']))


def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


def handle_creator_command(api, url, partner_tag):
    print("[CREATOR] === {} ===".format(CREATOR_VERSION), flush=True)
    asin = extract_asin(url)
    if not asin:
        return None, None, None, ("❌ Link Amazon non valido.\n\n"
                                   "Formati:\n"
                                   "• https://www.amazon.it/dp/CODICE\n"
                                   "• https://amzn.to/CODICE")

    print("[CREATOR] ASIN: {}".format(asin), flush=True)
    data, err = get_product_data(api, asin, partner_tag)
    if err:
        return None, None, None, "❌ {}".format(err)

    if data.get('discount_percent', 0) == 0:
        if data.get('original_price', 0) <= data.get('current_price', 0):
            data['original_price'] = data['current_price']

    try:
        storia = generate_story(data)
        post = generate_post(data)
        caption = generate_caption(data)
        return image_to_bytes(storia), image_to_bytes(post), caption, None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None, None, "❌ Errore generazione: {}".format(str(e)[:100])
