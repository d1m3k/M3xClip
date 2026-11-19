"""Program Monitor v1.5 — panel preview video di dalam jendela utama,
ala Program Monitor di Premiere / preview di CapCut / Composition panel.

Panel ini SELALU terlihat di sebelah kiri jendela utama (bukan jendela
pop-up): video preview yang bisa di-play, timeline untuk nambah stiker
lucu / sound effect di detik yang dipilih, lalu render.

Cara kerja (tanpa dependency baru — cuma ffmpeg + PIL yang sudah dipakai):
- Saat momen dimuat ke monitor (tombol ▶ Lihat di momen, atau 👁 Preview),
  segmen diekstrak jadi strip frame (5 fps, sekali jalan). Playback
  tinggal menampilkan gambar — ringan & stabil.
- Tiap frame yang ditampilkan di-layout ulang dengan PIL persis seperti
  hasil render (gameplay atas, facecam bawah), lalu subtitle & stiker
  digambar di atasnya. Jadi yang terlihat = yang akan di-render.
- Timeline: canvas dengan marker subtitle (abu-abu), SFX (bulat oranye),
  stiker (kotak biru), dan garis playhead merah. Klik timeline = lompat.
- Sound ikut bunyi saat playback melewati detiknya (Windows: winsound).
"""

import glob
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

import assembler
import sfx
import stickers

FPS_STRIP = 5
LEBAR_TAMPIL = 270
TINGGI_TAMPIL = 480


def ekstrak_strip(seg_path, tmp_dir, fps=FPS_STRIP, lebar=480):
    """Ekstrak segmen jadi strip frame JPG (sekali jalan, untuk playback).
    Kembalikan (daftar_frame, durasi): daftar_frame = [(waktu, path)]."""
    os.makedirs(tmp_dir, exist_ok=True)
    pola = os.path.join(tmp_dir, "frame_%04d.jpg")
    cmd = [assembler.find_ffmpeg(), "-y", "-v", "error",
           "-i", seg_path,
           "-vf", "fps=%d,scale=%d:-2" % (fps, lebar),
           "-q:v", "3", pola]
    hasil = subprocess.run(cmd, capture_output=True, text=True)
    if hasil.returncode != 0:
        raise RuntimeError("gagal mengekstrak frame preview: %s"
                           % hasil.stderr.strip().splitlines()[-1:])
    durasi = assembler.probe_video(seg_path)["duration"]
    berkas = sorted(glob.glob(os.path.join(tmp_dir, "frame_*.jpg")))
    return [(i / fps, p) for i, p in enumerate(berkas)], durasi


def _cover(img, ukuran):
    """Resize cover (isi penuh) lalu crop tengah ke ukuran."""
    tw, th = ukuran
    w, h = img.size
    skala = max(tw / w, th / h)
    img2 = img.resize((max(1, round(w * skala)), max(1, round(h * skala))),
                      Image.LANCZOS)
    x = (img2.width - tw) // 2
    y = (img2.height - th) // 2
    return img2.crop((x, y, x + tw, y + th))


