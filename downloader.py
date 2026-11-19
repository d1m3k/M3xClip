"""Download VOD YouTube dengan yt-dlp (dipanggil sebagai library,
bukan shell ke binary luar — supaya ikut terbundel ke dalam .exe).

Aturan utama: JANGAN download VOD utuh. Kita ambil metadata dulu,
lalu download HANYA segmen momen yang dibutuhkan lewat
download_ranges (setara --download-sections di CLI).

VOD "was_live" (live yang sudah selesai) diperlakukan seperti
video biasa — tidak ada perlakuan khusus.
"""

import glob
import os

from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func

# Teks error khas saat YouTube memblokir IP server ("Sign in to confirm
# you're not a bot"). Kalau kena ini, kita coba sekali lagi dengan
# player_client=android yang biasanya lolos dari bot-check.
PESAN_BOT_CHECK = "Sign in to confirm"


def _extract_info(url, opts, log=None):
    """extract_info dengan fallback: client default dulu, kalau kena
    bot-check YouTube coba lagi dengan player_client=android."""
    percobaan = [
        ("default", {}),
        ("android", {"extractor_args": {"youtube": {"player_client": ["android"]}}}),
    ]
    terakhir = None
    for nama, tambahan in percobaan:
        try:
            o = dict(opts)
            o.update(tambahan)
            with YoutubeDL(o) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001 - coba fallback dulu
            terakhir = e
            if PESAN_BOT_CHECK in str(e) and nama == "default":
                if log:
                    log("  YouTube minta verifikasi bot — coba lagi dengan client Android...")
                continue
            raise
    raise terakhir


def _download(url, opts, log=None):
    """ydl.download dengan fallback client yang sama seperti di atas."""
    percobaan = [
        ("default", {}),
        ("android", {"extractor_args": {"youtube": {"player_client": ["android"]}}}),
    ]
    terakhir = None
    for nama, tambahan in percobaan:
        try:
            o = dict(opts)
            o.update(tambahan)
            with YoutubeDL(o) as ydl:
                ydl.download([url])
            return
        except Exception as e:  # noqa: BLE001 - coba fallback dulu
            terakhir = e
            if PESAN_BOT_CHECK in str(e) and nama == "default":
                if log:
                    log("  YouTube minta verifikasi bot — coba lagi dengan client Android...")
                continue
            raise
    raise terakhir


def get_metadata(url, log=None, nocheckcertificate=False):
    """Ambil info video tanpa download: judul, channel, durasi, status live.

    Mengembalikan dict. 'duration' dalam detik (bisa None kalau gagal).
    nocheckcertificate=True HANYA untuk tes lokal di mesin yang
    sertifikatnya di-MITM proxy/antivirus — JANGAN dipakai normal.
    """
    opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "no_warnings": True,
        "nocheckcertificate": nocheckcertificate,
    }
    if log:
        log("yt-dlp: mengambil metadata video...")
    info = _extract_info(url, opts, log=log)
    meta = {
        "id": info.get("id"),
        "title": info.get("title") or "video",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration"),
        "live_status": info.get("live_status"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "webpage_url": info.get("webpage_url") or url,
    }
    if log:
        dur = meta["duration"]
        dur_teks = "%d detik (~%.1f jam)" % (dur, dur / 3600) if dur else "tidak diketahui"
        log("  Judul: %s" % meta["title"])
        log("  Channel: %s | Durasi: %s | Status: %s"
            % (meta["channel"], dur_teks, meta["live_status"]))
    return meta


def download_section(url, start_sec, end_sec, out_base, log=None, nocheckcertificate=False):
    """Download HANYA segmen [start_sec, end_sec] dari video.

    out_base : path tanpa ekstensi, misal "output/slug_seg1".
               File hasil jadi "output/slug_seg1.mp4".
    Mengembalikan path file hasil.
    """
    # ffmpeg_location: yt-dlp butuh ffmpeg untuk memotong segmen.
    # Kalau ada ffmpeg di tools/ (bundel .exe), pakai itu; kalau tidak,
    # yt-dlp memakai ffmpeg dari PATH sistem.
    ffmpeg_loc = None
    try:
        from assembler import find_ffmpeg
        ffmpeg_loc = find_ffmpeg()
    except Exception:  # noqa: BLE001 - fallback ke PATH
        ffmpeg_loc = None

    opts = {
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "nocheckcertificate": nocheckcertificate,
        # Video mp4 terbaik <=1080p + audio m4a; fallback ke best yang ada.
        "format": "bv[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": out_base + ".%(ext)s",
        # INI kuncinya: hanya segmen ini yang didownload.
        "download_ranges": download_range_func([], [(start_sec, end_sec)]),
    }
    if ffmpeg_loc:
        opts["ffmpeg_location"] = ffmpeg_loc

    if log:
        log("yt-dlp: download segmen %d-%d detik..." % (start_sec, end_sec))
    _download(url, opts, log=log)

    # Cari file hasil (ekstensi bisa mp4; jangan asumsi buta).
    hasil = sorted(glob.glob(out_base + ".*"))
    if not hasil:
        raise FileNotFoundError(
            "Segmen %d-%d tidak terdownload (file %s.* tidak ditemukan)."
            % (start_sec, end_sec, out_base)
        )
    path = hasil[0]
    if log:
        log("  Tersimpan: %s (%.1f MB)" % (path, os.path.getsize(path) / 1024 / 1024))
    return path


def list_auto_subs(url, log=None, nocheckcertificate=False):
    """Daftar bahasa auto-subtitle (auto-captions) yang tersedia di video.

    Mengembalikan list kode bahasa, misal ['id', 'en'].
    List kosong = video ini tidak punya auto-subtitle.
    """
    opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "no_warnings": True,
        "nocheckcertificate": nocheckcertificate,
    }
    info = _extract_info(url, opts, log=log)
    caps = info.get("automatic_captions") or {}
    bahasa = sorted(caps.keys())
    if log:
        if bahasa:
            log("  Auto-subtitle tersedia: %s" % ", ".join(bahasa))
        else:
            log("  Auto-subtitle: tidak ada di video ini.")
    return bahasa
