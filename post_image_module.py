"""Modulo che genera immagini quadrate 1080x1080 per i post Telegram delle offerte WOW.
Da integrare nel bot.py - stile v6.0 minimal coerente con storia/post IG.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import requests

# Colori v6.0 MINIMAL (stessi del Creator)
BG_WHITE = "#FCFCFA"
TEXT_BLACK = "#14161C"
ACCENT_RED = "#DC2631"
GOLD = "#C8911E"
GREEN = "#059669"
SUBTLE_GREY = "#6B7280"
LIGHT_GREY = "#E5E7EB"
CARD_BG = "#FFFFFF"

# Path font (DejaVu disponibile sia in container Claude che in GitHub Actions Ubuntu)
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _shrink_to_fit(text, max_width, font_path, max_size, min_size=24):
    """Trova font size che fa stare il testo nella larghezza data."""
    for size in range(max_size, min_size - 1, -2):
        f = ImageFont.truetype(font_path, size)
        b = f.getbbox(text)
        w = b[2] - b[0]
        if w <= max_width:
            return f
    return ImageFont.truetype(font_path, min_size)


def _wrap_text(text, font, max_width, draw):
    """Spezza il testo su piu' righe rispettando max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + " " + word if current else word
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _download_image(url, timeout=8):
    """Scarica immagine prodotto Amazon."""
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print("  [IMG_ERR]", e)
        return None


def _draw_logo(draw, x=40, y=40, scale=1.0):
    """Mini logo SOTTOCOSTO OGGI in alto."""
    font_logo = ImageFont.truetype(FONT_BOLD, int(38 * scale))
    text1 = "SOTTOCOSTO"
    draw.text((x, y), text1, font=font_logo, fill=TEXT_BLACK)
    bbox1 = draw.textbbox((0, 0), text1, font=font_logo)
    text1_w = bbox1[2] - bbox1[0]

    text2 = "OGGI"
    box_left = x + text1_w + 12
    bbox2 = font_logo.getbbox(text2)
    t2w = bbox2[2] - bbox2[0]
    t2h = bbox2[3] - bbox2[1]
    box_right = box_left + t2w + 24
    box_top = y + 4
    box_bottom = y + t2h + 16
    draw.rounded_rectangle([box_left, box_top, box_right, box_bottom],
                           radius=int(8 * scale), fill=ACCENT_RED)
    draw.text((box_left + 12, y), text2, font=font_logo, fill="#FFFFFF")


