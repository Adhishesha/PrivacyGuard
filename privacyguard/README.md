# PrivacyGuard — Student Data Privacy Tool v3

## Quick Start (No API key needed!)

### 1. Install dependencies
```
pip install flask flask-sqlalchemy werkzeug
```

### 2. Run the app

**Windows — double-click `run_windows.bat`**  
or in Command Prompt:
```
python app.py
```

**Mac / Linux:**
```
python app.py
```

### 3. Open browser
```
http://127.0.0.1:5000
```

### 4. Default admin login
- **Username:** `admin`
- **Password:** `admin123`

---

## Features
- **OCR Document Scanner** — FREE, no API key! Uses Tesseract.js in your browser
- **Account Switcher** — switch between student/faculty/admin without logging out
- **Consent Management** — students approve or deny data-sharing requests
- **Download Report** — export all personal data + scan history as .txt
- **Admin Panel** — view all users, requests, and audit logs

## OCR Scanner
The scanner uses Tesseract.js — an open-source OCR engine that runs entirely
in your browser. No data is sent to any external server. Works offline after
the first load (engine is cached by your browser).

Supported formats: JPG, PNG, WEBP, BMP, GIF
