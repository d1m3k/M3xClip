"""Sound effect (SFX) untuk clip — dibuat dengan ffmpeg, tanpa file eksternal.

Efek yang tersedia (semuanya disintesis dari sinyal, bukan rekaman):
  pop   : blip pendek, buat transisi/penekanan ringan.
  boing : nada turun cepat, buat momen kocak/absurd.
  ding  : nada cerah dua-nada, buat momen "dapet" / highlight.

Jadwal SFX dibuat dari subtitle (SRT): baris yang mengandung kata
kocak/punchline (wkwk, haha, ngakak, kocak, ...) dipasangi SFX di
awal baris itu. Plus satu "pop" di awal clip sebagai pembuka.
"""

import os
import re
import subprocess

import assembler

# Kata kunci -> (jenis SFX, teks stiker). Dipakai bareng stickers.py.
KATA_KOCAK = {
    "wkwk": ("boing", "HAHA!"),
    "haha": ("boing", "HAHA!"),
    "ngakak": ("boing", "HAHA!"),
    "kocak": ("boing", "KOCAK!"),
    "lucu": ("boing", "HAHA!"),
    "anjir": ("ding", "WOW!"),
    "anjay": ("ding", "WOW!"),
    "wow": ("ding", "WOW!"),
    "mantap": ("ding", "WOW!"),
    "gila": ("ding", "WOW!"),
    "astaga": ("ding", "WOW!"),
    "parah": ("ding", "WOW!"),
}

DURASI_SFX = {"pop": 0.15, "boing": 0.45, "ding": 0.5}


def _sintesis(jenis, path):
    """Buat satu file WAV SFX dengan ffmpeg (aevalsrc = sinyal matematis)."""
    if jenis == "pop":
        # Blip 900 Hz yang cepat menghilang.
        src = "aevalsrc='0.9*sin(2*PI*900*t)*exp(-40*t)':duration=0.15"
    elif jenis == "boing":
        # Nada turun eksponensial 700 -> 150 Hz (efek "boing").
        src = "aevalsrc='0.9*sin(2*PI*(150+550*exp(-8*t))*t)*exp(-6*t)':duration=0.45"
    elif jenis == "ding":
        # Dua nada cerah (1318 + 1760 Hz) yang meredam pelan.
        src = ("aevalsrc='0.5*sin(2*PI*1318*t)*exp(-7*t)"
               "+0.4*sin(2*PI*1760*t)*exp(-7*t)':duration=0.5")
    else:
        raise ValueError("SFX tidak dikenal: %s" % jenis)
    cmd = [
        assembler.find_ffmpeg(), "-y", "-v", "error",
        "-f", "lavfi", "-i", src,
        "-ar", "44100", "-ac", "2", path,  # stereo, supaya bisa di-mix ke audio clip
    ]
    hasil = subprocess.run(cmd, capture_output=True, text=True)
    if hasil.returncode != 0:
        raise RuntimeError("gagal membuat SFX %s: %s"
                           % (jenis, hasil.stderr.strip().splitlines()[-1:]))
    return path


def siapkan_sfx(folder):
    """Buat semua file SFX ke folder. Kembalikan {jenis: path}."""
    os.makedirs(folder, exist_ok=True)
    out = {}
    for jenis in ("pop", "boing", "ding"):
        p = os.path.join(folder, "sfx_%s.wav" % jenis)
        if not os.path.isfile(p):
            _sintesis(jenis, p)
        out[jenis] = p
    return out


def _parse_srt(path):
    """Baca SRT -> list (mulai_detik, selesai_detik, teks)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        isi = f.read()
    blok = re.split(r"\n\s*\n", isi.strip())
    hasil = []
    for b in blok:
        baris = [x.strip() for x in b.strip().splitlines() if x.strip()]
        if len(baris) < 3:
            continue
        # SRT pakai koma sebagai pemisah desimal: 00:00:03,919
        m = re.match(r"(\d+):(\d+):([\d.,]+)\s*-->\s*(\d+):(\d+):([\d.,]+)",
                     baris[1])
        if not m:
            continue
        det = lambda s: float(s.replace(",", "."))
        mulai = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + det(m.group(3))
        selesai = int(m.group(4)) * 3600 + int(m.group(5)) * 60 + det(m.group(6))
        teks = " ".join(baris[2:])
        hasil.append((mulai, selesai, teks))
    return hasil


def jadwal_dari_subtitle(srt_path, mode="ramai"):
    """Buat jadwal SFX + stiker dari subtitle.

    mode "ramai"  : pop di awal clip + SFX di tiap baris berk kata kocak.
    mode "minimal": hanya pop di awal clip.
    mode "mati"   : jadwal kosong.
    Kembalikan list dict {waktu, jenis, stiker} (waktu relatif ke awal clip).
    """
    if mode == "mati":
        return []
    jadwal = [{"waktu": 0.1, "jenis": "pop", "stiker": None}]
    if mode == "minimal" or not srt_path or not os.path.isfile(srt_path):
        return jadwal
    for mulai, selesai, teks in _parse_srt(srt_path):
        rendah = teks.lower()
        for kata, (jenis, stiker) in KATA_KOCAK.items():
            if kata in rendah:
                jadwal.append({"waktu": round(mulai + 0.15, 2),
                               "jenis": jenis, "stiker": stiker,
                               "sampai": min(round(selesai, 2), round(mulai + 2.0, 2))})
                break  # satu baris = satu SFX saja
    return jadwal


def campur_jadwal(jadwal, sfx_files, out_wav, durasi_clip):
    """Campur semua SFX terjadwal jadi satu file WAV (relatif ke awal clip).

    jadwal: list dict {waktu, jenis} dari jadwal_dari_subtitle().
    Kembalikan out_wav, atau None kalau tidak ada SFX yang dijadwalkan.
    """
    entri = [j for j in jadwal if j.get("jenis")]
    if not entri:
        return None
    masukan = []
    bagian = []
    for i, j in enumerate(entri):
        masukan += ["-i", sfx_files[j["jenis"]]]
        ms = int(j["waktu"] * 1000)
        bagian.append("[%d:a]adelay=%d|%d,volume=0.6[s%d]" % (i, ms, ms, i))
    if len(entri) == 1:
        fc = ";".join(bagian) + ";[s0]anull[a]"
    else:
        fc = (";".join(bagian) + ";" +
              "".join("[s%d]" % i for i in range(len(entri))) +
              "amix=inputs=%d:normalize=0[a]" % len(entri))
    cmd = ([assembler.find_ffmpeg(), "-y", "-v", "error"] + masukan +
           ["-filter_complex", fc, "-map", "[a]", "-t", str(durasi_clip), out_wav])
    hasil = subprocess.run(cmd, capture_output=True, text=True)
    if hasil.returncode != 0:
        raise RuntimeError("gagal mencampur SFX: %s"
                           % hasil.stderr.strip().splitlines()[-1:])
    return out_wav
