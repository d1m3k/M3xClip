"""Klien Gemini untuk mencari momen hype di video YouTube.

Cara kerja (resmi dari Google, tanpa download video):
  Kita kirim URL YouTube langsung sebagai input video ke Gemini
  (Part.from_uri dengan file_uri = URL YouTube). Gemini "nonton"
  videonya di server Google, lalu mengembalikan daftar momen
  dalam format JSON.

Model default: gemini-2.5-flash (murah, cukup untuk tugas ini).
Model bisa diganti lewat config.json ("model").

PENTING: file ini TIDAK PERNAH menyimpan atau mencetak API key.
Key hanya dipegang di memori selama program jalan, dan berasal
dari config.json yang dibuat user sendiri di samping .exe.
"""

import json
import re

try:
    from google import genai
    from google.genai import types
except ImportError:  # SDK belum terinstall — pesan errornya jelas di bawah
    genai = None
    types = None

# Model default. Ini nama model Gemini yang resmi dan masih aktif.
# Kalau Google menggantinya di masa depan, ubah di config.json ("model").
DEFAULT_MODEL = "gemini-2.5-flash"

# Skema JSON yang diminta ke Gemini (supaya jawabannya rapi dan bisa diparse).
MOMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_sec": {"type": "integer"},
                    "end_sec": {"type": "integer"},
                    "title_id": {"type": "string"},
                    "title_en": {"type": "string"},
                    "hook": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                    "thumbnail_frame_sec": {"type": "integer"},
                    "alasan": {"type": "string"},
                },
                "required": ["start_sec", "end_sec", "title_id", "hook"],
            },
        }
    },
    "required": ["moments"],
}


class GeminiClient:
    """Pembungkus kecil di atas google-genai SDK."""

    def __init__(self, api_key, model=DEFAULT_MODEL):
        # Tanpa API key, semua fungsi gagal dengan pesan yang jelas.
        # Key TIDAK disimpan ke file apa pun dari sini.
        if not api_key or not str(api_key).strip():
            raise ValueError(
                "API key Gemini belum diisi. Isi API key dulu di GUI "
                "(kolom API Key), lalu klik Simpan."
            )
        if genai is None:
            raise ImportError(
                "Paket google-genai belum terinstall. "
                "Jalankan: pip install -r requirements.txt"
            )
        self._api_key = str(api_key).strip()
        self.model = model or DEFAULT_MODEL
        self._client = genai.Client(api_key=self._api_key)

    # ------------------------------------------------------------------
    def test_connection(self):
        """Tes murah: minta Gemini membalas satu kata.

        Mengembalikan (berhasil: bool, pesan: str).
        Pesan tidak pernah berisi API key.
        """
        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents="Balas persis dengan kata: OK",
            )
            teks = (resp.text or "").strip()
            if "OK" in teks.upper():
                return True, "Koneksi OK — Gemini menjawab (model: %s)." % self.model
            return False, "Gemini menjawab tapi tidak seperti yang diharapkan: %r" % teks[:100]
        except Exception as e:  # noqa: BLE001 - tampilkan apa adanya ke user
            return False, "Koneksi gagal: %s" % _singkat_error(e)

    # ------------------------------------------------------------------
    def find_moments(self, video_url, video_title, duration_sec,
                     num_moments=3, dur_min=30, dur_max=60, log=None):
        """Minta Gemini menonton video dan mengembalikan daftar momen.

        video_url  : URL YouTube (bisa link live/VOD, contoh /live/VIDEO_ID)
        video_title: judul video (untuk konteks)
        duration_sec: durasi total video dalam detik
        num_moments: jumlah momen yang diminta
        dur_min/dur_max: durasi tiap clip yang diinginkan (detik)
        log        : fungsi log(msg) opsional, boleh None

        Mengembalikan list dict momen yang sudah divalidasi.
        """
        if log:
            log("Gemini: mengirim URL video untuk dianalisis (tanpa download)...")
            log("  Model: %s | Momen diminta: %d | Durasi clip: %d-%d detik"
                % (self.model, num_moments, dur_min, dur_max))

        prompt = (
            "Kamu adalah editor clip YouTube Shorts/Reels. Tonton video ini "
            "(judul: \"%s\", durasi total %d detik) dan temukan %d momen PALING HYPE "
            "yang cocok jadi clip vertikal: reaksi kaget/ketawa, momen lucu, "
            "aksi keren, plot twist, atau interaksi seru dengan penonton.\n\n"
            "Aturan tiap momen:\n"
            "- Durasi antara %d sampai %d detik (start_sec dan end_sec dalam detik).\n"
            "- Momen harus berdiri sendiri: penonton yang belum nonton videonya tetap paham.\n"
            "- Urutkan dari yang paling hype.\n"
            "- title_id: judul clip Bahasa Indonesia (pendek, menarik, tanpa clickbait bohong).\n"
            "- title_en: judul yang sama dalam Bahasa Inggris.\n"
            "- hook: satu kalimat pembuka yang besar dan memancing (Bahasa Indonesia).\n"
            "- points: 2-3 poin teks pendek yang merangkum isi momen.\n"
            "- thumbnail_frame_sec: detik di dalam momen dengan ekspresi/aksi paling menarik.\n"
            "- alasan: satu kalimat kenapa momen ini hype.\n\n"
            "Jawab HANYA dalam format JSON sesuai skema yang diberikan."
            % (video_title, duration_sec, num_moments, dur_min, dur_max)
        )

        # Cara resmi video understanding: URL YouTube sebagai file_uri.
        video_part = types.Part.from_uri(file_uri=video_url, mime_type="video/mp4")

        resp = self._client.models.generate_content(
            model=self.model,
            contents=[video_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MOMENTS_SCHEMA,
                temperature=0.4,
                max_output_tokens=4096,
            ),
        )
        moments = parse_moments_json(resp.text or "")
        moments = validate_moments(moments, duration_sec, dur_min, dur_max, num_moments)
        if log:
            log("Gemini: menemukan %d momen." % len(moments))
        return moments


