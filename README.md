# M3xClip — Clip Generator Reels/Shorts v1

Program Python portabel (.exe) untuk membuat clip vertikal dari VOD YouTube.
Kirim link VOD live streamer → Gemini nonton videonya lewat URL langsung
(tanpa download VOD utuh) → cari momen hype → download potongan itu saja →
rakit vertikal 1080x1920 (gameplay atas, facecam bawah) → subtitle
Indonesia/Inggris → thumbnail dari frame momen itu.

> **Catatan Content ID:** Speed, Windah Basudara, dan Kai Cenat secara
> terbuka mengizinkan viewer nge-clip ("kita sama-sama untung"). Izin itu
> TIDAK mematikan Content ID — klaim bisa saja terjadi (pendapatan lari
> ke streamer), itu normal. Yang bikin channel clip aman = editing
> transformatif (subtitle, layout, hook, thumbnail), BUKAN upload
> mentahan panjang.

---

## Yang dibutuhkan

- **Windows 10/11** (untuk .exe) atau **Linux/Mac** (jalan dari source)
- **Python 3.12** (kalau jalan dari source / build sendiri)
- **ffmpeg** — wajib. Untuk .exe: download dari
  https://www.gyan.dev/ffmpeg/builds/ (pilih `ffmpeg-release-essentials.zip`),
  copy `ffmpeg.exe` ke folder `tools/` sebelum build, atau install ffmpeg
  ke PATH Windows.
- **API key Gemini** — gratis, lihat bawah.

## Mendapatkan API key Gemini (gratis)

1. Buka https://aistudio.google.com/apikey (login akun Google biasa).
2. Klik **Create API key** → copy key-nya.
3. Di program M3xClip: tempel di kolom **API key Gemini**, klik **Simpan**.
4. Key disimpan di `config.json` di samping program — **jangan kirim file
   itu ke siapa pun, jangan kirim key lewat chat.**
5. Klik **Tes Koneksi** untuk memastikan key jalan.

> Google AI Pro **TIDAK SAMA** dengan billing API. Program ini jalan di
> **API Free Tier**. Analisis video via URL YouTube masih gratis (preview,
> jatah **8 jam video/hari**). Kalau jatah habis, tunggu reset besok.

## Menjalankan dari source

```bat
run.bat
```

(Buat venv otomatis, install dependensi, buka GUI.)

## Build .exe (Windows)

```bat
build.bat
```

Hasil: `dist\M3xClip.exe` — satu file, tinggal klik dua kali.
Kalau `tools\ffmpeg.exe` ada saat build, ffmpeg ikut dibundel ke dalam .exe.
Kalau tidak ada, .exe tetap jalan asal ffmpeg terinstall di PATH.

## Build otomatis via GitHub Actions (rute A, rekomendasi)

1. Push repo ini ke GitHub.
2. File `workflow-build.yml` (di root repo) di-copy isinya ke
   `.github/workflows/build.yml` **lewat web UI GitHub** (konektor tidak
   bisa push folder `.github/`).
3. Setiap push ke `main`, Actions otomatis build .exe → download di tab
   **Actions → Artifacts → M3xClip-windows**.

## Cara pakai

1. Tempel **URL YouTube** VOD-nya (contoh: `https://www.youtube.com/live/VIDEO_ID`).
2. Pilih **preset streamer** (Windah Basudara / IShowSpeed / Kai Cenat).
   - Windah sudah **terverifikasi** dari frame video asli (facecam kanan bawah).
   - Speed & Kai masih **default kanan bawah, belum terverifikasi** — kalau
     hasil clip-nya facecam kepotong, pilih **Custom** dan isi koordinat
     sendiri (x, y, w, h relatif 0.0–1.0, lihat frame video).
3. Isi **API key** (sekali saja, tersimpan di `config.json`).
4. Atur **jumlah momen** (default 3) dan **durasi clip** (default 30–60 detik).
5. Pilih **folder output**, klik **🔍 Cari Momen** — Gemini menonton video
   lalu menampilkan daftar rekomendasi (judul, jam mulai–selesai, durasi,
   alasan). **Centang** momen yang mau dipakai.
   **Klip manual (v1.4, alternatif tanpa Gemini/API key):** kalau kamu
   sudah tahu mau potong jam berapa, isi **Mulai** + **Selesai** di kotak
   "Klip manual" (format MM:SS atau detik, mis. 08:51–09:26) + **Judul**,
   klik **＋ Tambah sebagai momen** — momen itu masuk ke daftar yang
   sama, bisa di-preview di Studio atau langsung dibuat clip. Durasi
   5–180 detik (batas YouTube Shorts). Momen manual ikut terhapus kalau
   Cari Momen dijalankan lagi.
