"""
Modulo Creator per Sottocosto Oggi Bot v6 MINIMAL
Design pulito, sfondo bianco, allineamenti precisi.
"""

CREATOR_VERSION = "v6.0-MINIMAL"

import os
import re
import io
import math
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ====== PALETTE MINIMAL ======
C = {
    'bg': (252, 252, 250),          # bianco caldo (off-white)
    'bg_card': (255, 255, 255),     # bianco puro per card
    'ink': (20, 22, 28),            # nero soft (testo principale)
    'ink_soft': (90, 95, 110),      # grigio testo secondario
    'ink_light': (160, 165, 180),   # grigio leggero (etichette)
    'line': (230, 230, 235),        # divisori
    'accent': (220, 38, 49),        # rosso del brand (per highlight)
    'gold': (200, 145, 30),         # oro raffinato (non sgargiante)
    'green': (5, 150, 105),         # verde per risparmio
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


# ====== ESTRAZIONE DATI AMAZON ======

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
                return None, "Prodotto non disponibile (ASIN: {})".format(asin)
    except Exception as e:
        return None, "Errore API: {}".format(str(e)[:120])

    if not item:
        return None, "Prodotto non trovato"

    actual_asin = item.asin if hasattr(item, 'asin') else asin
    data = {'asin': actual_asin}

    try:
        data['title'] = item.item_info.title.display_value
    except (AttributeError, TypeError):
        return None, "Titolo non trovato"

    title = data['title']
    title = re.sub(r'\s+', ' ', title).strip()
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


# ====== RENDERING PRIMITIVES (PRECISI) ======

def text_dim(draw, text, font):
    """Ritorna (left, top, right, bottom, width, height, ascent_offset)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return {
        'left': bbox[0], 'top': bbox[1],
        'right': bbox[2], 'bottom': bbox[3],
        'w': bbox[2] - bbox[0],
        'h': bbox[3] - bbox[1],
    }


def draw_centered(draw, text, cx, cy, font, fill):
    """Centra in (cx, cy)."""
    d = text_dim(draw, text, font)
    x = cx - d['w'] // 2 - d['left']
    y = cy - d['h'] // 2 - d['top']
    draw.text((x, y), text, font=font, fill=fill)


def draw_left(draw, text, x, y, font, fill):
    """x = left edge, y = top edge del bbox visivo del testo."""
    d = text_dim(draw, text, font)
    draw.text((x - d['left'], y - d['top']), text, font=font, fill=fill)


def draw_right(draw, text, x, y, font, fill):
    """x = right edge."""
    d = text_dim(draw, text, font)
    draw.text((x - d['right'], y - d['top']), text, font=font, fill=fill)


def wrap_text(draw, text, font, max_w, max_lines=3):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        d = text_dim(draw, test, font)
        if d['w'] > max_w and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while text_dim(draw, last + '...', font)['w'] > max_w and len(last) > 3:
            last = last[:-1]
        lines[-1] = last + '...'
    return lines


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


def paste_product(img, prod, cx, cy, max_size):
    if not prod:
        return
    ratio = min(max_size / prod.width, max_size / prod.height)
    nw = int(prod.width * ratio)
    nh = int(prod.height * ratio)
    prod = prod.resize((nw, nh), Image.LANCZOS)
    img.paste(prod, (cx - nw // 2, cy - nh // 2),
              prod if prod.mode == 'RGBA' else None)


def add_subtle_shadow(img, x, y, w, h, blur=20, alpha=30):
    """Ombra sottile e morbida per dare profondita' al prodotto."""
    W, H = img.size
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    # Ellisse ombra sotto
    sd.ellipse([x, y, x + w, y + h], fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
    return Image.alpha_composite(img.convert('RGBA'), shadow).convert('RGB')


# ====== COMPONENTI BRAND ======

def draw_brand_logo(img, cx, cy, scale=1.0):
    """SOTTOCOSTO in nero + OGGI in box rosso, allineati perfettamente."""
    draw = ImageDraw.Draw(img)

    font_main = get_font(int(38 * scale))
    font_sub = get_font(int(16 * scale), 'bold')

    sotto = "SOTTOCOSTO"
    oggi = "OGGI"

    d_sotto = text_dim(draw, sotto, font_main)
    d_oggi = text_dim(draw, oggi, font_sub)

    pad_h = int(10 * scale)
    pad_v = int(5 * scale)
    box_w = d_oggi['w'] + pad_h * 2
    # Altezza del box = altezza del testo SOTTOCOSTO per allineamento perfetto
    box_h = max(d_oggi['h'] + pad_v * 2, int(d_sotto['h'] * 0.85))

    gap = int(10 * scale)
    total_w = d_sotto['w'] + gap + box_w
    start_x = cx - total_w // 2

    # SOTTOCOSTO (nero, allineato sulla baseline)
    sx = start_x - d_sotto['left']
    sy = cy - d_sotto['h'] // 2 - d_sotto['top']
    draw.text((sx, sy), sotto, font=font_main, fill=C['ink'])

    # Box OGGI - center allineato con il centro verticale di SOTTOCOSTO
    bx1 = start_x + d_sotto['w'] + gap
    bx2 = bx1 + box_w
    by1 = cy - box_h // 2
    by2 = cy + box_h // 2
    rounded_rect(draw, (bx1, by1, bx2, by2), int(4 * scale), fill=C['accent'])
    # OGGI centrato nel box
    draw_centered(draw, oggi, (bx1 + bx2) // 2, cy, font_sub, C['bg_card'])


def draw_dot_separator(draw, cx, y, color=None):
    """Piccolo punto centrato come divisore minimale."""
    if color is None:
        color = C['ink_light']
    draw.ellipse([cx - 3, y - 3, cx + 3, y + 3], fill=color)


def draw_tag_pill(draw, text, x, y, font, fill_color=None, text_color=None,
                  pad_h=14, pad_v=6, anchor='lt'):
    """Tag pillola minimal. anchor: 'lt'=left-top, 'mt'=center-top, 'mm'=center-middle."""
    if fill_color is None:
        fill_color = C['ink']
    if text_color is None:
        text_color = C['bg_card']
    d = text_dim(draw, text, font)
    w = d['w'] + pad_h * 2
    h = d['h'] + pad_v * 2

    if anchor[0] == 'm':
        bx1 = x - w // 2
    elif anchor[0] == 'r':
        bx1 = x - w
    else:
        bx1 = x

    if anchor[1] == 'm':
        by1 = y - h // 2
    elif anchor[1] == 'b':
        by1 = y - h
    else:
        by1 = y

    bx2 = bx1 + w
    by2 = by1 + h
    rounded_rect(draw, (bx1, by1, bx2, by2), h // 2, fill=fill_color)
    cx = (bx1 + bx2) // 2
    cy = (by1 + by2) // 2
    draw_centered(draw, text, cx, cy, font, text_color)
    return (bx1, by1, bx2, by2)


# ============================================================
# STORIA 1080x1920 MINIMAL
# ============================================================

def generate_story(data):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), C['bg'])
    draw = ImageDraw.Draw(img)

    # ===== HEADER LOGO =====
    draw_brand_logo(img, W // 2, 130, scale=1.4)
    draw = ImageDraw.Draw(img)

    # ===== TAG OFFERTA =====
    font_tag = get_font(22, 'medium')
    draw_tag_pill(draw, "OFFERTA SU AMAZON", W // 2, 230, font_tag,
                  fill_color=C['ink'], text_color=C['bg_card'],
                  pad_h=20, pad_v=8, anchor='mt')

    # ===== IMMAGINE PRODOTTO con ombra morbida =====
    img_cy = 760
    img_size = 680

    # Card bianca con leggero shadow
    card_x1 = W // 2 - img_size // 2 - 30
    card_y1 = img_cy - img_size // 2 - 30
    card_x2 = W // 2 + img_size // 2 + 30
    card_y2 = img_cy + img_size // 2 + 30

    # Ombra sotto la card
    img = add_subtle_shadow(img,
                            card_x1 + 30, card_y2 - 40,
                            card_x2 - card_x1 - 60, 80,
                            blur=30, alpha=40)
    draw = ImageDraw.Draw(img)

    # Card bianca arrotondata
    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), 24, fill=C['bg_card'])

    # Immagine prodotto
    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product(img, prod_img, W // 2, img_cy, img_size - 30)
        draw = ImageDraw.Draw(img)
    else:
        font_ph = get_font(28, 'light')
        draw_centered(draw, "[ Immagine ]", W // 2, img_cy, font_ph, C['ink_light'])

    # ===== BADGE SCONTO sovrapposto top-right =====
    if data['discount_percent'] > 0:
        badge_text = "-{}%".format(data['discount_percent'])
        font_badge = get_font(40, 'bold')
        bx = card_x2 - 50
        by = card_y1 + 50
        d = text_dim(draw, badge_text, font_badge)
        pad = 18
        bw = d['w'] + pad * 2
        bh = d['h'] + pad * 2

        # Ombra badge
        shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        rounded_rect(sd, (bx - bw // 2 + 3, by - bh // 2 + 5,
                          bx + bw // 2 + 3, by + bh // 2 + 5), bh // 2,
                     fill=(0, 0, 0, 60))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
        img.paste(shadow, (0, 0), shadow)

        draw = ImageDraw.Draw(img)
        rounded_rect(draw, (bx - bw // 2, by - bh // 2,
                            bx + bw // 2, by + bh // 2), bh // 2,
                     fill=C['accent'])
        draw_centered(draw, badge_text, bx, by, font_badge, C['bg_card'])

    # ===== NOME PRODOTTO =====
    name_y = 1240
    font_name = get_font(46, 'bold')
    lines = wrap_text(draw, data['title_short'], font_name, 940, max_lines=3)
    lh = 58
    for i, line in enumerate(lines):
        draw_centered(draw, line, W // 2, name_y + i * lh + lh // 2,
                      font_name, C['ink'])

    name_bottom = name_y + len(lines) * lh

    # ===== LINEA DIVISORIA =====
    sep_y = name_bottom + 50
    draw.line([(W // 2 - 60, sep_y), (W // 2 + 60, sep_y)], fill=C['ink'], width=2)

    # ===== PREZZI - LAYOUT VERTICALE MINIMAL =====
    price_block_y = sep_y + 70

    if data['discount_percent'] > 0:
        # Prezzo originale piccolo barrato
        font_orig = get_font(36, 'regular')
        orig_text = fmt_price(data['original_price'])
        d_orig = text_dim(draw, orig_text, font_orig)
        draw_centered(draw, orig_text, W // 2, price_block_y, font_orig, C['ink_light'])
        # Linea barrata
        bar_y = price_block_y + 2
        draw.line([(W // 2 - d_orig['w'] // 2 - 8, bar_y),
                   (W // 2 + d_orig['w'] // 2 + 8, bar_y)],
                  fill=C['accent'], width=3)

        # Prezzo grande
        big_y = price_block_y + 90
    else:
        big_y = price_block_y + 30

    font_big = get_font(130, 'bold')
    big_text = fmt_price(data['current_price'])
    draw_centered(draw, big_text, W // 2, big_y, font_big, C['ink'])

    # ===== RISPARMI (badge verde minimal) =====
    if data['discount_percent'] > 0:
        saving = data['original_price'] - data['current_price']
        rsp_text = "Risparmi {}".format(fmt_price(saving))
        font_rsp = get_font(24, 'medium')
        draw_tag_pill(draw, rsp_text, W // 2, big_y + 100, font_rsp,
                      fill_color=C['green'], text_color=C['bg_card'],
                      pad_h=18, pad_v=8, anchor='mt')

    # ===== FOOTER MINIMAL =====
    footer_y = 1830
    font_handle = get_font(26, 'medium')
    draw_centered(draw, "@sottocosto_oggi", W // 2, footer_y, font_handle, C['ink'])
    font_sub = get_font(16, 'light')
    draw_centered(draw, "su Telegram", W // 2, footer_y + 32, font_sub, C['ink_soft'])

    # Watermark versione
    font_v = get_font(8, 'light')
    draw.text((W - 70, H - 14), CREATOR_VERSION, font=font_v, fill=(220, 220, 225))

    return img


# ============================================================
# POST 1080x1080 MINIMAL
# ============================================================

def generate_post(data):
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), C['bg'])
    draw = ImageDraw.Draw(img)

    # ===== HEADER LOGO compatto =====
    draw_brand_logo(img, W // 2, 75, scale=0.85)
    draw = ImageDraw.Draw(img)

    # Linea sottilissima sotto header
    draw.line([(W // 2 - 60, 120), (W // 2 + 60, 120)], fill=C['line'], width=1)

    # ===== LAYOUT 2 COLONNE =====
    left_cx = 290
    left_cy = 540
    left_size = 480

    # Card bianca per immagine
    card_x1 = left_cx - left_size // 2 - 20
    card_y1 = left_cy - left_size // 2 - 20
    card_x2 = left_cx + left_size // 2 + 20
    card_y2 = left_cy + left_size // 2 + 20

    img = add_subtle_shadow(img,
                            card_x1 + 30, card_y2 - 30,
                            card_x2 - card_x1 - 60, 60,
                            blur=20, alpha=35)
    draw = ImageDraw.Draw(img)

    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), 20, fill=C['bg_card'])

    prod_img = download_image(data.get('image_url'))
    if prod_img:
        paste_product(img, prod_img, left_cx, left_cy, left_size - 20)
        draw = ImageDraw.Draw(img)
    else:
        font_ph = get_font(24, 'light')
        draw_centered(draw, "Img", left_cx, left_cy, font_ph, C['ink_light'])

    # Badge sconto sovrapposto top-left della card
    if data['discount_percent'] > 0:
        badge_text = "-{}%".format(data['discount_percent'])
        font_badge = get_font(32, 'bold')
        bx = card_x1 + 30
        by = card_y1 + 30
        d = text_dim(draw, badge_text, font_badge)
        pad = 14
        bw = d['w'] + pad * 2
        bh = d['h'] + pad * 2

        # Ombra
        shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        rounded_rect(sd, (bx + 2, by + 4, bx + bw + 2, by + bh + 4), bh // 2,
                     fill=(0, 0, 0, 60))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))
        img.paste(shadow, (0, 0), shadow)

        draw = ImageDraw.Draw(img)
        rounded_rect(draw, (bx, by, bx + bw, by + bh), bh // 2, fill=C['accent'])
        draw_centered(draw, badge_text, bx + bw // 2, by + bh // 2,
                      font_badge, C['bg_card'])

    # ===== COLONNA DESTRA =====
    right_x = 600

    # Tag OFFERTA SU AMAZON
    tag_y = 210
    font_tag = get_font(18, 'medium')
    draw_tag_pill(draw, "OFFERTA SU AMAZON", right_x, tag_y, font_tag,
                  fill_color=C['ink'], text_color=C['bg_card'],
                  pad_h=14, pad_v=7, anchor='lt')

    # Nome prodotto
    name_y = tag_y + 70
    font_name = get_font(34, 'bold')
    lines = wrap_text(draw, data['title_short'], font_name, 440, max_lines=3)
    lh = 44
    for i, line in enumerate(lines):
        draw_left(draw, line, right_x, name_y + i * lh, font_name, C['ink'])
    name_bottom = name_y + len(lines) * lh

    # Linea sottile
    div_y = name_bottom + 25
    draw.line([(right_x, div_y), (right_x + 50, div_y)], fill=C['ink'], width=2)

    # ===== PREZZI =====
    price_y = div_y + 35

    if data['discount_percent'] > 0:
        # Prezzo originale piccolo barrato (sopra)
        font_orig = get_font(26, 'regular')
        orig_text = fmt_price(data['original_price'])
        d_orig = text_dim(draw, orig_text, font_orig)
        draw_left(draw, orig_text, right_x, price_y, font_orig, C['ink_light'])
        # Linea barrata
        bar_y = price_y + d_orig['h'] // 2 + 4
        draw.line([(right_x - 4, bar_y),
                   (right_x + d_orig['w'] + 4, bar_y)],
                  fill=C['accent'], width=2)

        # Prezzo grande
        big_y = price_y + 50
    else:
        big_y = price_y

    font_big = get_font(76, 'bold')
    big_text = fmt_price(data['current_price'])
    draw_left(draw, big_text, right_x, big_y, font_big, C['ink'])
    d_big = text_dim(draw, big_text, font_big)
    big_bottom = big_y + d_big['h']

    # Risparmi (badge verde)
    if data['discount_percent'] > 0:
        saving = data['original_price'] - data['current_price']
        rsp_text = "Risparmi {}".format(fmt_price(saving))
        font_rsp = get_font(18, 'medium')
        draw_tag_pill(draw, rsp_text, right_x, big_bottom + 25, font_rsp,
                      fill_color=C['green'], text_color=C['bg_card'],
                      pad_h=14, pad_v=6, anchor='lt')

    # ===== FOOTER =====
    footer_y = 980
    # Linea sopra footer
    draw.line([(80, footer_y), (W - 80, footer_y)], fill=C['line'], width=1)

    font_cta = get_font(24, 'bold')
    draw_centered(draw, "LINK IN BIO", W // 2, footer_y + 35, font_cta, C['ink'])
    font_handle = get_font(18, 'light')
    draw_centered(draw, "@sottocosto_oggi   ·   su Telegram",
                  W // 2, footer_y + 70, font_handle, C['ink_soft'])

    # Watermark
    font_v = get_font(8, 'light')
    draw.text((W - 70, H - 14), CREATOR_VERSION, font=font_v, fill=(220, 220, 225))

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
