"""Subtitle: pakai auto-subtitle YouTube (gratis, tanpa Whisper).

Alur:
  1. Download auto-subs video itu (hanya file .srt, videonya TIDAK didownload).
  2. Potong SRT sesuai segmen momen + geser waktunya ke 0 (relatif terhadap clip).
  3. Bersihkan tag HTML khas YouTube (<font>, &amp;, dsb).

Kalau video tidak punya auto-subtitle, fungsi mengembalikan None
dan program LANJUT TANPA subtitle (clip tetap jadi, tidak gagal total).
Whisper TIDAK dibundel di v1 karena terlalu berat — rencana v1.1
opsional, lihat README.
"""

import glob
import html
import os
import re

import downloader  # untuk _download (fallback client Android kalau kena bot-check)

# Bahasa yang dicoba, urut prioritas: Indonesia dulu, lalu Inggris.
PREFERENSI_BAHASA = ("id", "en")

# Pola baris waktu SRT: 00:01:23,456 --> 00:01:25,789
POLA_WAKTU = re.compile(
    r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
)


def download_auto_subs(url, start_sec, end_sec, work_dir, log=None, nocheckcertificate=False):
    """Download auto-subs, potong ke segmen, simpan sebagai SRT clip.

    Bahasa dicoba SATU PER SATU sesuai prioritas (id dulu, lalu en) —
    supaya kalau satu bahasa kena rate-limit (HTTP 429), bahasa lain
    masih bisa dicoba dan clip tidak gagal total.

    work_dir : folder sementara untuk file .srt mentah.
    Mengembalikan (path_srt_atau_None, pesan).
    nocheckcertificate=True HANYA untuk tes lokal di mesin yang
    sertifikatnya di-MITM proxy/antivirus — JANGAN dipakai normal.
    """
    os.makedirs(work_dir, exist_ok=True)
    dasar = os.path.join(work_dir, "subs")

    for bahasa in PREFERENSI_BAHASA:
        opts = {
            "quiet": True,
            "noplaylist": True,
            "skip_download": True,          # hanya subtitle, tanpa video
            "writeautomaticsub": True,       # auto-subtitle YouTube
            "subtitleslangs": [bahasa],
            "subtitlesformat": "srt",
            "outtmpl": dasar + ".%(ext)s",
            "no_warnings": True,
            "nocheckcertificate": nocheckcertificate,
        }
        try:
            downloader._download(url, opts, log=log)
        except Exception as e:  # noqa: BLE001 - coba bahasa berikut / lanjut tanpa sub
            if log:
                log("  Subtitle %s gagal: %s" % (bahasa, _singkat(e)))
            continue

        # Cari file hasil untuk bahasa ini (bisa juga hasil unduhan
        # sebelumnya yang sebagian berhasil sebelum error).
        cocok = sorted(glob.glob(dasar + ".%s.srt" % bahasa))
        if not cocok:
            # Fallback: file bahasa apa pun yang kebetulan sudah ada.
            cocok = sorted(glob.glob(dasar + ".*.srt"))
        if not cocok:
            continue
        dipilih = cocok[0]
        out_path = os.path.join(work_dir, "clip_%d_%d.srt" % (start_sec, end_sec))
        jumlah = clip_srt(dipilih, start_sec, end_sec, out_path)
        if jumlah == 0:
            continue
        if log:
            log("  Subtitle: %s (%d baris, bahasa %s)"
                % (out_path, jumlah, os.path.basename(dipilih)))
        return out_path, "OK"

    return None, ("Video ini tidak punya auto-subtitle (id/en), "
                  "atau YouTube membatasi unduhan subtitle dari IP ini (HTTP 429).")


def clip_srt(srt_path, start_sec, end_sec, out_path):
    """Potong SRT ke jendela [start_sec, end_sec] dan geser waktunya ke 0.

    Mengembalikan jumlah blok subtitle yang disimpan.
    """
    with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
        isi = f.read()

    # Blok SRT dipisah baris kosong.
    blok = re.split(r"\n\s*\n", isi.strip())
    hasil = []
    nomor = 1
    for b in blok:
        baris = b.strip().splitlines()
        if len(baris) < 2:
            continue
        # Baris waktu bisa di baris ke-1 (tanpa nomor) atau ke-2 (dengan nomor).
        m = None
        idx_waktu = None
        for i, br in enumerate(baris[:2]):
            m = POLA_WAKTU.search(br)
            if m:
                idx_waktu = i
                break
        if not m:
            continue
        s = _ke_detik(m.group(1), m.group(2), m.group(3), m.group(4))
        e = _ke_detik(m.group(5), m.group(6), m.group(7), m.group(8))
        if e <= start_sec or s >= end_sec:
            continue  # di luar segmen
        s_baru = max(0.0, s - start_sec)
        e_baru = min(float(end_sec - start_sec), e - start_sec)
        if e_baru <= s_baru:
            continue
        teks = [clean_srt_text(t) for t in baris[idx_waktu + 1:]]
        teks = [t for t in teks if t]
        if not teks:
            continue
        hasil.append("%d\n%s --> %s\n%s" % (
            nomor, _ke_timecode(s_baru), _ke_timecode(e_baru), "\n".join(teks)))
        nomor += 1

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(hasil) + ("\n" if hasil else ""))
    return len(hasil)


def clean_srt_text(teks):
    """Bersihkan satu baris subtitle: hapus tag HTML YouTube, unescape entitas."""
    t = re.sub(r"<[^>]+>", "", teks)      # <font color=...>, <b>, dsb.
    t = html.unescape(t)                  # &amp; -> &, &#39; -> '
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ke_detik(jam, menit, detik, ms):
    return int(jam) * 3600 + int(menit) * 60 + int(detik) + int(ms) / 1000.0


def _ke_timecode(detik_float):
    total_ms = int(round(detik_float * 1000))
    jam, sisa = divmod(total_ms, 3600000)
    menit, sisa = divmod(sisa, 60000)
    detik, ms = divmod(sisa, 1000)
    return "%02d:%02d:%02d,%03d" % (jam, menit, detik, ms)


def _singkat(e):
    return str(e)[:200]