def layout_frame(frame_path, facecam, lebar_tampil=LEBAR_TAMPIL,
                 tinggi_tampil=TINGGI_TAMPIL):
    """Ubah 1 frame segmen 16:9 jadi layout clip vertikal (gameplay atas,
    facecam bawah) — rumus crop sama seperti assembler, tapi dengan PIL."""
    img = Image.open(frame_path).convert("RGB")
    W, H = img.size
    paruh = tinggi_tampil // 2
    g = assembler.hitung_crop_gameplay(W, H, facecam)
    atas = _cover(img.crop((g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"])),
                  (lebar_tampil, paruh))
    fx = max(0, int(facecam["x"] * W))
    fy = max(0, int(facecam["y"] * H))
    fw = max(1, int(facecam["w"] * W))
    fh = max(1, int(facecam["h"] * H))
    fw = min(fw, W - fx)
    fh = min(fh, H - fy)
    bawah = _cover(img.crop((fx, fy, fx + fw, fy + fh)),
                   (lebar_tampil, paruh))
    out = Image.new("RGB", (lebar_tampil, tinggi_tampil))
    out.paste(atas, (0, 0))
    out.paste(bawah, (0, paruh))
    return out


def _bungkus(teks, font, lebar_max, maks_baris=2):
    """Bungkus teks per kata supaya muat lebar_max, maksimal maks_baris."""
    kata = teks.split()
    baris, saat_ini = [], ""
    for k in kata:
        coba = (saat_ini + " " + k).strip()
        if font.getlength(coba) <= lebar_max:
            saat_ini = coba
        else:
            if saat_ini:
                baris.append(saat_ini)
            saat_ini = k
            if len(baris) >= maks_baris:
                break
    if saat_ini and len(baris) < maks_baris:
        baris.append(saat_ini)
    return baris


def komposit(img_layout, teks_sub, stiker_aktif):
    """Gambar subtitle + stiker di atas layout. stiker_aktif = list path PNG.
    Kembalikan PIL Image baru (yang asli tidak diubah)."""
    img = img_layout.copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size
    paruh = H // 2
    # Stiker: pojok kanan atas gameplay.
    ukuran_stiker = W // 4
    for path in stiker_aktif:
        try:
            st = Image.open(path).convert("RGBA").resize(
                (ukuran_stiker, ukuran_stiker), Image.LANCZOS)
        except OSError:
            continue
        img.paste(st, (W - ukuran_stiker - 8, 8), st)
    # Subtitle: kuning outline hitam, bawah gameplay (gaya render).
    # Ukuran font proporsional dengan lebar (W//22 ~ sama dengan render
    # 47 px di lebar 1080), supaya bungkusan barisnya sama.
    if teks_sub:
        font = stickers._font_bold(max(11, W // 22))
        baris = _bungkus(teks_sub, font, W - 16)
        tinggi_baris = font.size + 4
        total = len(baris) * tinggi_baris
        y = paruh - 12 - total
        for b in baris:
            x = (W - font.getlength(b)) / 2
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    if dx or dy:
                        draw.text((x + dx, y + dy), b, font=font, fill="#111111")
            draw.text((x, y), b, font=font, fill="#FFFF00")
            y += tinggi_baris
    return img


def mainkan_wav(path):
    """Bunyikan file WAV (Windows saja — di Linux dilewati)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


class MonitorPanel(ttk.Frame):
    """Panel Program Monitor: video preview + timeline + tambah stiker/sound.
    Selalu menempel di jendela utama; dimuat lewat muat(data)."""

    def __init__(self, master, *, on_render, log):
        super().__init__(master)
        self.on_render = on_render  # dipanggil (data, edits) saat Render
        self.log = log
        self.lebar_timeline = 280
        self.frames = []  # [(waktu, path)]
        self.durasi = 0.0
        self.facecam = None
        self.srt_entries = []  # [(mulai, selesai, teks)]
        self.jadwal_auto = []  # [{waktu, jenis, stiker, sampai}]
        self.stiker_files = {}  # {teks: path}
        self.sfx_files = {}  # {jenis: path}
        self.edits = []  # list edit manual (ditulis ke app.edit_manual)
        self.data = None  # data momen yang sedang dimuat
        self.waktu = 0.0
        self.mutar = False
        self._foto = None
        self._terakhir_sfx = -1.0

        ttk.Label(self, text="PROGRAM MONITOR",
                  font=("", 10, "bold")).pack(anchor="w", padx=6, pady=(4, 0))
        self.label_momen = ttk.Label(self, text="Belum ada momen.",
                                     foreground="gray", wraplength=280)
        self.label_momen.pack(anchor="w", padx=6)

        # --- Video ---
        self.label_video = ttk.Label(
            self, text="Klik ▶ Lihat di momen,\natau 👁 Preview.",
            foreground="gray", justify="center")
        self.label_video.pack(pady=(6, 4))

        # --- Kontrol play + slider ---
        frame_kontrol = ttk.Frame(self)
        frame_kontrol.pack(fill="x", padx=6)
        self.tombol_play = ttk.Button(frame_kontrol, text="▶  Play",
                                      command=self._toggle_play, width=9)
        self.tombol_play.pack(side="left")
        self.label_waktu = ttk.Label(frame_kontrol, text="00:00 / 00:00")
        self.label_waktu.pack(side="left", padx=6)
        self.skala = tk.Scale(frame_kontrol, from_=0, to=1,
                              resolution=0.1, orient="horizontal",
                              showvalue=False, command=self._geser_skala,
                              length=110)
        self.skala.pack(side="left", fill="x", expand=True)

        # --- Timeline ---
        ttk.Label(self, text="Timeline — klik untuk lompat ke detik itu",
                  foreground="gray").pack(anchor="w", padx=6, pady=(6, 0))
        self.canvas = tk.Canvas(self, width=self.lebar_timeline, height=64,
                                bg="white", highlightthickness=1,
                                highlightbackground="#cccccc")
        self.canvas.pack(padx=6, pady=2)
        self.canvas.bind("<Button-1>", self._klik_timeline)

        # --- Tambah stiker / sound di posisi playhead ---
        frame_tambah = ttk.LabelFrame(self, text="Tambah di posisi playhead")
        frame_tambah.pack(fill="x", padx=6, pady=6)
        ttk.Label(frame_tambah, text="Stiker:").grid(
            row=0, column=0, sticky="w", padx=4, pady=4)
        self.stiker_var = tk.StringVar(value="HAHA!")
        ttk.Combobox(frame_tambah, textvariable=self.stiker_var,
                     values=["HAHA!", "WOW!", "KOCAK!"],
                     state="readonly", width=8).grid(
                         row=0, column=1, padx=2, pady=4)
        ttk.Button(frame_tambah, text="＋ Stiker di sini",
                   command=self._tambah_stiker).grid(
                       row=0, column=2, padx=4, pady=4)
        ttk.Label(frame_tambah, text="Sound:").grid(
            row=1, column=0, sticky="w", padx=4, pady=4)
        self.sfx_var = tk.StringVar(value="ding")
        ttk.Combobox(frame_tambah, textvariable=self.sfx_var,
                     values=["pop", "boing", "ding"],
                     state="readonly", width=8).grid(
                         row=1, column=1, padx=2, pady=4)
        ttk.Button(frame_tambah, text="＋ Sound di sini",
                   command=self._tambah_sfx).grid(
                       row=1, column=2, padx=4, pady=4)

        # --- Daftar edit manual ---
        ttk.Label(self, text="Edit manual di timeline ini:",
                  foreground="gray").pack(anchor="w", padx=6)
        self.list_edits = tk.Listbox(self, height=4, width=38)
        self.list_edits.pack(fill="x", padx=6, pady=2)
        ttk.Button(self, text="Hapus edit yang dipilih",
                   command=self._hapus_edit).pack(anchor="w", padx=6)

        # --- Render ---
        ttk.Button(self, text="✓  Render clip ini",
                   command=self._klik_render).pack(
                       fill="x", padx=6, pady=10)
        self._gambar_timeline()

    # ------------------------------------------------------------------
    # Muat momen
    # ------------------------------------------------------------------
    def muat(self, data):
        """Muat 1 momen ke monitor (dipanggil dari thread utama)."""
        self.mutar = False
        self.tombol_play.configure(text="▶  Play")
        self.data = data
        self.frames = data["frames"]
        self.durasi = data["durasi"]
        self.facecam = data["facecam"]
        self.srt_entries = data["srt_entries"]
        self.jadwal_auto = data["jadwal_auto"]
        self.stiker_files = data["stiker_files"]
        self.sfx_files = data["sfx_files"]
        self.edits = data["edits"]
        self.waktu = 0.0
        self._terakhir_sfx = -1.0
        self.skala.configure(to=max(1, self.durasi))
        self.skala.set(0)
        self.label_momen.configure(text=data["m"].get("title_id") or "Momen")
        self._tampilkan_frame()
        self._gambar_timeline()
        self._segarkan_daftar()

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def _frame_pada(self, waktu):
        """Frame strip terdekat (ke belakang) untuk detik tertentu."""
        pilih = self.frames[0][1] if self.frames else None
        for t, p in self.frames:
            if t <= waktu:
                pilih = p
            else:
                break
        return pilih

    def _teks_pada(self, waktu):
        """Semua baris subtitle yang aktif di detik itu (auto-sub YouTube
        sering tumpang tindih — semuanya tampil, seperti di render)."""
        aktif = [teks for mulai, selesai, teks in self.srt_entries
                 if mulai <= waktu <= selesai]
        return " ".join(aktif)

    def _stiker_aktif(self, waktu):
        """Path stiker yang sedang tampil di detik ini (auto + manual)."""
        aktif = []
        for j in self.jadwal_auto:
            if j.get("stiker") and j["waktu"] <= waktu <= j.get("sampai", j["waktu"] + 2.0):
                aktif.append(self.stiker_files.get(j["stiker"]))
        for e in self.edits:
            if e["kind"] == "stiker" and e["waktu"] <= waktu <= e.get("sampai", e["waktu"] + 2.0):
                aktif.append(self.stiker_files.get(e["nilai"]))
        return [p for p in aktif if p]

    def _tampilkan_frame(self):
        if not self.frames or not self.facecam:
            return
        path = self._frame_pada(self.waktu)
        if not path:
            return
        layout = layout_frame(path, self.facecam)
        gambar = komposit(layout, self._teks_pada(self.waktu),
                          self._stiker_aktif(self.waktu))
        self._foto = ImageTk.PhotoImage(gambar)
        self.label_video.configure(image=self._foto)
        self.label_waktu.configure(
            text="%s / %s" % (_fmt(self.waktu), _fmt(self.durasi)))
        self._gambar_timeline()

    def _langkah(self):
        if not self.mutar or not self.frames:
            return
        baru = self.waktu + 0.2
        if baru >= self.durasi:
            self.waktu = self.durasi
            self.mutar = False
            self.tombol_play.configure(text="▶  Play")
        else:
            self.waktu = baru
            self.after(200, self._langkah)
        self._cek_sfx(self.waktu)
        self.skala.set(self.waktu)
        self._tampilkan_frame()

    def _cek_sfx(self, waktu):
        """Bunyikan SFX yang terlewati playhead (auto + manual)."""
        semua = ([{"waktu": j["waktu"], "jenis": j["jenis"]}
                  for j in self.jadwal_auto if j.get("jenis")] +
                 [{"waktu": e["waktu"], "jenis": e["nilai"]}
                  for e in self.edits if e["kind"] == "sfx"])
        for item in semua:
            if self._terakhir_sfx < item["waktu"] <= waktu:
                p = self.sfx_files.get(item["jenis"])
                if p:
                    mainkan_wav(p)
        self._terakhir_sfx = waktu

    def _toggle_play(self):
        if not self.frames:
            return
        if self.mutar:
            self.mutar = False
            self.tombol_play.configure(text="▶  Play")
        else:
            if self.waktu >= self.durasi:
                self.waktu = 0.0
                self._terakhir_sfx = -1.0
            self.mutar = True
            self.tombol_play.configure(text="⏸  Pause")
            self.after(200, self._langkah)

    def _geser_skala(self, nilai):
        if not self.frames:
            return
        self.waktu = float(nilai)
        self._terakhir_sfx = self.waktu
        self._tampilkan_frame()

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------
    def _x_waktu(self, waktu):
        return 8 + (waktu / max(1, self.durasi)) * (self.lebar_timeline - 16)

    def _gambar_timeline(self):
        c = self.canvas
        c.delete("all")
        if self.durasi <= 0:
            return
        # Bar dasar
        c.create_rectangle(8, 28, self.lebar_timeline - 8, 36, fill="#eeeeee",
                           outline="#cccccc")
        # Subtitle: tick abu-abu
        for mulai, selesai, _teks in self.srt_entries:
            x = self._x_waktu(mulai)
            c.create_line(x, 22, x, 42, fill="#999999")
        # SFX auto: bulat oranye; stiker auto: kotak biru muda
        for j in self.jadwal_auto:
            x = self._x_waktu(j["waktu"])
            if j.get("jenis"):
                c.create_oval(x - 5, 8, x + 5, 18, fill="#F59E0B",
                              outline="#92400E")
            if j.get("stiker"):
                c.create_rectangle(x - 5, 46, x + 5, 56, fill="#93C5FD",
                                   outline="#1D4ED8")
        # Edit manual: penanda lebih tebal
        for e in self.edits:
            x = self._x_waktu(e["waktu"])
            if e["kind"] == "sfx":
                c.create_oval(x - 6, 7, x + 6, 19, fill="#EA580C",
                              outline="#7C2D12", width=2)
            else:
                c.create_rectangle(x - 6, 45, x + 6, 57, fill="#2563EB",
                                   outline="#1E3A8A", width=2)
        # Playhead merah
        x = self._x_waktu(self.waktu)
        c.create_line(x, 4, x, 60, fill="#DC2626", width=2)

    def _klik_timeline(self, event):
        if self.durasi <= 0 or not self.frames:
            return
        self.waktu = max(0.0, min(self.durasi,
                                  (event.x - 8) / (self.lebar_timeline - 16) * self.durasi))
        self._terakhir_sfx = self.waktu
        self.skala.set(self.waktu)
        self._tampilkan_frame()

    # ------------------------------------------------------------------
    # Tambah / hapus edit manual
    # ------------------------------------------------------------------
    def _tambah_stiker(self):
        if not self.frames:
            return
        teks = self.stiker_var.get()
        self.edits.append({"waktu": round(self.waktu, 2), "kind": "stiker",
                           "nilai": teks, "sampai": round(self.waktu + 2.0, 2)})
        self.log("  Monitor: stiker %s ditambah di %.1f detik."
                 % (teks, self.waktu))
        self._segarkan_daftar()
        self._tampilkan_frame()

    def _tambah_sfx(self):
        if not self.frames:
            return
        jenis = self.sfx_var.get()
        self.edits.append({"waktu": round(self.waktu, 2), "kind": "sfx",
                           "nilai": jenis})
        self.log("  Monitor: sound %s ditambah di %.1f detik."
                 % (jenis, self.waktu))
        self._segarkan_daftar()
        self._tampilkan_frame()

    def _segarkan_daftar(self):
        self.list_edits.delete(0, "end")
        for e in sorted(self.edits, key=lambda x: x["waktu"]):
            if e["kind"] == "stiker":
                self.list_edits.insert(
                    "end", "%.1f dtk  STIKER %s" % (e["waktu"], e["nilai"]))
            else:
                self.list_edits.insert(
                    "end", "%.1f dtk  SOUND %s" % (e["waktu"], e["nilai"]))

    def _hapus_edit(self):
        pilih = self.list_edits.curselection()
        if not pilih:
            return
        teks = self.list_edits.get(pilih[0])
        # Cari entri yang cocok dengan baris yang dipilih (urut waktu).
        urut = sorted(self.edits, key=lambda x: x["waktu"])
        target = urut[pilih[0]]
        self.edits.remove(target)
        self.log("  Monitor: edit dihapus (%s)." % teks)
        self._segarkan_daftar()
        self._tampilkan_frame()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _klik_render(self):
        if not self.data:
            return
        self.mutar = False
        self.on_render(self.data, list(self.edits))


def _fmt(detik):
    detik = int(detik)
    return "%02d:%02d" % (detik // 60, detik % 60)