6. **Edit tipis** (sebelum render): atur ukuran subtitle (Kecil/Sedang/Besar),
   Sound (Mati/Minimal/Ramai) dan Stiker (Mati/Otomatis); geser trim
   mulai/selesai tiap momen kalau mau.
7. **Program Monitor (v1.5)** — panel preview di sebelah kiri jendela
   utama (selalu terlihat, ala Program Monitor di Premiere / preview di
   CapCut): klik **▶ Lihat di Monitor** di tiap momen, atau **👁 Preview**
   untuk momen pertama yang dicentang. Videonya bisa di-play, ada
   slider + **timeline** (klik untuk lompat), tambah stiker lucu
   (HAHA!/WOW!/KOCAK!) atau sound effect (pop/boing/ding) di detik
   yang dipilih, lalu **✓ Render clip ini**. Edit manual dari timeline
   ikut masuk ke hasil render (juga berlaku kalau nanti klik Buat Clip).
   Monitor tetap bisa dipakai sesudah render.
8. Atau langsung klik **✂️ Buat Clip yang Dipilih** untuk render penuh
   tanpa preview. Untuk tiap momen yang dicentang, yt-dlp download
   **hanya durasi momen itu** dari URL (bukan VOD utuh), lalu clip
   dirakit + thumbnail dibuat. Pantau log.
9. Hasil: `{slug}_clip1.mp4`, `{slug}_clip2.mp4`, … + `{slug}_thumb1.jpg`, …

**Gaya clip (v1.2, ala Short referensi):** subtitle kecil kuning ber-outline
hitam di bawah area gameplay (tidak menutupi gameplay maupun facecam);
sound effect (pop di awal, boing/ding di baris berk kata kocak seperti
wkwk, haha, anjir, wow) + stiker bintang (HAHA! / WOW! / KOCAK!) di pojok
kanan atas gameplay selama ~2 detik. Semua SFX & stiker dibuat sendiri
oleh program (ffmpeg + PIL), tanpa file eksternal.

Catatan: kalau satu model Gemini sedang overload (503) atau kuotanya habis
(429), program otomatis pindah ke model lain (3.8-flash → 3.5-flash-lite →
3.5-flash → 2.5-flash). Kalau semua model gagal, tunggu sebentar lalu coba lagi.

## Troubleshooting

| Masalah | Penyebab / solusi |
|---|---|
| `API key belum diisi` | Isi key di GUI, klik Simpan. Key dibuat di AI Studio, bukan dikirim ke siapa pun. |
| `Koneksi gagal` / 400 | Key salah / belum aktif. Cek di AI Studio, buat key baru. |
| `Kuota habis` (429) | Free tier model itu habis. Program otomatis pindah ke model lain; kalau semua model habis, tunggu reset besok. |
| Video tidak ada subtitle | Video itu tidak punya auto-subtitle. Clip tetap jadi, tanpa subtitle. (Rencana: subtitle via Whisper, opsional.) |
| VOD privat / dihapus | yt-dlp tidak bisa akses. Pakai VOD publik. |
| `ffmpeg tidak ditemukan` | Install ffmpeg ke PATH, atau taruh `ffmpeg.exe` di folder `tools/`. |
| Facecam kepotong / salah posisi | Preset Speed/Kai belum terverifikasi. Lihat satu frame video, ukur posisi facecam, isi lewat preset **Custom**. |
| Clip gelap / aneh | Cek dulu clip tes di folder output. Laporkan beserta screenshot frame aslinya. |

## Rencana v1.1 (opsional, belum dibangun)

- Subtitle via Whisper lokal (kalau video tidak punya auto-subtitle).
- Preset facecam Speed & Kai terverifikasi dari frame asli.
- Bot Telegram private (Fase 2): kirim link, bot kirim balik clip + thumbnail.
