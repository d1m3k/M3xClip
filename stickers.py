"""Stiker kocak untuk clip — digambar dengan PIL, tanpa file eksternal.

Tiap stiker: bentuk bintang (starburst) kuning + teks tebal ber-outline.
Dipakai bareng sfx.py: satu baris subtitle berk kata kocak menampilkan
stiker yang cocok selama ~2 detik di pojok kanan atas area gameplay.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

WARNA = {
    "HAHA!": ("#FFD400", "#E11D2E"),   # kuning + merah
    "WOW!": ("#FFD400", "#1D4ED8"),    # kuning + biru
    "KOCAK!": ("#FFD400", "#16A34A"),  # kuning + hijau
}

UKURAN = (360, 360)  # px, transparan


def _font_bold(ukuran):
    for kandidat in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if os.path.isfile(kandidat):
            return ImageFont.truetype(kandidat, ukuran)
    return ImageFont.load_default()


def _starburst(draw, cx, cy, r_luar, r_dalam, jumlah=12, isi="#FFD400"):
    titik = []
    for i in range(jumlah * 2):
        r = r_luar if i % 2 == 0 else r_dalam
        sudut = math.pi * i / jumlah - math.pi / 2
        titik.append((cx + r * math.cos(sudut), cy + r * math.sin(sudut)))
    draw.polygon(titik, fill=isi, outline="#111111", width=4)


def buat_stiker(teks, path):
    """Gambar satu stiker (teks di dalam starburst) ke file PNG."""
    warna_isi, warna_teks = WARNA.get(teks, ("#FFD400", "#111111"))
    img = Image.new("RGBA", UKURAN, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _starburst(draw, 180, 180, 168, 132, isi=warna_isi)

    # Ukuran font menyesuaikan panjang teks supaya muat di dalam bintang.
    ukuran_font = 72 if len(teks) <= 5 else 58 if len(teks) <= 6 else 46
    font = _font_bold(ukuran_font)
    # Teks ber-outline hitam tebal (digambar 8 arah + tengah).
    for dx in (-3, -2, -1, 0, 1, 2, 3):
        for dy in (-3, -2, -1, 0, 1, 2, 3):
            if dx or dy:
                draw.text((180 + dx, 180 + dy), teks, font=font,
                          fill="#111111", anchor="mm")
    draw.text((180, 180), teks, font=font, fill=warna_teks, anchor="mm")
    img.save(path, "PNG")
    return path


def siapkan_stiker(folder, daftar_teks=("HAHA!", "WOW!", "KOCAK!")):
    """Buat semua stiker ke folder. Kembalikan {teks: path}."""
    os.makedirs(folder, exist_ok=True)
    out = {}
    for teks in daftar_teks:
        p = os.path.join(folder, "stiker_%s.png"
                         % teks.replace("!", "").lower())
        if not os.path.isfile(p):
            buat_stiker(teks, p)
        out[teks] = p
    return out
