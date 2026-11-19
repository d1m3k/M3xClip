"""M3xClip v1.4 — GUI untuk membuat clip Reels/Shorts dari VOD YouTube.

Alur kerja 2 langkah (rekomendasi dulu, baru potong):
  LANGKAH 1 — klik "Cari Momen": ambil metadata VOD lewat yt-dlp,
  lalu Gemini menonton video lewat URL-nya langsung dan menampilkan
  daftar rekomendasi momen (judul, jam mulai-selesai, durasi, alasan).
  Atau KLIP MANUAL (tanpa Cari Momen, tanpa API key): isi durasi
  mulai/selesai sendiri (MM:SS atau detik) + judul, klik "Tambah
  sebagai momen" — momen itu masuk ke daftar yang sama.
  LANGKAH 2 — centang momen yang mau dipakai, atur edit tipis
  (ukuran subtitle, sound effect, stiker, trim mulai/selesai),
  klik "👁 Preview" untuk membuka Studio Preview: video preview di
  dalam aplikasi (bisa di-play) + timeline untuk nambah stiker lucu /
  sound effect di detik yang dipilih — lalu Render. Atau langsung klik
  "Buat Clip yang Dipilih" untuk render penuh. Untuk tiap momen yang
  dicentang, yt-dlp download HANYA durasi momen itu dari URL
  (bukan VOD utuh) -> ambil auto-subtitle -> rakit clip vertikal
  1080x1920 (subtitle kecil kuning di bawah gameplay, SFX + stiker
  kocak di momen punchline) -> buat thumbnail.
  Hasil: {output}/{slug}_clip{N}.mp4 dan {slug}_thumb{N}.jpg.

API key Gemini: dibuat user sendiri di Google AI Studio, disimpan di
config.json di samping program (tombol Simpan). Program TIDAK PERNAH
menampilkan key lengkap di log — hanya 4 karakter terakhir saat tes.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import assembler
import downloader
import gemini_client
import presets
import preview
import sfx
import stickers
import subtitler
import thumbnail

NAMA_CONFIG = "config.json"


# ----------------------------------------------------------------------
# Config (disimpan di samping script/.exe — BUKAN di repo)
# ----------------------------------------------------------------------
def config_path():
    return os.path.join(assembler.app_dir(), NAMA_CONFIG)


def load_config():
    """Baca config.json kalau ada; kalau tidak ada, pakai default."""
    default = {
        "api_key": "",
        "model": gemini_client.DEFAULT_MODEL,
        "preset": "Windah Basudara",
        "num_moments": 3,
        "dur_min": 30,
        "dur_max": 60,
        "output_dir": os.path.join(assembler.app_dir(), "output"),
        # Edit tipis (v1.2)
        "ukuran_sub": "Sedang",
        "subtitle_on": True,
        "sfx_mode": "Ramai",
        "stiker_mode": "Otomatis",
    }
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        default.update({k: v for k, v in data.items() if k in default})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return default


def save_config(cfg):
    """Simpan config.json (termasuk API key — file ini masuk .gitignore)."""
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def slug_dari_judul(judul, fallback="video"):
    """Slug aman untuk nama file, misal 'gta-vi-siap-tamat-100'."""
    s = re.sub(r"[^a-z0-9]+", "-", str(judul).lower()).strip("-")[:40]
    return s or fallback


def _format_waktu(detik):
    """Detik -> 'MM:SS' atau 'H:MM:SS', misal 531 -> '08:51'."""
    detik = int(detik)
    jam, sisa = divmod(detik, 3600)
    menit, dtk = divmod(sisa, 60)
    if jam:
        return "%d:%02d:%02d" % (jam, menit, dtk)
    return "%02d:%02d" % (menit, dtk)


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("M3xClip — Clip Generator Reels/Shorts v1.4")
        self.geometry("760x840")
        self.resizable(True, True)

        self.cfg = load_config()
        self.antrian_log = queue.Queue()
        self.antrian_ui = queue.Queue()  # tugas GUI dari thread lain
        self.sedang_jalan = False
        # Hasil LANGKAH 1 (rekomendasi momen) — dipakai LANGKAH 2.
        self.momen_list = []
        self.momen_vars = []
        self.momen_trim = []  # list (var_mulai, var_selesai) per momen
        self.meta_saat_ini = None
        self.slug_saat_ini = None
        # Edit manual dari Studio Preview: {idx_momen: [edit, ...]}
        self.edit_manual = {}
        self._studio = None
        self._studio_tmp = None

        self._bangun_ui()
        self._isi_dari_config()
        self.after(150, self._cek_antrian_log)

    # ------------------------------------------------------------------
    def _bangun_ui(self):
        pad = {"padx": 10, "pady": 4}
        baris = 0

        ttk.Label(self, text="URL YouTube (VOD / live):").grid(
            row=baris, column=0, sticky="w", **pad)
        self.url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.url_var, width=70).grid(
            row=baris, column=1, columnspan=2, sticky="ew", **pad)
        baris += 1

        ttk.Label(self, text="Streamer (preset facecam):").grid(
            row=baris, column=0, sticky="w", **pad)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(
            self, textvariable=self.preset_var,
            values=presets.preset_names(), state="readonly", width=25)
        self.preset_combo.grid(row=baris, column=1, sticky="w", **pad)
        self.preset_combo.bind("<<ComboboxSelected>>", self._saat_preset_berubah)
        self.preset_info = ttk.Label(self, text="", foreground="gray")
        self.preset_info.grid(row=baris, column=2, sticky="w", **pad)
        baris += 1

        # Koordinat Custom (hanya aktif kalau preset = Custom)
        ttk.Label(self, text="Custom facecam (x, y, w, h):").grid(
            row=baris, column=0, sticky="w", **pad)
        frame_custom = ttk.Frame(self)
        frame_custom.grid(row=baris, column=1, columnspan=2, sticky="w", **pad)
        self.custom_vars = {}
        for i, kunci in enumerate(("x", "y", "w", "h")):
            ttk.Label(frame_custom, text=kunci).grid(row=0, column=i * 2, padx=2)
            var = tk.StringVar(value="0.85" if kunci == "x" else
                               "0.70" if kunci == "y" else
                               "0.15" if kunci == "w" else "0.30")
            ent = ttk.Entry(frame_custom, textvariable=var, width=7)
            ent.grid(row=0, column=i * 2 + 1, padx=2)
            self.custom_vars[kunci] = (var, ent)
        ttk.Label(frame_custom,
                  text="(relatif 0.0-1.0)").grid(
                      row=0, column=8, padx=6)
        baris += 1

        ttk.Label(self, text="API key Gemini:").grid(
            row=baris, column=0, sticky="w", **pad)
        self.key_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.key_var, show="*", width=45).grid(
            row=baris, column=1, sticky="ew", **pad)
        frame_key = ttk.Frame(self)
        frame_key.grid(row=baris, column=2, sticky="w", **pad)
        ttk.Button(frame_key, text="Simpan", command=self._simpan_key).pack(side="left", padx=2)
        ttk.Button(frame_key, text="Tes Koneksi", command=self._tes_koneksi).pack(side="left", padx=2)
        baris += 1

        ttk.Label(self, text="Jumlah momen:").grid(
            row=baris, column=0, sticky="w", **pad)
        self.jumlah_var = tk.IntVar(value=3)
        ttk.Spinbox(self, from_=1, to=5, textvariable=self.jumlah_var, width=5).grid(
            row=baris, column=1, sticky="w", **pad)
        baris += 1

        ttk.Label(self, text="Durasi clip (detik):").grid(
            row=baris, column=0, sticky="w", **pad)
        frame_dur = ttk.Frame(self)
        frame_dur.grid(row=baris, column=1, sticky="w", **pad)
        self.dur_min_var = tk.IntVar(value=30)
        self.dur_max_var = tk.IntVar(value=60)
        ttk.Spinbox(frame_dur, from_=10, to=90, textvariable=self.dur_min_var, width=5).pack(side="left")
        ttk.Label(frame_dur, text=" s.d. ").pack(side="left")
        ttk.Spinbox(frame_dur, from_=15, to=90, textvariable=self.dur_max_var, width=5).pack(side="left")
        baris += 1

        ttk.Label(self, text="Folder output:").grid(
            row=baris, column=0, sticky="w", **pad)
        self.output_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.output_var, width=55).grid(
            row=baris, column=1, sticky="ew", **pad)
        ttk.Button(self, text="Browse...", command=self._pilih_output).grid(
            row=baris, column=2, sticky="w", **pad)
        baris += 1

        # --- Edit tipis (dipakai saat Preview & Buat Clip) ---
        frame_edit = ttk.LabelFrame(self, text="Edit tipis (sebelum render)")
        frame_edit.grid(row=baris, column=0, columnspan=3,
                        sticky="ew", padx=10, pady=4)
        ttk.Label(frame_edit, text="Subtitle:").grid(
            row=0, column=0, sticky="w", padx=4, pady=4)
        self.ukuran_sub_var = tk.StringVar(value="Sedang")
        ttk.Combobox(frame_edit, textvariable=self.ukuran_sub_var,
                     values=["Kecil", "Sedang", "Besar"],
                     state="readonly", width=8).grid(
                         row=0, column=1, padx=2, pady=4)
        self.subtitle_on_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_edit, text="tampilkan",
                        variable=self.subtitle_on_var).grid(
                            row=0, column=2, padx=2, pady=4)
        ttk.Label(frame_edit, text="Sound:").grid(
            row=0, column=3, sticky="w", padx=(10, 2), pady=4)
        self.sfx_var = tk.StringVar(value="Ramai")
        ttk.Combobox(frame_edit, textvariable=self.sfx_var,
                     values=["Mati", "Minimal", "Ramai"],
                     state="readonly", width=8).grid(
                         row=0, column=4, padx=2, pady=4)
        ttk.Label(frame_edit, text="Stiker:").grid(
            row=0, column=5, sticky="w", padx=(10, 2), pady=4)
        self.stiker_var = tk.StringVar(value="Otomatis")
        ttk.Combobox(frame_edit, textvariable=self.stiker_var,
                     values=["Mati", "Otomatis"],
                     state="readonly", width=9).grid(
                         row=0, column=6, padx=2, pady=4)
        baris += 1

        frame_tombol = ttk.Frame(self)
        frame_tombol.grid(row=baris, column=0, columnspan=3,
                          sticky="ew", padx=10, pady=8)
        frame_tombol.columnconfigure(0, weight=1)
        frame_tombol.columnconfigure(1, weight=1)
        frame_tombol.columnconfigure(2, weight=1)
        self.tombol_cari = ttk.Button(
            frame_tombol, text="🔍  Cari Momen", command=self._klik_cari_momen)
        self.tombol_cari.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.tombol_preview = ttk.Button(
            frame_tombol, text="👁  Preview", command=self._klik_preview,
            state="disabled")
        self.tombol_preview.grid(row=0, column=1, sticky="ew", padx=4)
        self.tombol_buat = ttk.Button(
            frame_tombol, text="✂️  Buat Clip yang Dipilih",
            command=self._klik_buat_clip, state="disabled")
        self.tombol_buat.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        baris += 1

        # --- Klip manual: isi durasi sendiri, tanpa Cari Momen (tanpa key) ---
        frame_manual = ttk.LabelFrame(
            self, text="Klip manual — isi durasi sendiri (tanpa Cari Momen, tanpa API key)")
        frame_manual.grid(row=baris, column=0, columnspan=3,
                          sticky="ew", padx=10, pady=(4, 0))
        ttk.Label(frame_manual, text="Mulai").grid(
            row=0, column=0, sticky="w", padx=(6, 2), pady=4)
        self.manual_mulai_var = tk.StringVar(value="08:51")
        ttk.Entry(frame_manual, textvariable=self.manual_mulai_var,
                  width=10).grid(row=0, column=1, padx=2, pady=4)
        ttk.Label(frame_manual, text="s.d.").grid(row=0, column=2, padx=2, pady=4)
        self.manual_selesai_var = tk.StringVar(value="09:26")
        ttk.Entry(frame_manual, textvariable=self.manual_selesai_var,
                  width=10).grid(row=0, column=3, padx=2, pady=4)
        ttk.Label(frame_manual, text="Judul (opsional)").grid(
            row=0, column=4, sticky="w", padx=(8, 2), pady=4)
        self.manual_judul_var = tk.StringVar()
        ttk.Entry(frame_manual, textvariable=self.manual_judul_var,
                  width=22).grid(row=0, column=5, padx=2, pady=4)
        ttk.Button(frame_manual, text="＋ Tambah sebagai momen",
                   command=self._tambah_momen_manual).grid(
                       row=0, column=6, padx=(6, 4), pady=4)
        ttk.Label(frame_manual,
                  text="Format: MM:SS atau detik (mis. 08:51 atau 531). Durasi 5–180 detik. "
                       "Momen manual ikut terhapus kalau Cari Momen dijalankan lagi.",
                  foreground="gray").grid(row=1, column=0, columnspan=7,
                                          sticky="w", padx=6, pady=(0, 4))
        baris += 1

        ttk.Label(self, text="Momen yang ditemukan (centang yang mau dibuat clip):").grid(
            row=baris, column=0, columnspan=3, sticky="w", padx=10)
        baris += 1
        self.frame_momen = ttk.Frame(self, relief="sunken", borderwidth=1)
        self.frame_momen.grid(row=baris, column=0, columnspan=3,
                              sticky="ew", padx=10, pady=4)
        ttk.Label(self.frame_momen,
                  text="Belum ada momen — isi URL + API key, lalu klik “Cari Momen”.",
                  foreground="gray").pack(anchor="w", padx=6, pady=6)
        baris += 1

        self.status_var = tk.StringVar(value="Siap. Isi URL + API key, lalu Cari Momen.")
        ttk.Label(self, textvariable=self.status_var, foreground="blue").grid(
            row=baris, column=0, columnspan=3, sticky="w", padx=10)
        baris += 1

        self.log_widget = scrolledtext.ScrolledText(self, height=12, wrap="word")
        self.log_widget.grid(row=baris, column=0, columnspan=3,
                             sticky="nsew", padx=10, pady=6)
        self.grid_rowconfigure(baris, weight=1)
        self.grid_columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    def _isi_dari_config(self):
        self.preset_var.set(self.cfg.get("preset", "Windah Basudara"))
        self.key_var.set(self.cfg.get("api_key", ""))
        self.jumlah_var.set(self.cfg.get("num_moments", 3))
        self.dur_min_var.set(self.cfg.get("dur_min", 30))
        self.dur_max_var.set(self.cfg.get("dur_max", 60))
        self.output_var.set(self.cfg.get("output_dir", ""))
        self.ukuran_sub_var.set(self.cfg.get("ukuran_sub", "Sedang"))
        self.subtitle_on_var.set(self.cfg.get("subtitle_on", True))
        self.sfx_var.set(self.cfg.get("sfx_mode", "Ramai"))
        self.stiker_var.set(self.cfg.get("stiker_mode", "Otomatis"))
        self._saat_preset_berubah()

    def _saat_preset_berubah(self, event=None):
        nama = self.preset_var.get()
        if nama == "Custom":
            for var, ent in self.custom_vars.values():
                ent.configure(state="normal")
            self.preset_info.configure(text="Isi koordinat sendiri (0.0-1.0).")
        else:
            for var, ent in self.custom_vars.values():
                ent.configure(state="disabled")
            if presets.is_verified(nama):
                self.preset_info.configure(text="✓ Terverifikasi dari frame video.")
            else:
                self.preset_info.configure(
                    text="⚠ Belum terverifikasi — cek hasilnya, sesuaikan via Custom.")

    # ------------------------------------------------------------------
    # Log (aman dari thread lain lewat queue)
    # ------------------------------------------------------------------
    def log(self, pesan):
        self.antrian_log.put(pesan)

    def _cek_antrian_log(self):
        try:
            while True:
                pesan = self.antrian_log.get_nowait()
                self.log_widget.insert("end", pesan + "\n")
                self.log_widget.see("end")
        except queue.Empty:
            pass
        # Tugas GUI dari thread lain (mis. menampilkan daftar momen) —
        # dijalankan di sini supaya selalu di thread utama.
        try:
            while True:
                job = self.antrian_ui.get_nowait()
                job()
        except queue.Empty:
            pass
        self.after(150, self._cek_antrian_log)

    def _set_status(self, teks):
        self.status_var.set(teks)

    # ------------------------------------------------------------------
    # Aksi tombol
    # ------------------------------------------------------------------
    def _simpan_key(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning("API key kosong", "Isi API key dulu.")
            return
        self.cfg["api_key"] = key
        self.cfg["model"] = self.cfg.get("model", gemini_client.DEFAULT_MODEL)
        save_config(self.cfg)
        self.log("API key disimpan ke config.json (hanya 4 karakter terakhir "
                 "yang pernah ditampilkan: ...%s)." % key[-4:])
        messagebox.showinfo("Tersimpan", "API key disimpan di config.json "
                            "di samping program. Jangan bagikan file itu.")

    def _tes_koneksi(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning("API key kosong", "Isi API key dulu.")
            return
        self._set_status("Mengetes koneksi Gemini...")
        self.log("Tes koneksi Gemini (key ...%s)..." % key[-4:])
        threading.Thread(target=self._tes_koneksi_thread, args=(key,), daemon=True).start()

    def _tes_koneksi_thread(self, key):
        try:
            klien = gemini_client.GeminiClient(
                key, model=self.cfg.get("model", gemini_client.DEFAULT_MODEL))
            ok, pesan = klien.test_connection()
            self.log(pesan)
            self._set_status("Tes koneksi: " + ("OK" if ok else "GAGAL"))
        except Exception as e:  # noqa: BLE001 - tampilkan ke user
            self.log("Tes koneksi gagal: %s" % e)
            self._set_status("Tes koneksi: GAGAL")

    def _pilih_output(self):
        folder = filedialog.askdirectory(initialdir=self.output_var.get() or ".")
        if folder:
            self.output_var.set(folder)

    def _simpan_preferensi(self):
        """Simpan pilihan GUI ke config (bukan key — key hanya lewat tombol Simpan)."""
        self.cfg.update({
            "preset": self.preset_var.get(),
            "num_moments": self.jumlah_var.get(),
            "dur_min": self.dur_min_var.get(),
            "dur_max": self.dur_max_var.get(),
            "output_dir": self.output_var.get().strip() or "output",
            "ukuran_sub": self.ukuran_sub_var.get(),
            "subtitle_on": self.subtitle_on_var.get(),
            "sfx_mode": self.sfx_var.get(),
            "stiker_mode": self.stiker_var.get(),
        })

    def _validasi_awal(self, butuh_key=True):
        """Cek URL + key sebelum jalan. Kembalikan False kalau belum lengkap.
        Klip manual & Preview tidak butuh key (butuh_key=False)."""
        if not self.url_var.get().strip():
            messagebox.showwarning("URL kosong", "Isi URL YouTube dulu.")
            return False
        if butuh_key and not self.key_var.get().strip():
            messagebox.showwarning(
                "API key kosong",
                "Isi API key Gemini dulu (dibuat di Google AI Studio).\n"
                "Lihat README.md bagian 'Mendapatkan API key'.")
            return False
        return True

    # ------------------------------------------------------------------
    # LANGKAH 1 — Cari momen: Gemini rekomendasi dulu, user yang pilih
    # ------------------------------------------------------------------
    def _klik_cari_momen(self):
        if self.sedang_jalan:
            return
        if not self._validasi_awal():
            return
        self._simpan_preferensi()
        self.sedang_jalan = True
        self.tombol_cari.configure(state="disabled")
        self.tombol_preview.configure(state="disabled")
        self.tombol_buat.configure(state="disabled")
        self._set_status("Mencari momen... lihat log di bawah.")
        threading.Thread(target=self._cari_momen_thread, daemon=True).start()

    def _cari_momen_thread(self):
        """Jalan di thread terpisah supaya GUI tidak freeze."""
        log = self.log
        try:
            url = self.url_var.get().strip()
            key = self.key_var.get().strip()

            # 1. Metadata VOD
            meta = downloader.get_metadata(url, log=log)
            durasi = meta.get("duration") or 0

            # 2. Gemini cari momen (rekomendasi — belum download apa pun)
            klien = gemini_client.GeminiClient(
                key, model=self.cfg.get("model", gemini_client.DEFAULT_MODEL))
            momen = klien.find_moments(
                url, meta["title"], durasi,
                num_moments=self.jumlah_var.get(),
                dur_min=self.dur_min_var.get(),
                dur_max=self.dur_max_var.get(),
                log=log)
            if not momen:
                raise RuntimeError("Gemini tidak mengembalikan momen. "
                                   "Coba lagi atau ganti video.")
            log("Gemini: menemukan %d momen — centang yang mau dibuat clip."
                % len(momen))
            # Tampilkan di GUI (harus lewat antrean UI — jalan di thread utama).
            self.antrian_ui.put(lambda: self._tampilkan_momen(momen, meta))
            self._set_status("Ditemukan %d momen — centang lalu klik 'Buat Clip yang Dipilih'."
                             % len(momen))
        except Exception as e:  # noqa: BLE001 - tampilkan ke user
            log("BERHENTI: %s" % e)
            self._set_status("Gagal: %s" % str(e)[:100])
        finally:
            self.sedang_jalan = False
            self.tombol_cari.configure(state="normal")

    def _tampilkan_momen(self, momen, meta):
        """Isi daftar rekomendasi di GUI (jalan di thread utama)."""
        for w in self.frame_momen.winfo_children():
            w.destroy()
        self.momen_list = momen
        self.meta_saat_ini = meta
        self.slug_saat_ini = slug_dari_judul(meta.get("title") or "",
                                             meta.get("id") or "video")
        self.momen_vars = []
        self.momen_trim = []
        for m in momen:
            self._tambah_baris_momen(m)
        self.tombol_buat.configure(state="normal")
        self.tombol_preview.configure(state="normal")

    def _tambah_baris_momen(self, m):
        """Tambah 1 baris momen (checkbox + alasan + trim) ke daftar."""
        var = tk.BooleanVar(value=True)
        self.momen_vars.append(var)
        judul = "%s–%s  •  %d dtk  •  %s" % (
            _format_waktu(m["start_sec"]), _format_waktu(m["end_sec"]),
            m["end_sec"] - m["start_sec"],
            m.get("title_id") or "(tanpa judul)")
        cb = tk.Checkbutton(self.frame_momen, text=judul, variable=var,
                            anchor="w", justify="left", wraplength=700)
        cb.pack(anchor="w", padx=6, pady=(6, 0))
        alasan = (m.get("alasan") or "").strip()
        if alasan:
            ttk.Label(self.frame_momen, text="      " + alasan,
                      foreground="gray", wraplength=700,
                      justify="left").pack(anchor="w", padx=6)
        # Trim tipis: geser mulai/selesai momen (detik).
        frame_trim = ttk.Frame(self.frame_momen)
        frame_trim.pack(anchor="w", padx=6)
        ttk.Label(frame_trim, text="      trim: mulai").pack(side="left")
        var_mulai = tk.IntVar(value=m["start_sec"])
        ttk.Spinbox(frame_trim, from_=0, to=99999,
                    textvariable=var_mulai, width=6).pack(side="left", padx=2)
        ttk.Label(frame_trim, text="s.d.").pack(side="left")
        var_selesai = tk.IntVar(value=m["end_sec"])
        ttk.Spinbox(frame_trim, from_=1, to=99999,
                    textvariable=var_selesai, width=6).pack(side="left", padx=2)
        ttk.Label(frame_trim, text="dtk").pack(side="left")
        self.momen_trim.append((var_mulai, var_selesai))

    # ------------------------------------------------------------------
    # Klip manual — isi durasi sendiri, tanpa Cari Momen
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_waktu(teks):
        """Parse durasi: 'MM:SS', 'HH:MM:SS', atau detik ('531').
        Kembalikan detik (int). ValueError kalau formatnya salah."""
        teks = (teks or "").strip()
        if not teks:
            raise ValueError("durasi kosong")
        if ":" in teks:
            bagian = teks.split(":")
            if len(bagian) not in (2, 3) or not all(
                    b.strip().isdigit() for b in bagian):
                raise ValueError("format waktu salah: %s" % teks)
            angka = [int(b) for b in bagian]
            if len(angka) == 2:
                menit, detik = angka
                if menit < 0 or detik < 0 or detik >= 60:
                    raise ValueError("menit/detik tidak masuk akal: %s" % teks)
                return menit * 60 + detik
            jam, menit, detik = angka
            if jam < 0 or menit < 0 or detik < 0 or menit >= 60 or detik >= 60:
                raise ValueError("jam/menit/detik tidak masuk akal: %s" % teks)
            return jam * 3600 + menit * 60 + detik
        if not teks.isdigit():
            raise ValueError("format waktu salah: %s" % teks)
        return int(teks)

    def _tambah_momen_manual(self):
        """Tambah momen dari durasi yang diisi manual ke daftar momen."""
        if not self.url_var.get().strip():
            messagebox.showwarning("URL kosong", "Isi URL YouTube dulu.")
            return
        try:
            mulai = self._parse_waktu(self.manual_mulai_var.get())
            selesai = self._parse_waktu(self.manual_selesai_var.get())
        except ValueError as e:
            messagebox.showwarning("Durasi salah", str(e) +
                                   "\nFormat: MM:SS atau detik, mis. 08:51 atau 531.")
            return
        if selesai <= mulai:
            messagebox.showwarning("Durasi salah",
                                   "Waktu selesai harus lebih besar dari waktu mulai.")
            return
        durasi = selesai - mulai
        if durasi < 5:
            messagebox.showwarning("Durasi salah",
                                   "Durasi minimal 5 detik (saat ini %d detik)." % durasi)
            return
        if durasi > 180:
            messagebox.showwarning(
                "Durasi salah",
                "Durasi maksimal 180 detik (3 menit, batas YouTube Shorts) — "
                "saat ini %d detik. Potong jadi beberapa momen." % durasi)
            return
        judul = self.manual_judul_var.get().strip()
        if not judul:
            judul = "Klip manual %s–%s" % (_format_waktu(mulai),
                                           _format_waktu(selesai))
        m = {"start_sec": mulai, "end_sec": selesai, "title_id": judul,
             "hook": judul, "points": [],
             "thumbnail_frame_sec": mulai + 2,
             "alasan": "Momen manual — durasi dimasukkan sendiri.",
             "manual": True}
        if not self.momen_list:
            for w in self.frame_momen.winfo_children():
                w.destroy()
        self.momen_list.append(m)
        self._tambah_baris_momen(m)
        self.tombol_buat.configure(state="normal")
        self.tombol_preview.configure(state="normal")
        self.log("Momen manual ditambah: %s (%d–%d detik) — centang lalu "
                 "klik Preview atau Buat Clip." % (judul, mulai, selesai))
        self._set_status("Momen manual ditambah: %s" % judul)

    # ------------------------------------------------------------------
    # LANGKAH 2 — Buat clip dari momen yang dicentang
    # ------------------------------------------------------------------
    def _klik_buat_clip(self):
        if self.sedang_jalan:
            return
        if not self.momen_list:
            messagebox.showwarning("Belum ada momen",
                                   "Klik 'Cari Momen' dulu.")
            return
        dipilih = [i for i, v in enumerate(self.momen_vars) if v.get()]
        if not dipilih:
            messagebox.showwarning("Tidak ada yang dicentang",
                                   "Centang minimal 1 momen yang mau dibuat clip.")
            return
        # Key Gemini cuma butuh kalau ada momen hasil Cari Momen yang dipilih;
        # momen manual murni tidak butuh key.
        butuh_key = any(not self.momen_list[i].get("manual") for i in dipilih)
        if not self._validasi_awal(butuh_key=butuh_key):
            return
        self._simpan_preferensi()
        self.sedang_jalan = True
        self.tombol_cari.configure(state="disabled")
        self.tombol_preview.configure(state="disabled")
        self.tombol_buat.configure(state="disabled")
        self._set_status("Membuat clip... lihat log di bawah.")
        threading.Thread(target=self._buat_clip_thread, args=(dipilih,),
                         daemon=True).start()

    def _buat_clip_thread(self, dipilih):
        """Jalan di thread terpisah supaya GUI tidak freeze.

        Untuk tiap momen yang dicentang: yt-dlp download HANYA durasi
        momen itu dari URL (bukan VOD utuh) -> auto-subtitle -> rakit
        clip vertikal -> thumbnail.
        """
        log = self.log
        try:
            url = self.url_var.get().strip()
            preset_nama = self.preset_var.get()
            # Kalau belum pernah Cari Momen (aliran klip manual murni),
            # ambil metadata dulu supaya nama file clip pakai judul video.
            meta = self.meta_saat_ini or {}
            if not meta:
                meta = downloader.get_metadata(url, log=log)
                self.meta_saat_ini = meta
                self.slug_saat_ini = slug_dari_judul(
                    meta.get("title") or "", meta.get("id") or "video")
            slug = self.slug_saat_ini or slug_dari_judul(
                meta.get("title") or "", meta.get("id") or "video")

            # Facecam: preset atau Custom (dihitung di sini supaya kalau
            # preset diganti setelah Cari Momen, yang dipakai yang terbaru).
            if preset_nama == "Custom":
                try:
                    facecam = {k: float(v.get()) for k, (v, e) in self.custom_vars.items()}
                except ValueError:
                    raise ValueError("Koordinat Custom harus angka 0.0-1.0.")
            else:
                facecam = presets.get_preset(preset_nama)
            log("Preset facecam: %s %s" % (preset_nama, facecam))

            # 4. Proses tiap momen yang dicentang
            out_dir = self.output_var.get().strip() or "output"
            os.makedirs(out_dir, exist_ok=True)
            tmp_dir = tempfile.mkdtemp(prefix="m3xclip_")
            berhasil = 0
            momen = self.momen_list
            for idx in dipilih:
                clip = self._proses_satu_momen(
                    idx, momen[idx], url, facecam, out_dir, tmp_dir, slug, log=log,
                    edit_manual=self.edit_manual.get(idx, []))
                if clip:
                    berhasil += 1

            shutil.rmtree(tmp_dir, ignore_errors=True)
            log("SELESAI: %d/%d clip berhasil. Hasil di: %s"
                % (berhasil, len(dipilih), os.path.abspath(out_dir)))
            self._set_status("Selesai: %d/%d clip di %s" % (berhasil, len(dipilih), out_dir))
        except Exception as e:  # noqa: BLE001 - tampilkan ke user
            log("BERHENTI: %s" % e)
            self._set_status("Gagal: %s" % str(e)[:100])
        finally:
            self.sedang_jalan = False
            self.tombol_cari.configure(state="normal")
            if self.momen_list:
                self.tombol_buat.configure(state="normal")
                self.tombol_preview.configure(state="normal")

    def _proses_satu_momen(self, idx, m, url, facecam, out_dir, tmp_dir, slug,
                           preview=False, log=None, seg_path=None, srt_path=None,
                           edit_manual=None):
        """Proses SATU momen: download segmen (durasi trim) -> subtitle ->
        SFX + stiker dari kata kocak -> rakit clip -> thumbnail.
        Kembalikan clip_path, atau None kalau gagal.
        Dipakai Buat Clip (penuh), Preview (cepat, resolusi rendah) dan
        Render dari Studio Preview (seg_path/srt_path sudah ada).
        edit_manual: list edit dari timeline Studio Preview."""
        log = log or self.log
        i = idx + 1
        # Trim dari spinbox (kalau ada), dijaga tetap masuk akal.
        mulai, selesai = self._trim_momen(idx, m)
        try:
            log("=== Momen %d: %s (%d-%d detik)%s ===" % (
                i, m.get("title_id") or "?", mulai, selesai,
                " [PREVIEW]" if preview else ""))
            if seg_path and os.path.isfile(seg_path):
                seg = seg_path
                log("  Segmen sudah ada (dari Studio Preview).")
            else:
                seg_base = os.path.join(tmp_dir, "seg%d" % i)
                seg = downloader.download_section(url, mulai, selesai, seg_base, log=log)

            srt = srt_path if (srt_path and os.path.isfile(srt_path)) else None
            if srt is None:
                srt, pesan_sub = subtitler.download_auto_subs(
                    url, mulai, selesai, tmp_dir, log=log)
                if not srt:
                    log("  Subtitle: %s — lanjut TANPA subtitle." % pesan_sub)

            # SFX + stiker dari subtitle (baris berk kata kocak).
            mode_sfx = self.sfx_var.get()
            mode_stiker = self.stiker_var.get()
            jadwal = sfx.jadwal_dari_subtitle(srt, mode_sfx) if srt else []
            # Edit manual dari Studio Preview (timeline) selalu menang.
            for e in (edit_manual or []):
                entri = {"waktu": e["waktu"], "manual": True}
                if e["kind"] == "sfx":
                    entri.update({"jenis": e["nilai"], "stiker": None})
                else:
                    entri.update({"jenis": None, "stiker": e["nilai"],
                                  "sampai": e.get("sampai", e["waktu"] + 2.0)})
                jadwal.append(entri)
            sfx_mix = None
            jadwal_sfx = [j for j in jadwal
                          if j.get("jenis") and (j.get("manual") or mode_sfx != "Mati")]
            if jadwal_sfx:
                berkas_sfx = sfx.siapkan_sfx(os.path.join(tmp_dir, "sfx"))
                sfx_mix = sfx.campur_jadwal(
                    jadwal_sfx, berkas_sfx,
                    os.path.join(tmp_dir, "mix%d.wav" % i), selesai - mulai)
                if sfx_mix:
                    log("  SFX: %d efek dicampur." % len(jadwal_sfx))
            stiker_jadwal = []
            entri_stiker = [j for j in jadwal
                            if j.get("stiker") and (j.get("manual") or mode_stiker == "Otomatis")]
            if entri_stiker:
                berkas_stiker = stickers.siapkan_stiker(
                    os.path.join(tmp_dir, "stiker"))
                for j in entri_stiker:
                    stiker_jadwal.append({
                        "path": berkas_stiker[j["stiker"]],
                        "mulai": j["waktu"],
                        "sampai": j.get("sampai", j["waktu"] + 2.0),
                    })
                log("  Stiker: %d stiker." % len(stiker_jadwal))

            nama = ("preview_clip%d.mp4" % i) if preview else ("%s_clip%d.mp4" % (slug, i))
            clip_path = os.path.join(out_dir, nama)
            assembler.assemble_clip(
                seg, facecam, clip_path, srt, log=log,
                ukuran_sub=self.ukuran_sub_var.get(),
                subtitle_on=self.subtitle_on_var.get(),
                sfx_mix=sfx_mix, stiker_jadwal=stiker_jadwal,
                preset="ultrafast" if preview else "medium",
                crf=30 if preview else 20,
                lebar=540 if preview else 1080,
                tinggi=960 if preview else 1920)

            # Frame thumbnail: detiknya RELATIF terhadap awal segmen,
            # karena seg cuma berisi potongan momen itu (bukan VOD utuh).
            frame_dtk = (m.get("thumbnail_frame_sec") or mulai + 2) - mulai
            frame_dtk = max(0, frame_dtk)
            frame_path = os.path.join(tmp_dir, "thumb%d.jpg" % i)
            assembler.extract_frame(seg, frame_dtk, frame_path)
            thumb_path = os.path.join(out_dir, "%s_thumb%d.jpg" % (slug, i))
            thumbnail.make_thumbnail(
                frame_path, m.get("hook") or m.get("title_id") or "",
                m.get("points", []), thumb_path)
            log("  Thumbnail: %s" % thumb_path)

            # Bersihkan file sementara segmen (hemat disk).
            for f in (seg, srt):
                if f and os.path.isfile(f):
                    os.remove(f)
            return clip_path
        except Exception as e:  # noqa: BLE001 - lanjut ke momen berikut
            log("  GAGAL momen %d: %s" % (i, e))
            return None

    # ------------------------------------------------------------------
    # Preview — render cepat (resolusi rendah) sebelum render penuh
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Studio Preview — video preview di dalam aplikasi + timeline edit
    # ------------------------------------------------------------------
    def _klik_preview(self):
        """Buka Studio Preview untuk momen pertama yang dicentang."""
        if self.sedang_jalan:
            return
        if not self.momen_list:
            messagebox.showwarning("Belum ada momen",
                                   "Klik 'Cari Momen' dulu.")
            return
        dipilih = [i for i, v in enumerate(self.momen_vars) if v.get()]
        if not dipilih:
            messagebox.showwarning("Tidak ada yang dicentang",
                                   "Centang minimal 1 momen untuk di-preview.")
            return
        # Studio Preview tidak memakai Gemini — tidak butuh API key.
        if not self._validasi_awal(butuh_key=False):
            return
        self._simpan_preferensi()
        self.sedang_jalan = True
        self.tombol_cari.configure(state="disabled")
        self.tombol_preview.configure(state="disabled")
        self.tombol_buat.configure(state="disabled")
        self._set_status("Menyiapkan Studio Preview...")
        threading.Thread(target=self._siapkan_studio_thread,
                         args=(dipilih[0],), daemon=True).start()

    def _facecam_saat_ini(self):
        """Facecam dari preset/Custom saat ini (dipakai preview & render)."""
        preset_nama = self.preset_var.get()
        if preset_nama == "Custom":
            try:
                return {k: float(v.get())
                        for k, (v, e) in self.custom_vars.items()}
            except ValueError:
                raise ValueError("Koordinat Custom harus angka 0.0-1.0.")
        return presets.get_preset(preset_nama)

    def _trim_momen(self, idx, m):
        """Mulai/selesai momen dari spinbox trim (dijaga masuk akal)."""
        try:
            mulai = int(self.momen_trim[idx][0].get())
            selesai = int(self.momen_trim[idx][1].get())
        except (IndexError, AttributeError, ValueError, tk.TclError):
            mulai, selesai = m["start_sec"], m["end_sec"]
        mulai = max(0, mulai)
        selesai = max(mulai + 5, selesai)
        return mulai, selesai

    def _siapkan_studio_thread(self, idx):
        """Download segmen + subtitle, ekstrak strip frame, lalu buka studio
        di thread utama (lewat antrian_ui)."""
        log = self.log
        try:
            m = self.momen_list[idx]
            mulai, selesai = self._trim_momen(idx, m)
            url = self.url_var.get().strip()
            facecam = self._facecam_saat_ini()
            log("Preset facecam: %s %s" % (self.preset_var.get(), facecam))
            tmp_dir = tempfile.mkdtemp(prefix="m3xstudio_")
            seg = downloader.download_section(
                url, mulai, selesai, os.path.join(tmp_dir, "seg"), log=log)
            srt, pesan_sub = subtitler.download_auto_subs(
                url, mulai, selesai, tmp_dir, log=log)
            if not srt:
                log("  Subtitle: %s — preview TANPA subtitle." % pesan_sub)
            frames, durasi = preview.ekstrak_strip(
                seg, os.path.join(tmp_dir, "strip"))
            srt_entries = sfx._parse_srt(srt) if srt else []
            jadwal_auto = (sfx.jadwal_dari_subtitle(srt, self.sfx_var.get())
                           if srt else [])
            stiker_files = stickers.siapkan_stiker(
                os.path.join(tmp_dir, "stiker"))
            sfx_files = sfx.siapkan_sfx(os.path.join(tmp_dir, "sfx"))
            data = {"idx": idx, "m": m, "mulai": mulai, "selesai": selesai,
                    "seg": seg, "srt": srt, "facecam": facecam,
                    "tmp_dir": tmp_dir, "frames": frames, "durasi": durasi,
                    "srt_entries": srt_entries, "jadwal_auto": jadwal_auto,
                    "stiker_files": stiker_files, "sfx_files": sfx_files}
            self.antrian_ui.put(lambda d=data: self._buka_studio(d))
        except Exception as e:  # noqa: BLE001 - tampilkan ke user
            log("Studio gagal disiapkan: %s" % e)
            self._set_status("Gagal: %s" % str(e)[:100])
        finally:
            self.sedang_jalan = False
            self.tombol_cari.configure(state="normal")
            if self.momen_list:
                self.tombol_buat.configure(state="normal")
                self.tombol_preview.configure(state="normal")

    def _buka_studio(self, d):
        """Buka jendela Studio Preview (thread utama)."""
        if self._studio is not None:
            try:
                self._studio.destroy()
            except tk.TclError:
                pass
            self._studio = None
        if self._studio_tmp:
            shutil.rmtree(self._studio_tmp, ignore_errors=True)
        self._studio_tmp = d["tmp_dir"]
        edits = self.edit_manual.setdefault(d["idx"], [])
        self._studio = preview.StudioPreview(
            self, judul=d["m"].get("title_id") or "Momen",
            frames=d["frames"], durasi=d["durasi"], facecam=d["facecam"],
            srt_entries=d["srt_entries"], jadwal_auto=d["jadwal_auto"],
            stiker_files=d["stiker_files"], sfx_files=d["sfx_files"],
            edits=edits,
            on_render=lambda ed: self._render_dari_studio(d, ed),
            on_tutup=self._tutup_studio, log=self.log)
        self._set_status(
            "Studio Preview terbuka — play, tambah stiker/sound, lalu Render.")

    def _tutup_studio(self):
        """Studio ditutup tanpa render — bersihkan file sementara."""
        self._studio = None
        if self._studio_tmp:
            shutil.rmtree(self._studio_tmp, ignore_errors=True)
            self._studio_tmp = None

    def _render_dari_studio(self, d, edits):
        """Render penuh momen itu dengan edit manual dari timeline."""
        if self._studio is not None:
            try:
                self._studio.destroy()
            except tk.TclError:
                pass
            self._studio = None
        self.sedang_jalan = True
        self.tombol_cari.configure(state="disabled")
        self.tombol_preview.configure(state="disabled")
        self.tombol_buat.configure(state="disabled")
        self._set_status("Merender clip dari Studio Preview...")
        threading.Thread(target=self._render_studio_thread, args=(d, edits),
                         daemon=True).start()

    def _render_studio_thread(self, d, edits):
        log = self.log
        tmp_dir = d["tmp_dir"]
        try:
            meta = self.meta_saat_ini or {}
            slug = self.slug_saat_ini or slug_dari_judul(
                meta.get("title") or "", meta.get("id") or "video")
            out_dir = self.output_var.get().strip() or "output"
            os.makedirs(out_dir, exist_ok=True)
            clip = self._proses_satu_momen(
                d["idx"], d["m"], self.url_var.get().strip(), d["facecam"],
                out_dir, tmp_dir, slug, log=log,
                seg_path=d["seg"], srt_path=d["srt"], edit_manual=edits)
            if clip:
                log("SELESAI (dari Studio): %s" % clip)
                self._set_status("Selesai: %s" % clip)
            else:
                self._set_status("Render gagal — lihat log.")
        except Exception as e:  # noqa: BLE001 - tampilkan ke user
            log("BERHENTI: %s" % e)
            self._set_status("Gagal: %s" % str(e)[:100])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if self._studio_tmp == tmp_dir:
                self._studio_tmp = None
            self.sedang_jalan = False
            self.tombol_cari.configure(state="normal")
            if self.momen_list:
                self.tombol_buat.configure(state="normal")
                self.tombol_preview.configure(state="normal")

    def _buka_file(self, path):
        """Buka file video di player default sistem."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606 - path dari output user sendiri
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as e:  # noqa: BLE001 - preview tetap bisa dibuka manual
            self.log("  (Tidak bisa membuka player otomatis: %s — buka manual: %s)"
                     % (e, path))


if __name__ == "__main__":
    App().mainloop()
