@echo off
setlocal
cd /d "%~dp0"
title Portal BPK Kaltim
if exist ".venv\Scripts\python.exe" goto deps
where py >nul 2>nul
if %errorlevel% equ 0 (
 py -3 -m venv .venv
) else (
 python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
 echo Python belum tersedia. Pasang Python 3.11 atau lebih baru dan aktifkan Add Python to PATH.
 echo Untuk melihat rancangan tanpa instalasi, buka Pratinjau_BPK_Kaltim.html.
 pause
 exit /b 1
)
:deps
if exist ".venv\bpk-dependencies-ready" goto run
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
 echo Instalasi paket belum berhasil. Pastikan internet aktif dan jalankan kembali file ini.
 pause
 exit /b 1
)
echo ok> ".venv\bpk-dependencies-ready"
:run
".venv\Scripts\python.exe" ambil_logo.py
start "BPK Browser" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" server.py
pause
