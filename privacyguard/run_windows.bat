@echo off
echo ===================================
echo  PrivacyGuard — Startup
echo ===================================
echo.
echo  Checking Tesseract installation...
where tesseract >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: Tesseract OCR not found on PATH!
    echo  Download and install from:
    echo  https://github.com/UB-Mannheim/tesseract/wiki
    echo  Then add it to your PATH and restart.
    echo.
    pause
)
echo  Installing Python packages...
pip install flask flask-sqlalchemy werkzeug pytesseract pillow --quiet
echo.
echo  Starting server at http://127.0.0.1:5000
echo  Press Ctrl+C to stop.
echo.
python app.py
pause
