"""Rakit clip vertikal 1080x1920 dengan ffmpeg.

Layout (sesuai desain M3xClip):
  ATAS  (1080x960) : gameplay — center-crop dari frame 16:9 yang
                     MENGHINDARI kotak facecam, lalu di-scale.
  BAWAH (1080x960) : facecam — crop kotak preset, di-scale cover.
  Keduanya digabung (vstack) jadi 1080x1920.

Subtitle (kalau ada) di-burn ke area gameplay (bagian atas),
supaya tidak menutupi wajah streamer di bawah.

ffmpeg dicari dengan urutan: PATH sistem -> tools/ffmpeg(.exe) di
samping script/.exe -> folder bundel PyInstaller (_MEIPASS).
"""

import json
import os
import shutil
import subprocess
import sys

LEBAR_OUT = 1080
TINGGI_OUT = 1920
TINGGI_PARUH = 960  # tiap paruh (gameplay / facecam)


def app_dir():
    """Folder tempat script/.exe berada (untuk config.json, tools/, output)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg():
    """Cari binary ffmpeg. Mengembalikan path (atau 'ffmpeg' sebagai fallback)."""
    dari_path = shutil.which("ffmpeg")
    if dari_path:
        return dari_path
    kandidat_dir = [app_dir(), os.path.join(app_dir(), "tools")]
    if hasattr(sys, "_MEIPASS"):  # folder bundel PyInstaller onefile
        kandidat_dir.append(sys._MEIPASS)
    for d in kandidat_dir:
        for nama in ("ffmpeg.exe", "ffmpeg"):
            p = os.path.join(d, nama)
            if os.path.isfile(p):
                return p
    return "ffmpeg"  # biar error-nya jelas kalau memang tidak ada


def probe_video(path):
    """Baca info video lewat ffprobe: lebar, tinggi, durasi, ada audio atau tidak."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # ffprobe biasanya satu paket dengan ffmpeg
        ffmpeg = find_ffmpeg()
        ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
        if not os.path.isfile(ffprobe):
            ffprobe = "ffprobe"
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    lebar, tinggi = int(stream["width"]), int(stream["height"])
    durasi = float(data["format"].get("duration") or 0)

    # Cek ada audio atau tidak (segmen tanpa audio tetap harus bisa dirakit).
    cmd_a = [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", path,
    ]
    res_a = subprocess.run(cmd_a, capture_output=True, text=True)
    ada_audio = bool(res_a.stdout.strip())
    return {"width": lebar, "height": tinggi, "duration": durasi, "has_audio": ada_audio}


