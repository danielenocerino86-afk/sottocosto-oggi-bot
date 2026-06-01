"""
Modulo Creator per Sottocosto Oggi Bot v4.1 PREMIUM
Design professionale - VERSIONE: 2026-06-01-PREMIUM
"""

# Tag versione visibile nei log e nelle immagini
CREATOR_VERSION = "v4.1-PREMIUM"

import os
import re
import io
import math
import random
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Palette colori brand
COLORS = {
    'bg_dark': (8, 14, 35),         # blu notte profondo
    'bg_mid': (18, 28, 60),         # blu medio
    'bg_light': (28, 42, 80),       # blu schiarito
    'accent': (255, 71, 87),        # rosso vivo (piu' moderno)
    'accent_dark': (200, 35, 50),
    'gold': (255, 200, 60),         # oro caldo
    'gold_bright': (255, 220, 100),
    'white': (255, 255, 255),
    'off_white': (240, 240, 245),
    'gray': (140, 145, 160),
    'gray_dark': (80, 85, 100),
}

FONT_PATHS = {
    'bold': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ],
    'medium': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf',
        '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ],
    'regular': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ],
    'light': [
        '/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf',
        '/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ],
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
    """Formatta prezzo italiano con virgola. Es: 168.75 -> '168,75 €'."""
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
    # Tronca al primo separatore se il titolo e' troppo lungo
    cut = title.find(', ')
    if 30 < cut < 90:
        title = title[:cut]
    if len(title) > 70:
        title = title[:70] + '...'
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
            if hasattr(listing, 'saving_basis') and listing.saving_basis:
                data['original_price'] = listing.saving_basis.amount
                if data['original_price'] > data['current_price']:
                    data['discount_percent'] = round(
                        ((data['original_price'] - data['current_price']) / data['original_price']) * 100
                    )
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


# ============================================================
# HELPERS DESIGN
# ============================================================

def get_text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_text(draw, text, x, y, font, fill, anchor='lt'):
    """Disegna testo con anchor:
    - 'lt' = left-top (default)
    - 'mt' = middle-top (centrato orizzontalmente)
    - 'mm' = middle-middle (centrato H+V)
    - 'rt' = right-top (allineato a destra)
    """
    w, h = get_text_size(draw, text, font)
    bbox = draw.textbbox((0, 0), text, font=font)
    offset_y = bbox[1]  # offset per allineamento corretto del top

    if anchor[0] == 'm':
        x -= w // 2
    elif anchor[0] == 'r':
        x -= w
    if anchor[1] == 'm':
        y -= (h // 2) + offset_y // 2

    draw.text((x, y), text, font=font, fill=fill)


def wrap_lines(draw, text, font, max_width, max_lines=3):
    """Spezza testo in righe e ritorna la lista delle righe."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        w, _ = get_text_size(draw, test, font)
        if w > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        # Aggiungi ... all'ultima riga
        last = lines[-1]
        while True:
            w, _ = get_text_size(draw, last + '...', font)
            if w <= max_width or len(last) <= 3:
                break
            last = last[:-1]
        lines[-1] = last + '...'
    return lines


def draw_radial_bg(img, cx, cy, max_r):
    """Sfondo radiale dal centro (chiaro) all'esterno (scuro)."""
    draw = ImageDraw.Draw(img)
    for r in range(max_r, 0, -6):
        t = r / max_r
        # Interpolazione: bg_light al centro, bg_dark fuori
        color = tuple(
            int(COLORS['bg_light'][i] * (1 - t) + COLORS['bg_dark'][i] * t)
            for i in range(3)
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def draw_soft_rays(img, cx, cy, num=20, alpha=14):
    """Raggi morbidi dal centro - molto sottili e diffusi."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_dist = max(img.size) * 1.5
    for i in range(num):
        if i % 2 == 1:
            continue
        angle = (math.pi * 2 / num) * i
        half_ang = math.pi / num / 3
        x1 = cx + math.cos(angle - half_ang) * max_dist
        y1 = cy + math.sin(angle - half_ang) * max_dist
        x2 = cx + math.cos(angle + half_ang) * max_dist
        y2 = cy + math.sin(angle + half_ang) * max_dist
        draw.polygon([(cx, cy), (x1, y1), (x2, y2)],
                     fill=(COLORS['gold'][0], COLORS['gold'][1], COLORS['gold'][2], alpha))
    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


def add_noise_texture(img, alpha=8):
    """Aggiunge granulosita' premium subliminale."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(800):
        x = random.randint(0, img.width)
        y = random.randint(0, img.height)
        size = random.choice([1, 1, 1, 2])
        color = random.choice([
            (255, 255, 255, alpha),
            (COLORS['gold'][0], COLORS['gold'][1], COLORS['gold'][2], alpha + 5),
        ])
        draw.point((x, y), fill=color)
        if size == 2:
            draw.point((x + 1, y), fill=color)
    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


def add_corner_glow(img, position='top-left', color=None, intensity=120, size_pct=0.5):
    """Glow morbido in un angolo per profondita'."""
    if color is None:
        color = COLORS['accent']
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    positions = {
        'top-left': (0, 0),
        'top-right': (img.width, 0),
        'bottom-left': (0, img.height),
        'bottom-right': (img.width, img.height),
        'center': (img.width // 2, img.height // 2),
    }
    cx, cy = positions.get(position, (0, 0))
    radius = int(max(img.size) * size_pct)

    for r in range(radius, 0, -10):
        t = r / radius
        alpha = int(intensity * (1 - t) ** 2)
        if alpha < 1:
            continue
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(color[0], color[1], color[2], alpha))

    # Blur per renderlo morbido
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=60))
    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


def draw_glow_text(img, text, x, y, font, fill, glow_color, glow_size=15, anchor='lt'):
    """Disegna testo con glow morbido sotto."""
    # Layer glow
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    w, h = get_text_size(gd, text, font)
    bbox = gd.textbbox((0, 0), text, font=font)
    offset_y = bbox[1]

    gx, gy = x, y
    if anchor[0] == 'm':
        gx -= w // 2
    elif anchor[0] == 'r':
        gx -= w
    if anchor[1] == 'm':
        gy -= (h // 2) + offset_y // 2

    # Disegna testo glow esteso
    glow_alpha = 180
    gd.text((gx, gy), text, font=font,
            fill=(glow_color[0], glow_color[1], glow_color[2], glow_alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_size))
    img.paste(glow, (0, 0), glow)

    # Testo principale
    draw = ImageDraw.Draw(img)
    draw.text((gx, gy), text, font=font, fill=fill)


def paste_product_image(img, prod_img, cx, cy, max_size):
    """Centra immagine prodotto. Senza cornice."""
    if not prod_img:
        return
    ratio = min(max_size / prod_img.width, max_size / prod_img.height)
    new_w = int(prod_img.width * ratio)
    new_h = int(prod_img.height * ratio)
    prod_img = prod_img.resize((new_w, new_h), Image.LANCZOS)
    img.paste(prod_img, (cx - new_w // 2, cy - new_h // 2),
              prod_img if prod_img.mode == 'RGBA' else None)


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """Rettangolo arrotondato."""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.pieslice([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=fill)
    draw.pieslice([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=fill)
    if outline:
        # Disegna bordo arrotondato
        draw.arc([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=outline, width=width)
        draw.arc([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=outline, width=width)
        draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=width)
        draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=width)
        draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=width)
        draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=width)


def draw_horizontal_line_gradient(draw, x1, x2, y, color, width=2):
    """Linea orizzontale con fade ai bordi."""
    length = x2 - x1
    for i in range(length):
        t = i / length
        # Fade-in e fade-out ai bordi
        if t < 0.15:
            alpha = int(255 * (t / 0.15))
        elif t > 0.85:
            alpha = int(255 * ((1 - t) / 0.15))
        else:
            alpha = 255
        if alpha > 0:
            for w in range(width):
                draw.point((x1 + i, y + w), fill=(color[0], color[1], color[2]))


# ============================================================
# LOGO BRAND
# ============================================================

def draw_brand_logo(img, x, y, scale=1.0, with_separator=True):
    """Logo SOTTOCOSTO con OGGI in box rosso (richiamo al logo originale)."""
    draw = ImageDraw.Draw(img)
    # SOTTOCOSTO grande in oro
    font_main = get_font(int(48 * scale))
    draw_glow_text(img, "SOTTOCOSTO", x, y, font_main, COLORS['gold_bright'],
                   COLORS['gold'], glow_size=8, anchor='mt')

    # OGGI in box rosso piccolo, sotto
    draw = ImageDraw.Draw(img)
    font_sub = get_font(int(22 * scale))
    oggi_text = "OGGI"
    w_oggi, h_oggi = get_text_size(draw, oggi_text, font_sub)
    pad_h = int(14 * scale)
    pad_v = int(6 * scale)
    box_w = w_oggi + pad_h * 2
    box_h = h_oggi + pad_v * 2
    box_x1 = x - box_w // 2
    box_y1 = y + int(58 * scale)
    box_x2 = box_x1 + box_w
    box_y2 = box_y1 + box_h
    draw_rounded_rect(draw, (box_x1, box_y1, box_x2, box_y2), int(4 * scale),
                      fill=COLORS['accent'])
    draw_text(draw, oggi_text, x, box_y1 + pad_v + 2, font_sub, COLORS['white'], anchor='mt')

    if with_separator:
        # Linea decorativa sotto
        sep_y = box_y2 + int(20 * scale)
        sep_len = int(160 * scale)
        # Linea con punto centrale oro
        draw.line([(x - sep_len // 2, sep_y), (x - 8, sep_y)],
                  fill=COLORS['gold'], width=2)
        draw.line([(x + 8, sep_y), (x + sep_len // 2, sep_y)],
                  fill=COLORS['gold'], width=2)
        # Diamantino centrale
        draw.polygon([(x, sep_y - 5), (x + 5, sep_y), (x, sep_y + 5), (x - 5, sep_y)],
                     fill=COLORS['gold_bright'])


# ============================================================
# DISCOUNT BADGE
# ============================================================

def draw_discount_badge(img, x, y, percent, size=140):
    """Badge sconto circolare premium con doppio bordo."""
    if percent <= 0:
        return
    draw = ImageDraw.Draw(img)
    # Glow esterno
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([x - size - 20, y - size - 20, x + size + 20, y + size + 20],
               fill=(COLORS['accent'][0], COLORS['accent'][1], COLORS['accent'][2], 80))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=20))
    img.paste(glow, (0, 0), glow)

    draw = ImageDraw.Draw(img)
    # Cerchio esterno oro (anello)
    draw.ellipse([x - size, y - size, x + size, y + size], fill=COLORS['gold'])
    # Cerchio interno rosso
    inner = size - 10
    draw.ellipse([x - inner, y - inner, x + inner, y + inner], fill=COLORS['accent'])
    # Anello interno sottile oro
    inner2 = inner - 8
    draw.ellipse([x - inner2, y - inner2, x + inner2, y + inner2],
                 outline=COLORS['gold_bright'], width=2)

    # Testo
    font_pct_big = get_font(int(size * 0.55))
    font_pct_sm = get_font(int(size * 0.25))
    text_big = "-{}%".format(percent)
    draw_text(draw, text_big, x, y, font_pct_big, COLORS['white'], anchor='mm')


# ============================================================
# STORIA INSTAGRAM 1080x1920
# ============================================================

def generate_story(data):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), COLORS['bg_dark'])

    # Sfondo radiale + raggi morbidi + rumore
    draw_radial_bg(img, W // 2, H // 2, 1400)
    img = draw_soft_rays(img, W // 2, H // 2, num=20, alpha=12)
    img = add_corner_glow(img, 'top-left', COLORS['accent'], intensity=80, size_pct=0.6)
    img = add_corner_glow(img, 'bottom-right', COLORS['gold'], intensity=70, size_pct=0.5)
    img = add_noise_texture(img, alpha=6)

    draw = ImageDraw.Draw(img)

    # ============ HEADER: LOGO BRAND ============
    draw_brand_logo(img, W // 2, 100, scale=1.3, with_separator=True)
    draw = ImageDraw.Draw(img)

    # ============ TAG "OFFERTA EXCLUSIVE" ============
    # piccola etichetta minimal sopra il prodotto
    tag_text = "OFFERTA SU AMAZON"
    font_tag = get_font(28, 'medium')
    tw, th = get_text_size(draw, tag_text, font_tag)
    # Box arrotondato sottile
    tag_x = W // 2
    tag_y = 310
    pad = 22
    box_h = 50
    draw_rounded_rect(draw, (tag_x - (tw // 2 + pad), tag_y - box_h // 2,
                              tag_x + (tw // 2 + pad), tag_y + box_h // 2),
                      box_h // 2, fill=None, outline=COLORS['gold'], width=2)
    draw_text(draw, tag_text, tag_x, tag_y, font_tag, COLORS['gold_bright'], anchor='mm')

    # ============ IMMAGINE PRODOTTO - NO CORNICE, IL PRODOTTO E' L'EROE ============
    prod_img = download_image(data.get('image_url'))
    if prod_img:
        # Glow morbido dietro l'immagine prodotto
        glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([200, 450, 880, 1130], fill=(255, 255, 255, 30))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=80))
        img.paste(glow, (0, 0), glow)
        # Immagine
        paste_product_image(img, prod_img, W // 2, 790, 740)
        draw = ImageDraw.Draw(img)
    else:
        # Placeholder elegante
        draw_rounded_rect(draw, (200, 450, 880, 1130), 30,
                          fill=COLORS['bg_mid'], outline=COLORS['gold'], width=3)
        font_ph = get_font(36, 'light')
        draw_text(draw, "IMMAGINE", W // 2, 790, font_ph, COLORS['gray'], anchor='mm')

    # ============ BADGE SCONTO sovrapposto in alto a destra dell'immagine ============
    if data['discount_percent'] > 0:
        draw_discount_badge(img, 870, 530, data['discount_percent'], size=110)
        draw = ImageDraw.Draw(img)

    # ============ NOME PRODOTTO ============
    font_name = get_font(48, 'bold')
    lines = wrap_lines(draw, data['title_short'], font_name, 940, max_lines=3)
    name_y = 1230
    for line in lines:
        draw_text(draw, line, W // 2, name_y, font_name, COLORS['white'], anchor='mt')
        name_y += 60

    # ============ DIVISORE ELEGANTE ============
    sep_y = name_y + 30
    draw.line([(380, sep_y), (700, sep_y)], fill=COLORS['gold'], width=2)
    draw.polygon([(W // 2, sep_y - 6), (W // 2 + 6, sep_y), (W // 2, sep_y + 6), (W // 2 - 6, sep_y)],
                 fill=COLORS['gold_bright'])

    # ============ PREZZI PREMIUM ============
    # Layout verticale per la storia (piu' impatto)
    # Riga 1: prezzo originale piccolo barrato
    # Riga 2: prezzo grande in oro

    if data['discount_percent'] > 0:
        # Da
        font_da = get_font(28, 'light')
        draw_text(draw, "DA", W // 2 - 130, sep_y + 50, font_da, COLORS['gray'], anchor='mt')
        # Prezzo originale
        font_orig = get_font(50, 'medium')
        orig_text = fmt_price(data['original_price'])
        orig_w, _ = get_text_size(draw, orig_text, font_orig)
        ox = W // 2 - 60
        oy = sep_y + 40
        draw_text(draw, orig_text, ox, oy, font_orig, COLORS['gray'], anchor='lt')
        # Linea barrata
        line_y = oy + 35
        draw.line([(ox - 8, line_y), (ox + orig_w + 8, line_y)],
                  fill=COLORS['accent'], width=4)

        # A
        a_y = sep_y + 130
        font_a = get_font(28, 'light')
        draw_text(draw, "ORA SOLO", W // 2, a_y, font_a, COLORS['gold'], anchor='mt')

    # Prezzo principale - GIGANTE in oro con glow
    main_y = sep_y + 195
    font_main = get_font(160, 'bold')
    main_text = fmt_price(data['current_price'])
    draw_glow_text(img, main_text, W // 2, main_y, font_main,
                   COLORS['gold_bright'], COLORS['gold'], glow_size=25, anchor='mt')
    draw = ImageDraw.Draw(img)

    # ============ FOOTER MINIMAL ============
    # solo "@sottocosto_oggi" piccolissimo, lo spazio sotto resta vuoto per il link IG
    footer_y = 1830
    font_handle = get_font(26, 'medium')
    draw_text(draw, "@sottocosto_oggi", W // 2, footer_y, font_handle, COLORS['gold'], anchor='mt')
    font_footer_sm = get_font(18, 'light')
    draw_text(draw, "scopri tutte le offerte su Telegram", W // 2, footer_y + 38,
              font_footer_sm, COLORS['gray'], anchor='mt')

    # Watermark versione (per verifica deploy)
    font_v = get_font(10, 'light')
    draw_text(draw, CREATOR_VERSION, W - 20, H - 20, font_v, (60, 60, 80), anchor='rt')

    return img


# ============================================================
# POST QUADRATO 1080x1080
# ============================================================

def generate_post(data):
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), COLORS['bg_dark'])

    draw_radial_bg(img, W // 2, H // 2, 900)
    img = draw_soft_rays(img, W // 2, H // 2, num=16, alpha=10)
    img = add_corner_glow(img, 'top-left', COLORS['accent'], intensity=70, size_pct=0.4)
    img = add_corner_glow(img, 'bottom-right', COLORS['gold'], intensity=60, size_pct=0.4)
    img = add_noise_texture(img, alpha=5)

    draw = ImageDraw.Draw(img)

    # ============ HEADER BRAND minimal in alto ============
    # tutto su una riga: SOTTOCOSTO [OGGI rosso] · @sottocosto_oggi
    header_y = 50
    font_brand = get_font(34, 'bold')
    draw_text(draw, "SOTTOCOSTO", W // 2 - 80, header_y, font_brand, COLORS['gold_bright'], anchor='rt')

    # OGGI in box rosso
    font_oggi = get_font(22, 'bold')
    oggi_text = "OGGI"
    w_oggi, _ = get_text_size(draw, oggi_text, font_oggi)
    pad_h = 12
    box_x1 = W // 2 - 70
    box_y1 = header_y - 2
    box_x2 = box_x1 + w_oggi + pad_h * 2
    box_y2 = box_y1 + 38
    draw_rounded_rect(draw, (box_x1, box_y1, box_x2, box_y2), 4, fill=COLORS['accent'])
    draw_text(draw, oggi_text, box_x1 + pad_h, box_y1 + 8, font_oggi, COLORS['white'])

    # Linea decorativa sotto
    draw.line([(180, 130), (520, 130)], fill=COLORS['gold'], width=1)
    draw.polygon([(W // 2, 124), (W // 2 + 5, 130), (W // 2, 136), (W // 2 - 5, 130)],
                 fill=COLORS['gold_bright'])
    draw.line([(560, 130), (900, 130)], fill=COLORS['gold'], width=1)

    # ============ LAYOUT 2 COLONNE ============
    # Sinistra: immagine prodotto su sfondo morbido
    # Destra: testo + prezzi

    # GLOW dietro al prodotto (sostituisce la cornice)
    prod_img = download_image(data.get('image_url'))
    if prod_img:
        glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([20, 200, 560, 880], fill=(255, 255, 255, 25))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
        img.paste(glow, (0, 0), glow)
        paste_product_image(img, prod_img, 290, 540, 530)
        draw = ImageDraw.Draw(img)
    else:
        draw_rounded_rect(draw, (50, 220, 540, 860), 20,
                          fill=COLORS['bg_mid'], outline=COLORS['gold'], width=2)
        font_ph = get_font(28, 'light')
        draw_text(draw, "IMG", 290, 540, font_ph, COLORS['gray'], anchor='mm')

    # Badge sconto sovrapposto
    if data['discount_percent'] > 0:
        draw_discount_badge(img, 100, 250, data['discount_percent'], size=80)
        draw = ImageDraw.Draw(img)

    # ============ PANNELLO DESTRO ============
    right_x = 600
    right_w = 440

    # Tag minimal
    tag_y = 200
    font_tag = get_font(20, 'medium')
    draw_text(draw, "OFFERTA SU AMAZON", right_x, tag_y, font_tag, COLORS['gold'])

    # Nome prodotto - tipografia grande
    font_name = get_font(36, 'bold')
    lines = wrap_lines(draw, data['title_short'], font_name, right_w, max_lines=4)
    ny = tag_y + 40
    for line in lines:
        draw_text(draw, line, right_x, ny, font_name, COLORS['white'])
        ny += 46

    # Divisore
    div_y = ny + 15
    draw.line([(right_x, div_y), (right_x + 60, div_y)], fill=COLORS['gold'], width=3)

    # PREZZI
    price_y = div_y + 35
    if data['discount_percent'] > 0:
        # "Da" piccolo
        font_label = get_font(18, 'light')
        draw_text(draw, "DA", right_x, price_y, font_label, COLORS['gray'])

        # Prezzo originale piccolo barrato
        font_orig = get_font(32, 'medium')
        orig_text = fmt_price(data['original_price'])
        orig_w, _ = get_text_size(draw, orig_text, font_orig)
        ox = right_x + 50
        draw_text(draw, orig_text, ox, price_y - 5, font_orig, COLORS['gray'])
        # Barra
        draw.line([(ox - 5, price_y + 15), (ox + orig_w + 5, price_y + 15)],
                  fill=COLORS['accent'], width=3)

        # "Ora solo"
        font_now = get_font(18, 'light')
        draw_text(draw, "ORA SOLO", right_x, price_y + 50, font_now, COLORS['gold'])

    # Prezzo grande
    sc_y = price_y + 80 if data['discount_percent'] > 0 else price_y
    font_main = get_font(78, 'bold')
    sc_text = fmt_price(data['current_price'])
    draw_glow_text(img, sc_text, right_x, sc_y, font_main,
                   COLORS['gold_bright'], COLORS['gold'], glow_size=15)
    draw = ImageDraw.Draw(img)

    # Risparmi piccolo
    if data['discount_percent'] > 0:
        saving = data['original_price'] - data['current_price']
        font_sv = get_font(20, 'medium')
        draw_text(draw, "Risparmi {}".format(fmt_price(saving).strip()),
                  right_x, sc_y + 95, font_sv, COLORS['off_white'])

    # ============ FOOTER ============
    # Bottom area con CTA minimal
    footer_y = 960
    # Linea sopra
    draw_horizontal_line_gradient(draw, 80, W - 80, footer_y - 10, COLORS['gold'], width=1)

    # Bottone CTA minimalista
    cta_text = "LINK IN BIO"
    font_cta = get_font(32, 'bold')
    draw_text(draw, cta_text, W // 2, footer_y + 5, font_cta, COLORS['gold_bright'], anchor='mt')

    # Handle Telegram
    font_handle = get_font(22, 'light')
    draw_text(draw, "@sottocosto_oggi  ·  su Telegram", W // 2, footer_y + 50,
              font_handle, COLORS['gray'], anchor='mt')

    # Watermark versione (in piccolo, in basso a destra) per verifica deploy
    font_v = get_font(10, 'light')
    draw_text(draw, CREATOR_VERSION, W - 20, H - 20, font_v, (60, 60, 80), anchor='rt')

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
            pct=data['discount_percent'],
            title=data['title_short'],
            orig=fmt_price(data['original_price']),
            sc=fmt_price(data['current_price']),
            sv=fmt_price(saving),
        )
    else:
        return (
            "🛒 NUOVO PRODOTTO AMAZON\n\n"
            "{title}\n\n"
            "💰 Solo {sc}\n\n"
            "⚡ Disponibile su Amazon!\n\n"
            "Altre offerte ogni giorno sul mio canale Telegram:\n"
            "👉 t.me/sottocosto_oggi\n\n"
            "#amazon #shopping #sottocostoOggi #italia"
        ).format(
            title=data['title_short'],
            sc=fmt_price(data['current_price']),
        )


def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


def handle_creator_command(api, url, partner_tag):
    print("[CREATOR] === {} ===".format(CREATOR_VERSION), flush=True)

    asin = extract_asin(url)
    if not asin:
        return None, None, None, ("❌ Link Amazon non valido o non risolvibile.\n\n"
                                   "Formati supportati:\n"
                                   "• https://www.amazon.it/dp/CODICE\n"
                                   "• https://amzn.to/CODICE\n"
                                   "• https://amzn.eu/d/CODICE")

    print("[CREATOR] ASIN estratto: {}".format(asin), flush=True)

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
        return None, None, None, "❌ Errore generazione: {}".format(str(e)[:100])
