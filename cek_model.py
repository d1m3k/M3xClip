"""Cek model Gemini apa saja yang bisa dipakai API key di config.json.

Jalankan dari terminal VSCode (posisi di folder M3xClip):
    .venv\\Scripts\\python.exe cek_model.py

Script ini membaca config.json LOKAL kamu dan hanya bicara ke API
Google. API key TIDAK PERNAH dicetak utuh (hanya 4 karakter terakhir)
dan TIDAK PERNAH dikirim ke mana pun selain Google — jadi hasilnya
aman dikirim ke siapa pun.

Yang ditampilkan:
  1. Daftar model generateContent yang bisa dipakai key ini.
  2. Tes cepat model default (berapa detik sampai Gemini menjawab).
"""

import json
import os
import sys
import time

try:
    from google import genai
except ImportError:
    print("Paket google-genai belum terinstall. "
          "Jalankan: .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE_DIR, "config.json")


def _bisa_generate(model):
    """True kalau info model ini menyebut generateContent."""
    for attr in ("supported_actions", "supported_methods"):
        methods = getattr(model, attr, None)
        if methods:
            return "generateContent" in methods
    return None  # info tidak tersedia — jangan menebak


def main():
    if not os.path.exists(CONFIG):
        print("config.json tidak ditemukan.")
        print("Buka GUI M3xClip dulu, isi API key, klik Simpan, lalu jalanin script ini lagi.")
        return
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    key = (cfg.get("api_key") or "").strip()
    if not key:
        print("config.json tidak berisi api_key. Isi API key dulu di GUI.")
        return
    print("Key: ...%s" % key[-4:])
    print("Model di config: %s" % (cfg.get("model") or "(tidak ada, pakai default)"))

    client = genai.Client(api_key=key)

    print("\n== Model generateContent yang bisa dipakai key ini ==")
    try:
        semua = list(client.models.list())
    except Exception as e:  # noqa: BLE001 - tampilkan apa adanya
        print("Gagal mengambil daftar model: %s" % str(e)[:300])
        return
    ada = []
    for m in semua:
        nama = getattr(m, "name", "?")
        bisa = _bisa_generate(m)
        if bisa is False:
            continue
        ada.append(nama)
        print(" - %s%s" % (nama, "" if bisa else " (tidak yakin bisa generateContent)"))
    if not ada:
        print(" (tidak ada model yang terdaftar)")

    from gemini_client import DEFAULT_MODEL
    print("\n== Tes cepat model default (%s) ==" % DEFAULT_MODEL)
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=DEFAULT_MODEL, contents="Balas persis dengan kata: OK")
        print("OK dalam %.1f detik — jawaban: %r"
              % (time.time() - t0, (resp.text or "").strip()[:20]))
    except Exception as e:  # noqa: BLE001 - tampilkan apa adanya
        print("GAGAL setelah %.1f detik: %s" % (time.time() - t0, str(e)[:300]))


if __name__ == "__main__":
    main()