def generate_post_image(deal, output_path):
    """Genera immagine post 1080x1080 per offerta WOW.

    Args:
        deal: dict con keys: title, current_price, original_price, discount_percent,
              discount, image_url, rating, review_count, has_deal
        output_path: dove salvare il PNG generato

    Returns:
        True se generata con successo, False altrimenti.
    """
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), BG_WHITE)
    draw = ImageDraw.Draw(img)

    # === BIG % DECORATION (sfondo morbido top-right) ===
    deco_font = ImageFont.truetype(FONT_BOLD, 420)
    draw.text((W - 360, -80), "%", font=deco_font, fill="#F3EFE9")

    # === LOGO TOP ===
    _draw_logo(draw, x=40, y=40, scale=1.4)

    # === BADGE SCONTO TOP-RIGHT ===
    pct = deal['discount_percent']
    badge_text = "-{}%".format(pct)
    font_badge = ImageFont.truetype(FONT_BOLD, 64)
    bbox_b = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = bbox_b[2] - bbox_b[0]
    bh = bbox_b[3] - bbox_b[1]
    pad = 22
    badge_x = W - bw - pad - 60
    badge_y = 50
    draw.rounded_rectangle(
        [badge_x - pad, badge_y - 4, badge_x + bw + pad, badge_y + bh + 12],
        radius=18, fill=ACCENT_RED
    )
    draw.text((badge_x, badge_y), badge_text, font=font_badge, fill="#FFFFFF")

    # === CARD PRODOTTO (centro con ombra) ===
    card_top = 175
    card_bottom = 715
    card_left = 100
    card_right = W - 100

    # Ombra: shape con blur
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([card_left + 8, card_top + 18, card_right + 8, card_bottom + 18],
                          radius=28, fill=(0, 0, 0, 35))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
    img.paste(shadow, (0, 0), shadow)

    # Card vera
    draw.rounded_rectangle([card_left, card_top, card_right, card_bottom],
                            radius=28, fill=CARD_BG, outline=LIGHT_GREY, width=2)

    # === IMMAGINE PRODOTTO dentro la card ===
    if deal.get("image_url"):
        product_img = _download_image(deal["image_url"])
        if product_img:
            # Resize mantenendo aspect ratio
            max_w = card_right - card_left - 80
            max_h = card_bottom - card_top - 80
            product_img.thumbnail((max_w, max_h), Image.LANCZOS)

            # Centra dentro la card
            px = card_left + (card_right - card_left - product_img.width) // 2
            py = card_top + (card_bottom - card_top - product_img.height) // 2
            # Se ha alpha channel, gestiscilo
            if product_img.mode == 'RGBA':
                img.paste(product_img, (px, py), product_img)
            else:
                img.paste(product_img, (px, py))

    # === LIGHTNING DEAL FLAME (se attivo) ===
    if deal.get("has_deal") or pct >= 50:
        flame_font = ImageFont.truetype(FONT_BOLD, 32)
        flame_text = "OFFERTA LAMPO"
        bbox_f = draw.textbbox((0, 0), flame_text, font=flame_font)
        fw = bbox_f[2] - bbox_f[0]
        fh = bbox_f[3] - bbox_f[1]
        fx = (W - fw) // 2
        fy = 745
        flame_pad = 22
        draw.rounded_rectangle(
            [fx - flame_pad - 6, fy - 8, fx + fw + flame_pad + 6, fy + fh + 16],
            radius=14, fill=ACCENT_RED
        )
        draw.text((fx, fy), flame_text, font=flame_font, fill="#FFFFFF")

    # === TITOLO PRODOTTO ===
    title = deal["title"]
    title_y = 800 if (deal.get("has_deal") or pct >= 50) else 745
    font_title = ImageFont.truetype(FONT_BOLD, 32)
    title_lines = _wrap_text(title, font_title, W - 100, draw)[:2]  # max 2 righe
    line_height = 42
    for i, line in enumerate(title_lines):
        bbox_l = draw.textbbox((0, 0), line, font=font_title)
        lw = bbox_l[2] - bbox_l[0]
        draw.text(((W - lw) // 2, title_y + i * line_height), line,
                  font=font_title, fill=TEXT_BLACK)

    # === PREZZI ===
    price_y = title_y + len(title_lines) * line_height + 30
    if price_y > 920:
        price_y = 920

    # Prezzo originale barrato (sx)
    font_orig = ImageFont.truetype(FONT_REG, 36)
    orig_text = "{:.2f}€".format(deal["original_price"])
    bbox_o = draw.textbbox((0, 0), orig_text, font=font_orig)
    ow = bbox_o[2] - bbox_o[0]
    oh = bbox_o[3] - bbox_o[1]

    # Prezzo nuovo (dx, grande)
    font_new = ImageFont.truetype(FONT_BOLD, 60)
    new_text = "{:.2f}€".format(deal["current_price"])
    bbox_n = draw.textbbox((0, 0), new_text, font=font_new)
    nw = bbox_n[2] - bbox_n[0]

    arrow = " → "
    font_arrow = ImageFont.truetype(FONT_BOLD, 36)
    bbox_a = draw.textbbox((0, 0), arrow, font=font_arrow)
    aw = bbox_a[2] - bbox_a[0]

    total_w = ow + aw + nw
    px_start = (W - total_w) // 2

    # Orig
    draw.text((px_start, price_y + 14), orig_text, font=font_orig, fill=SUBTLE_GREY)
    # Riga barrata
    draw.line([(px_start - 2, price_y + 32), (px_start + ow + 2, price_y + 32)],
              fill=SUBTLE_GREY, width=2)
    # Freccia
    draw.text((px_start + ow, price_y + 14), arrow, font=font_arrow, fill=TEXT_BLACK)
    # Nuovo
    draw.text((px_start + ow + aw, price_y - 2), new_text, font=font_new, fill=ACCENT_RED)

    # === RISPARMI (verde, piccolo, in basso) ===
    saving_text = "Risparmi {:.2f}€".format(deal["discount"])
    font_saving = ImageFont.truetype(FONT_BOLD, 28)
    bbox_s = draw.textbbox((0, 0), saving_text, font=font_saving)
    sw = bbox_s[2] - bbox_s[0]
    saving_y = price_y + 80
    if saving_y < 1020:
        draw.text(((W - sw) // 2, saving_y), saving_text, font=font_saving, fill=GREEN)

    # === HANDLE BOTTOM ===
    handle = "@sottocosto_oggi"
    font_handle = ImageFont.truetype(FONT_BOLD, 24)
    bbox_h = draw.textbbox((0, 0), handle, font=font_handle)
    hw = bbox_h[2] - bbox_h[0]
    draw.text(((W - hw) // 2, 1035), handle, font=font_handle, fill=ACCENT_RED)

    img.save(output_path, "PNG", quality=92, optimize=True)
    return True


# === TEST se eseguito direttamente ===
if __name__ == "__main__":
    test_deal = {
        "title": "Dyson V11 Aspirapolvere Senza Fili Senza Sacco",
        "current_price": 449.00,
        "original_price": 699.00,
        "discount_percent": 36,
        "discount": 250.00,
        "image_url": "https://m.media-amazon.com/images/I/61f0+r9xvBL._AC_SL1500_.jpg",
        "rating": "4.6",
        "review_count": 8423,
        "has_deal": True,
    }
    success = generate_post_image(test_deal, "/mnt/user-data/outputs/POST_test_wow_1080.png")
    print("OK!" if success else "FAIL")
