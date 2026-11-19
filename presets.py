"""Preset posisi facecam tiap streamer.

Koordinat RELATIF terhadap ukuran frame video (0.0 - 1.0):
  x, y = pojok kiri-atas kotak facecam
  w, h = lebar dan tinggi kotak facecam
Contoh: x=0.835 artinya kotak mulai di 83,5% lebar frame dari kiri.

Kenapa relatif, bukan piksel? Supaya preset yang sama tetap benar
walau videonya 720p, 1080p, atau ukuran lain.
"""

# Nama preset -> data preset
PRESETS = {
    "Windah Basudara": {
        "x": 0.835,
        "y": 0.70,
        "w": 0.165,
        "h": 0.30,
        "verified": True,
        "note": "TERVERIFIKASI dari 2 frame VOD GTA VI (frame menit ke-60 dan ke-120): "
                "facecam di pojok kanan bawah, konsisten. Minimap ada di kiri bawah, "
                "HUD uang di kanan atas.",
    },
    "IShowSpeed": {
        "x": 0.85,
        "y": 0.70,
        "w": 0.15,
        "h": 0.30,
        "verified": False,
        "note": "BELUM TERVERIFIKASI — nilai default pojok kanan bawah. "
                "Sesuaikan lewat kolom Custom di GUI setelah melihat satu frame videonya.",
    },
    "Kai Cenat": {
        "x": 0.85,
        "y": 0.70,
        "w": 0.15,
        "h": 0.30,
        "verified": False,
        "note": "BELUM TERVERIFIKASI — nilai default pojok kanan bawah. "
                "Sesuaikan lewat kolom Custom di GUI setelah melihat satu frame videonya.",
    },
}


def preset_names():
    """Daftar nama preset + 'Custom' di akhir (untuk dropdown GUI)."""
    return list(PRESETS.keys()) + ["Custom"]


def get_preset(name):
    """Ambil dict koordinat {x, y, w, h} untuk nama preset.

    Mengembalikan None kalau namanya 'Custom' atau tidak dikenal.
    """
    data = PRESETS.get(name)
    if not data:
        return None
    return {"x": data["x"], "y": data["y"], "w": data["w"], "h": data["h"]}


def is_verified(name):
    """True kalau preset ini sudah dicek dari frame video asli."""
    data = PRESETS.get(name)
    return bool(data and data.get("verified"))
