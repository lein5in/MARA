@echo off
:: ─── MARA Auto-Launch ────────────────────────────────────────────────────────
:: Délai 10s pour laisser Windows finir de démarrer
timeout /t 10 /nobreak > nul

:: Activation venv + lancement MARA
cd /d "C:\Users\Admin\Documents\MARA"
call venv\Scripts\activate.bat
python main.py
pause 