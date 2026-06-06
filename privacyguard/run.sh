#!/bin/bash
echo "==================================="
echo " PrivacyGuard — Startup"
echo "==================================="
if ! command -v tesseract &>/dev/null; then
  echo " Installing Tesseract..."
  sudo apt-get install -y tesseract-ocr 2>/dev/null || brew install tesseract 2>/dev/null
fi
pip install flask flask-sqlalchemy werkzeug pytesseract pillow -q
echo " Starting server at http://127.0.0.1:5000"
python app.py
