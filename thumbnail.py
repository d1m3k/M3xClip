"""Thumbnail 1080x1920 dari frame momen (pakai PIL/Pillow).

Layout:
  - Frame di-resize cover ke 1080x1920 (di-crop tengah kalau rasio beda).
  - Bagian atas dan bawah digelapkan sedikit supaya teks terbaca.
  - Hook BESAR di atas (kuning tebal + outline hitam).
  - 2-3 poin teks kecil di bawah (putih + outline).

Font: DejaVuSans-Bold (sudah ada di Linux; di Windows dicoba Arial Bold
atau font di folder fonts/ samping .exe). Tidak download font dari internet.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

LEBAR = 1080
TINGGI = 1920

# Lokasi font tebal yang dicoba, urut prioritas.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",                          # Windows
    r"C:\Windows\Fonts\DejaVuSans-Bold.ttf",
]


def _cari_font():
    """Cari file font tebal: folder fonts/ samping exe/script dulu, lalu sistem."""
    base = [os.path.dirname(os.path.abspath(__file__))]
    if getattr(sys, "frozen", False):
        base.insert(0, os.path.dirname(sys.executable))
    if hasattr(sys, "_MEIPASS"):
        base.append(sys._MEIPASS)
    for d in base:
        for nama in ("DejaVuSans-Bold.ttf", "arialbd.ttf"):
            p = os.path.join(d, "fonts", nama)
            if os.path.isfile(p):
                return p
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def load_font(ukuran):
    """Muat font tebal ukuran tertentu; fallback ke font default Pillow."""
    path = _cari_font()
    if path:
        try:
            return ImageFont.truetype(path, ukuran)
        except Exception:  # noqa: BLE001 - fallback di bawah
            pass
    try:
        return ImageFont.load_default(size=ukuran)
    except TypeError:  # Pillow lama tanpa argumen size
        return ImageFont.load_default()


def _bungkus_teks(draw, teks, font, lebar_maks):
    """Pecah teks jadi beberapa baris supaya muat dalam lebar_maks."""
    kata = teks.split()
    baris, jalan = [], ""
    for k in kata:
        coba = (jalan + " " + k).strip()
        if draw.textlength(coba, font=font) <= lebar_maks:
            jalan = coba
        else:
            if jalan:
                baris.append(jalan)
            jalan = k
    if jalan:
        baris.append(jalan)
    return baris


def make_thumbnail(frame_path, hook, points, out_path):
    """Buat thumbnail 1080x1920. Mengembalikan out_path."""
    img = Image.open(frame_path).convert("RGB")

    # Resize cover 1080x1920: scale sampai menutupi, lalu crop tengah.
    skala = max(LEBAR / img.width, TINGGI / img.height)
    baru = img.resize((int(img.width * skala) + 1, int(img.height * skala) + 1),
                      Image.LANCZOS)
    x0 = (baru.width - LEBAR) // 2
    y0 = (baru.height - TINGGI) // 2
    img = baru.crop((x0, y0, x0 + LEBAR, y0 + TINGGI))

    # Gelapkan pita atas dan bawah (untuk teks) dengan overlay hitam transparan.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d_over = ImageDraw.Draw(overlay)
    d_over.rectangle([0, 0, LEBAR, 560], fill=(0, 0, 0, 140))
    d_over.rectangle([0, 1380, LEBAR, TINGGI], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    margin = 70
    lebar_teks = LEBAR - 2 * margin

    # --- Hook besar di atas (kuning, tebal, outline hitam) ---
    font_hook = load_font(96)
    baris_hook = _bungkus_teks(draw, hook or "MOMEN HYPE", font_hook, lebar_teks)
    # Kalau hook kepanjangan, kecilkan font sampai muat max 4 baris.
    while len(baris_hook) > 4 and font_hook.size > 60:
        font_hook = load_font(font_hook.size - 8)
        baris_hook = _bungkus_teks(draw, hook or "MOMEN HYPE", font_hook, lebar_teks)
    y = 120
    for b in baris_hook:
        draw.text((LEBAR / 2, y), b, font=font_hook, fill=(255, 214, 10),
                  anchor="ma", stroke_width=4, stroke_fill=(0, 0, 0))
        y += int(font_hook.size * 1.15)

    # --- Poin-poin kecil di bawah (putih, outline hitam) ---
    font_poin = load_font(46)
    y = 1480
    for p in (points or [])[:3]:
        baris = _bungkus_teks(draw, "• " + p, font_poin, lebar_teks)
        for b in baris:
            draw.text((LEBAR / 2, y), b, font=font_poin, fill=(255, 255, 255),
                      anchor="ma", stroke_width=3, stroke_fill=(0, 0, 0))
            y += int(font_poin.size * 1.25)

    img.save(out_path, "JPEG", quality=90)
    return out_path