# ----------------------------------------------------------------------
# Fungsi parsing & validasi (bisa diuji TANPA API key dan TANPA internet)
# ----------------------------------------------------------------------
def parse_moments_json(text):
    """Parse jawaban JSON Gemini menjadi list dict momen.

    Tahan terhadap jawaban yang dibungkus ```json ... ``` atau
    dibungkus object {"moments": [...]} maupun list langsung [...].
    Field yang hilang diisi default kosong supaya program tidak crash.
    """
    if not text:
        return []
    bersih = text.strip()
    # Buang pagar kode markdown kalau ada: ```json ... ```
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", bersih, re.DOTALL)
    if m:
        bersih = m.group(1).strip()
    try:
        data = json.loads(bersih)
    except json.JSONDecodeError:
        # Coba ambil potongan JSON pertama yang ditemukan di teks.
        m2 = re.search(r"(\{.*\}|\[.*\])", bersih, re.DOTALL)
        if not m2:
            return []
        try:
            data = json.loads(m2.group(1))
        except json.JSONDecodeError:
            return []

    if isinstance(data, dict):
        daftar = data.get("moments") or data.get("clips") or []
    elif isinstance(data, list):
        daftar = data
    else:
        return []

    hasil = []
    for item in daftar:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("start_sec", 0))
            end = int(item.get("end_sec", 0))
        except (TypeError, ValueError):
            continue
        poin = item.get("points") or []
        if isinstance(poin, str):
            poin = [poin]
        hasil.append({
            "start_sec": start,
            "end_sec": end,
            "title_id": str(item.get("title_id") or ""),
            "title_en": str(item.get("title_en") or ""),
            "hook": str(item.get("hook") or ""),
            "points": [str(p) for p in poin][:3],
            "thumbnail_frame_sec": _int_atau(item.get("thumbnail_frame_sec"), start + 2),
            "alasan": str(item.get("alasan") or ""),
        })
    hasil.sort(key=lambda d: d["start_sec"])
    return hasil


def validate_moments(moments, duration_sec, dur_min=30, dur_max=60, max_count=3):
    """Bersihkan daftar momen: buang yang waktunya tidak valid,
    potong yang kepanjangan, batasi jumlahnya."""
    bersih = []
    for m in moments:
        start, end = m["start_sec"], m["end_sec"]
        if duration_sec and start >= duration_sec:
            continue
        if end <= start:
            continue
        if duration_sec:
            end = min(end, int(duration_sec))
        # Potong kalau lebih panjang dari durasi maksimal.
        if end - start > dur_max:
            end = start + dur_max
        # Buang kalau terlalu pendek (kecuali tidak bisa diperpanjang lagi).
        if end - start < dur_min:
            if duration_sec and end + (dur_min - (end - start)) <= duration_sec:
                end = start + dur_min
            else:
                continue
        m = dict(m)
        m["start_sec"], m["end_sec"] = start, end
        # Frame thumbnail harus ada di dalam momen.
        tf = m.get("thumbnail_frame_sec", start + 2)
        m["thumbnail_frame_sec"] = max(start, min(end - 1, tf))
        bersih.append(m)
        if len(bersih) >= max_count:
            break
    return bersih


def _int_atau(nilai, default):
    try:
        return int(nilai)
    except (TypeError, ValueError):
        return default


def _singkat_error(e):
    """Pesan error yang aman ditampilkan (tanpa key, tanpa traceback)."""
    msg = str(e)
    # Jangan sampai ada potongan key yang bocor ke log.
    return msg[:300]
