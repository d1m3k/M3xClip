@echo off
REM M3xClip — jalankan dari source (Windows)
REM Buat venv otomatis kalau belum ada, install dependensi, lalu buka GUI.
chcp 65001 >nul
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
  echo Python tidak ditemukan. Install Python 3.12 dari python.org dulu,
  echo lalu centang "Add python.exe to PATH" saat install.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Membuat virtual environment...
  python -m venv .venv
)

echo Menginstall dependensi (sekali saja, selanjutnya dilewati)...
.venv\Scripts\python.exe -m pip install -q -r requirements.txt

echo Menjalankan M3xClip...
.venv\Scripts\python.exe main.py
pause
