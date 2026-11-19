@echo off
REM M3xClip — build .exe portabel dengan PyInstaller (Windows)
REM Hasil: dist\M3xClip.exe (satu file, tinggal klik dua kali).
REM
REM ffmpeg: kalau ada tools\ffmpeg.exe, ikut dibundel ke dalam .exe.
REM Kalau belum ada, download dulu dari https://www.gyan.dev/ffmpeg/builds/
REM (pilih "ffmpeg-release-essentials.zip"), lalu copy ffmpeg.exe ke folder tools\.
REM Kalau tidak dibundel, .exe tetap jalan ASAL ffmpeg terinstall di PATH Windows.
chcp 65001 >nul
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
  echo Python tidak ditemukan. Install Python 3.12 dari python.org dulu.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller

set "FFMPEG_ARG="
if exist tools\ffmpeg.exe (
  echo ffmpeg ditemukan di tools\ — akan dibundel ke dalam .exe.
  set "FFMPEG_ARG=--add-binary tools\ffmpeg.exe;."
) else (
  echo CATATAN: tools\ffmpeg.exe tidak ada — .exe nanti butuh ffmpeg di PATH.
)

.venv\Scripts\pyinstaller.exe --onefile --windowed --name M3xClip %FFMPEG_ARG% main.py

echo.
echo SELESAI. File .exe ada di: dist\M3xClip.exe
echo config.json dibuat otomatis di samping .exe saat pertama simpan API key.
pause