def hitung_crop_gameplay(lebar, tinggi, facecam):
    """Hitung crop gameplay (tengah, full tinggi) yang menghindari kotak facecam.

    facecam: dict relatif {x, y, w, h}. Kotak facecam biasanya di kanan bawah.
    Lebar crop = 2 * (x_awal_facecam) - lebar_frame - margin, supaya
    tepi kanan crop tidak menyentuh facecam. Contoh 1280x720 Windah:
      x_awal facecam = 0.835*1280 = 1069  ->  2*1069 - 1280 - 48 = 810
      crop 810x720 di tengah (x0=235, x1=1045) aman dari facecam.
    """
    fx = int(facecam["x"] * lebar)
    lebar_crop = int(2 * fx - lebar) - 48
    # Jaga-jaga kalau preset aneh (facecam di tengah/kiri): minimal 320 px.
    lebar_crop = max(320, min(lebar, lebar_crop))
    x0 = max(0, (lebar - lebar_crop) // 2)
    return {"x": x0, "y": 0, "w": lebar_crop, "h": tinggi}


UKURAN_SUB = {"Kecil": 11, "Sedang": 14, "Besar": 18}


def _gaya_subtitle(ukuran="Sedang"):
    """Style subtitle ala Short referensi: kuning, outline hitam, kecil,
    di bawah area gameplay (Alignment=2, di atas batas facecam).

    FontSize di sini skala libass (frame 960 px -> x3,33): 14 berarti
    ~47 px di layar 1080 — kecil, tidak menutupi gameplay.
    """
    fs = UKURAN_SUB.get(ukuran, 14)
    return ("FontName=DejaVu Sans,FontSize=%d,Bold=1,"
            "PrimaryColour=&H00FFFF,OutlineColour=&H000000,"
            "BorderStyle=1,Outline=2,Alignment=2,MarginV=30" % fs)


def assemble_clip(segment_path, facecam, out_path, srt_path=None, log=None,
                  ukuran_sub="Sedang", subtitle_on=True, sfx_mix=None,
                  stiker_jadwal=None, preset="medium", crf=20,
                  lebar=LEBAR_OUT, tinggi=TINGGI_OUT):
    """Rakit segmen 16:9 menjadi clip vertikal (default 1080x1920).

    segment_path: video segmen hasil yt-dlp (isinya gameplay + facecam).
    facecam     : dict relatif {x, y, w, h} dari preset/Custom.
    srt_path    : file SRT subtitle (opsional, boleh None).
    ukuran_sub  : "Kecil"/"Sedang"/"Besar" (lihat UKURAN_SUB).
    subtitle_on : False = tanpa subtitle.
    sfx_mix     : file WAV berisi SFX yang sudah dicampur (relatif ke
                  awal clip) — dicampur ke audio; None = tanpa SFX.
    stiker_jadwal: list dict {path, mulai, sampai} — PNG stiker yang
                  ditampilkan di pojok kanan atas area gameplay.
    preset/crf  : kualitas encode (preview pakai ultrafast/30).
    lebar/tinggi: ukuran output (preview pakai 540x960).
    Mengembalikan out_path.
    """
    info = probe_video(segment_path)
    W, H = info["width"], info["height"]
    paruh = tinggi // 2
    if log:
        log("  Rakit clip: sumber %dx%d, durasi %.1f detik" % (W, H, info["duration"]))

    # --- Kotak facecam dalam piksel ---
    fx = max(0, int(facecam["x"] * W))
    fy = max(0, int(facecam["y"] * H))
    fw = max(1, int(facecam["w"] * W))
    fh = max(1, int(facecam["h"] * H))
    fw = min(fw, W - fx)
    fh = min(fh, H - fy)

    # --- Crop gameplay (tengah, hindari facecam) ---
    g = hitung_crop_gameplay(W, H, facecam)

    # Filter: gameplay -> scale cover lebar x paruh
    filter_top = (
        "[0:v]crop=%d:%d:%d:%d,"
        "scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d[top0]"
        % (g["w"], g["h"], g["x"], g["y"], lebar, paruh, lebar, paruh)
    )
    # Subtitle dibakar ke stream atas saja (sebelum digabung).
    if subtitle_on and srt_path and os.path.isfile(srt_path):
        srt_esc = _escape_filter_path(srt_path)
        filter_top += (";[top0]subtitles='%s':force_style='%s'[top]"
                       % (srt_esc, _gaya_subtitle(ukuran_sub)))
        if log:
            log("  Subtitle dibakar ke area gameplay (%s)." % ukuran_sub)
    else:
        filter_top += ";[top0]copy[top]"

    # Filter: facecam -> scale cover lebar x paruh
    filter_bot = (
        "[0:v]crop=%d:%d:%d:%d,"
        "scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d[bot]"
        % (fw, fh, fx, fy, lebar, paruh, lebar, paruh)
    )

    filter_bagian = ["%s;%s;[top][bot]vstack,format=yuv420p[v0]" % (
        filter_top, filter_bot)]

    # Stiker: tiap entri jadi satu input gambar (loop), di-overlay dengan
    # enable between(t, mulai, sampai) di pojok kanan atas gameplay.
    stiker_jadwal = stiker_jadwal or []
    ukuran_stiker = max(96, lebar // 4)
    label_v = "v0"
    for j, st in enumerate(stiker_jadwal):
        idx_input = 1 + j
        label_stk = "stk%d" % j
        label_next = "v%d" % (j + 1)
        filter_bagian.append(
            "[%d:v]scale=%d:%d[%s]" % (idx_input, ukuran_stiker, ukuran_stiker, label_stk))
        filter_bagian.append(
            "[%s][%s]overlay=%d:16:enable='between(t,%s,%s)'[%s]"
            % (label_v, label_stk, lebar - ukuran_stiker - 16,
               st["mulai"], st["sampai"], label_next))
        label_v = label_next

    # Audio: campur SFX ke audio segmen (kalau ada).
    idx_sfx = 1 + len(stiker_jadwal)
    label_audio = None
    if sfx_mix and os.path.isfile(sfx_mix):
        if info["has_audio"]:
            filter_bagian.append(
                "[0:a][%d:a]amix=inputs=2:normalize=0:duration=first[aout]"
                % idx_sfx)
            label_audio = "[aout]"
        else:
            label_audio = "[%d:a]" % idx_sfx

    filter_complex = ";".join(filter_bagian)

    cmd = [find_ffmpeg(), "-y", "-i", segment_path]
    for st in stiker_jadwal:
        cmd += ["-loop", "1", "-i", st["path"]]
    if sfx_mix and os.path.isfile(sfx_mix):
        cmd += ["-i", sfx_mix]
    cmd += ["-filter_complex", filter_complex, "-map", "[%s]" % label_v]
    if label_audio:
        cmd += ["-map", label_audio, "-c:a", "aac", "-b:a", "128k"]
    elif info["has_audio"]:
        cmd += ["-map", "0:a", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest", out_path,
    ]
    _jalankan_ffmpeg(cmd, "merakit clip")

    if log:
        log("  Clip jadi: %s (%.1f MB)"
            % (out_path, os.path.getsize(out_path) / 1024 / 1024))
    return out_path


def extract_frame(video_path, detik, out_jpg):
    """Ambil 1 frame dari video pada detik tertentu (untuk thumbnail)."""
    cmd = [
        find_ffmpeg(), "-y",
        "-ss", str(detik),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        out_jpg,
    ]
    _jalankan_ffmpeg(cmd, "mengambil frame thumbnail")
    return out_jpg


def _escape_filter_path(path):
    """Escape path file untuk dipakai di dalam filter ffmpeg.
    Backslash Windows jadi slash, ':' dan ''' di-escape."""
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:").replace("'", "\\'")
    return p


def _jalankan_ffmpeg(cmd, apa):
    """Jalankan ffmpeg; kalau gagal, lempar error dengan 5 baris terakhir log."""
    try:
        hasil = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg tidak ditemukan saat %s. Install ffmpeg dan pastikan "
            "ada di PATH, atau taruh ffmpeg.exe di folder tools/." % apa
        )
    if hasil.returncode != 0:
        ekor = "\n".join(hasil.stderr.strip().splitlines()[-5:])
        raise RuntimeError("ffmpeg gagal saat %s:\n%s" % (apa, ekor))
