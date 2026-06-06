"""routes/student.py — Server-side OCR via pytesseract, with full error handling"""
import json, os, re, io, base64, traceback
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request, jsonify, send_file, abort)
from database import db
from models import Student, ShareRequest, ConsentLog, ScanHistory, ScanRequest
from functools import wraps

student_bp = Blueprint('student', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SENSITIVE_KEYS = {'phone','mobile','address','dob','date of birth','birth date',
                  'father','mother','guardian','aadhaar','pan','passport',
                  'id number','roll number','student id','blood'}

def is_sensitive(key):
    return any(s in key.lower() for s in SENSITIVE_KEYS)

# ── Tesseract auto-detect ─────────────────────────────────────────────────────
def _get_tesseract():
    """Returns (pytesseract_module, error_string_or_None)"""
    import glob
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return pytesseract, None
    except Exception:
        pass

    win_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\tesseract\tesseract.exe',
    ]
    for pat in [r'C:\Program Files*\Tesseract*\tesseract.exe',
                r'C:\Users\*\AppData\Local\*Tesseract*\tesseract.exe']:
        try:
            win_paths.extend(glob.glob(pat))
        except Exception:
            pass

    try:
        import pytesseract
        for path in win_paths:
            if os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                try:
                    pytesseract.get_tesseract_version()
                    return pytesseract, None
                except Exception:
                    continue
    except ImportError:
        pass

    return None, (
        "Tesseract OCR is not installed on this computer.\n"
        "Download from: https://github.com/UB-Mannheim/tesseract/wiki\n"
        "Install the .exe, then restart python app.py"
    )

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('student', 'admin'):
            flash('Student login required.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

# ── Dashboard ─────────────────────────────────────────────────────────────────
@student_bp.route('/dashboard')
@student_required
def dashboard():
    student   = Student.query.get(session['student_id'])
    pending   = ShareRequest.query.filter_by(student_id=student.id, status='pending').all()
    history   = ConsentLog.query.filter_by(student_id=student.id)\
                                .order_by(ConsentLog.decided_at.desc()).limit(10).all()
    scans     = ScanHistory.query.filter_by(student_id=student.id)\
                                 .order_by(ScanHistory.scanned_at.desc()).limit(5).all()
    scan_reqs = ScanRequest.query.filter_by(student_id=student.id)\
                                 .order_by(ScanRequest.requested_at.desc()).limit(5).all()
    return render_template('student/dashboard.html', student=student,
                           pending=pending, history=history,
                           scans=scans, scan_reqs=scan_reqs)

# ── Profile ───────────────────────────────────────────────────────────────────
@student_bp.route('/profile')
@student_required
def profile():
    return render_template('student/profile.html',
                           student=Student.query.get(session['student_id']))

# ── Consent ───────────────────────────────────────────────────────────────────
@student_bp.route('/consent/<int:request_id>/<decision>')
@student_required
def consent(request_id, decision):
    if decision not in ('approved', 'denied'):
        flash('Invalid decision.', 'danger')
        return redirect(url_for('student.dashboard'))
    share_req = ShareRequest.query.get_or_404(request_id)
    if share_req.student_id != session['student_id']:
        abort(403)
    if share_req.status != 'pending':
        flash('Already processed.', 'info')
        return redirect(url_for('student.dashboard'))
    share_req.status = decision
    db.session.add(ConsentLog(student_id=session['student_id'],
                              request_id=request_id, decision=decision,
                              ip_address=request.remote_addr))
    db.session.commit()
    flash(f'Request #{request_id} {decision}.', 'success')
    return redirect(url_for('student.dashboard'))

# ── Scanner page ──────────────────────────────────────────────────────────────
@student_bp.route('/scanner')
@student_required
def scanner():
    student   = Student.query.get(session['student_id'])
    scans     = ScanHistory.query.filter_by(student_id=student.id)\
                                 .order_by(ScanHistory.scanned_at.desc()).all()
    _, tess_error = _get_tesseract()
    return render_template('student/scanner.html', student=student,
                           scans=scans, tess_error=tess_error)

# ── SERVER-SIDE OCR ───────────────────────────────────────────────────────────
@student_bp.route('/scanner/ocr', methods=['POST'])
@student_required
def scanner_ocr():
    # Always return valid JSON — no exceptions escape to the browser
    try:
        return _do_ocr()
    except Exception as e:
        tb = traceback.format_exc()
        print("OCR ERROR:\n", tb)
        # Return the real error message so the browser can display it
        return jsonify({'error': f'Server error: {str(e)}', 'detail': tb[-500:]}), 500

def _do_ocr():
    pytess, err = _get_tesseract()
    if err:
        return jsonify({'error': err, 'install_needed': True})

    try:
        from PIL import Image, ImageEnhance
    except ImportError:
        return jsonify({'error': 'Pillow not installed. Run: pip install pillow'})

    # ── Accept multipart file upload ──────────────────────────────────────
    img       = None
    filename  = 'document'
    scan_type = request.form.get('scan_type', 'id_card')

    if request.files.get('image'):
        f        = request.files['image']
        filename = f.filename or 'document'
        try:
            img = Image.open(f.stream).convert('RGB')
        except Exception as e:
            return jsonify({'error': f'Cannot open image: {e}'})
    else:
        data      = request.get_json(silent=True) or {}
        b64       = data.get('image_b64', '')
        filename  = data.get('filename', 'document')
        scan_type = data.get('scan_type', 'id_card')
        if not b64:
            return jsonify({'error': 'No image provided'})
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        try:
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
        except Exception as e:
            return jsonify({'error': f'Cannot decode image: {e}'})

    # ── Pre-process ───────────────────────────────────────────────────────
    w, h = img.size
    if max(w, h) < 1400:
        scale = 1400 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img  = ImageEnhance.Contrast(img).enhance(2.0)
    img  = ImageEnhance.Sharpness(img).enhance(2.0)
    gray = img.convert('L')

    # ── Run OCR ───────────────────────────────────────────────────────────
    try:
        raw_text = pytess.image_to_string(gray, config='--oem 3 --psm 3 -l eng').strip()
    except Exception as e:
        return jsonify({'error': f'OCR engine error: {e}'})

    if not raw_text:
        return jsonify({'ok': True, 'extracted': {}, 'raw_text': '',
                        'plain_count': 0, 'secret_count': 0, 'scan_id': None,
                        'warning': 'No text detected. Try a clearer, well-lit image.'})

    extracted = _parse_fields(raw_text)

    # ── Save to DB safely ─────────────────────────────────────────────────
    try:
        scan = ScanHistory(student_id=session['student_id'],
                           filename=filename, scan_type=scan_type)
        scan.set_data(extracted)
        db.session.add(scan)
        db.session.commit()
        scan_id      = scan.id
        plain_count  = len(scan.get_plain())
        secret_count = len(scan.get_secret())
    except Exception as e:
        db.session.rollback()
        # DB schema mismatch — save without encryption as fallback
        try:
            scan = ScanHistory(student_id=session['student_id'],
                               filename=filename, scan_type=scan_type,
                               extracted=json.dumps(extracted),
                               encrypted='')
            db.session.add(scan)
            db.session.commit()
            scan_id      = scan.id
            plain_count  = len(extracted)
            secret_count = 0
        except Exception as e2:
            db.session.rollback()
            return jsonify({'error': f'Database error: {e2}. Try deleting instance/student_privacy.db and restarting.'})

    return jsonify({
        'ok':          True,
        'scan_id':     scan_id,
        'extracted':   extracted,
        'raw_text':    raw_text[:2000],
        'plain_count': plain_count,
        'secret_count':secret_count,
    })

# ── Manual save ───────────────────────────────────────────────────────────────
@student_bp.route('/scanner/manual', methods=['POST'])
@student_required
def scanner_manual():
    try:
        data      = request.get_json(silent=True) or {}
        extracted = data.get('extracted', {})
        scan_type = data.get('scan_type', 'other')
        if not extracted:
            return jsonify({'error': 'No data'})
        scan = ScanHistory(student_id=session['student_id'],
                           filename='manual-entry', scan_type=scan_type)
        scan.set_data(extracted)
        db.session.add(scan)
        db.session.commit()
        return jsonify({'ok': True, 'scan_id': scan.id})
    except Exception as e:
        db.session.rollback()
        # Fallback without encryption
        try:
            scan = ScanHistory(student_id=session['student_id'],
                               filename='manual-entry', scan_type=data.get('scan_type','other'),
                               extracted=json.dumps(extracted), encrypted='')
            db.session.add(scan)
            db.session.commit()
            return jsonify({'ok': True, 'scan_id': scan.id})
        except Exception as e2:
            db.session.rollback()
            return jsonify({'error': str(e2)})

# ── Apply scan → profile ──────────────────────────────────────────────────────
@student_bp.route('/scanner/apply/<int:scan_id>')
@student_required
def scanner_apply(scan_id):
    scan    = ScanHistory.query.get_or_404(scan_id)
    if scan.student_id != session['student_id']:
        abort(403)
    student   = Student.query.get(session['student_id'])
    try:
        extracted = scan.get_all()
    except Exception:
        extracted = json.loads(scan.extracted or '{}')

    field_map = {
        'name':       ['name','full name','student name'],
        'email':      ['email','e-mail','mail'],
        'phone':      ['phone','mobile','contact'],
        'address':    ['address','addr','residence'],
        'dob':        ['dob','date of birth','birth date'],
        'department': ['department','dept','branch','course'],
        'year':       ['year','academic year','sem'],
    }
    updated = 0
    for attr, keys in field_map.items():
        for ek, ev in extracted.items():
            if not ev: continue
            for k in keys:
                if k in ek.lower():
                    if attr == 'year':
                        m = re.search(r'\d+', str(ev))
                        if m:
                            setattr(student, attr, int(m.group())); updated += 1
                    else:
                        setattr(student, attr, str(ev)); updated += 1
                    break
    db.session.commit()
    flash(f'Profile updated — {updated} field(s) applied from scan.', 'success')
    return redirect(url_for('student.profile'))

# ── Delete scan ───────────────────────────────────────────────────────────────
@student_bp.route('/scanner/delete/<int:scan_id>', methods=['POST'])
@student_required
def scanner_delete(scan_id):
    scan = ScanHistory.query.get_or_404(scan_id)
    if scan.student_id != session['student_id']:
        abort(403)
    try:
        ScanRequest.query.filter_by(scan_id=scan_id).delete()
    except Exception:
        pass
    db.session.delete(scan)
    db.session.commit()
    flash('Scan deleted.', 'info')
    return redirect(url_for('student.scanner'))

# ── Request admin ─────────────────────────────────────────────────────────────
@student_bp.route('/scanner/request_admin/<int:scan_id>', methods=['POST'])
@student_required
def request_admin_view(scan_id):
    scan = ScanHistory.query.get_or_404(scan_id)
    if scan.student_id != session['student_id']:
        abort(403)
    try:
        existing = ScanRequest.query.filter_by(
            student_id=session['student_id'], scan_id=scan_id, status='pending').first()
        if existing:
            flash('A request is already pending.', 'info')
            return redirect(url_for('student.scanner'))
        db.session.add(ScanRequest(student_id=session['student_id'],
                                   scan_id=scan_id,
                                   purpose=request.form.get('purpose','Admin review')))
        db.session.commit()
        flash('Request sent to admin.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Could not send request: {e}', 'danger')
    return redirect(url_for('student.scanner'))

# ── Download report ───────────────────────────────────────────────────────────
@student_bp.route('/report/download')
@student_required
def download_report():
    student = Student.query.get(session['student_id'])
    scans   = ScanHistory.query.filter_by(student_id=student.id)\
                               .order_by(ScanHistory.scanned_at.desc()).all()
    consent = ConsentLog.query.filter_by(student_id=student.id)\
                              .order_by(ConsentLog.decided_at.desc()).all()
    lines = ['='*60,'  PRIVACYGUARD — STUDENT DATA REPORT',
             f'  Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC',
             '='*60,'','PERSONAL INFORMATION','-'*40,
             f'  Full Name    : {student.name}',f'  Email        : {student.email}',
             f'  Phone        : {student.phone or "N/A"}',
             f'  Address      : {student.address or "N/A"}',
             f'  Date of Birth: {student.dob or "N/A"}',
             f'  Department   : {student.department or "N/A"}',
             f'  Year         : Year {student.year or "N/A"}','','SCAN HISTORY','-'*40]
    for s in scans:
        lines.append(f'  [{s.scanned_at.strftime("%Y-%m-%d %H:%M")}] {s.scan_type.upper()} — {s.filename}')
        try:
            for k,v in s.get_plain().items(): lines.append(f'    {k}: {v}')
            sc = s.get_secret()
            if sc: lines.append(f'    [{len(sc)} encrypted field(s)]')
        except Exception:
            try:
                for k,v in json.loads(s.extracted or '{}').items():
                    lines.append(f'    {k}: {v}')
            except Exception:
                pass
    if not scans: lines.append('  No scan records.')
    lines += ['','CONSENT HISTORY','-'*40]
    for c in consent:
        lines.append(f'  [{c.decided_at.strftime("%Y-%m-%d %H:%M")}] Request #{c.request_id} — {c.decision.upper()}')
    if not consent: lines.append('  No consent decisions yet.')
    lines += ['','='*60,'  END OF REPORT','='*60]
    buf = io.BytesIO('\n'.join(lines).encode('utf-8'))
    buf.seek(0)
    fname = f'PrivacyGuard_{student.name.replace(" ","_")}_{datetime.utcnow().strftime("%Y%m%d")}.txt'
    return send_file(buf, as_attachment=True, download_name=fname, mimetype='text/plain')

# ── Field parser ──────────────────────────────────────────────────────────────
def _parse_fields(text):
    fields = {}
    patterns = [
        ('Name',          r'(?:name|student\s*name|full\s*name)\s*[:\-]?\s*([A-Za-z][A-Za-z ]{2,50})'),
        ('Email',         r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})'),
        ('Phone',         r'(?:phone|mobile|cell|contact)\s*[:\-]?\s*([\+\d][\d\s\-\(\)]{7,16}\d)'),
        ('Date of Birth', r'(?:dob|date\s*of\s*birth|birth\s*date)\s*[:\-]?\s*([\d]{1,2}[\-\/\.][\d]{1,2}[\-\/\.][\d]{2,4})'),
        ('Department',    r'(?:dept|department|branch|program|course)\s*[:\-]?\s*([A-Za-z &]{3,60})'),
        ('Year',          r'(?:year|academic\s*year|sem(?:ester)?)\s*[:\-]?\s*(\d+(?:st|nd|rd|th)?(?:\s*year)?)'),
        ('Roll Number',   r'(?:roll\s*(?:no|number)|reg(?:istration)?\s*no|student\s*id)\s*[:\-]?\s*([\w\d\-\/]+)'),
        ('Address',       r'(?:address|addr|residence)\s*[:\-]?\s*(.{5,100})'),
        ('College',       r'(?:college|university|institution)\s*[:\-]?\s*(.{3,80})'),
        ('GPA',           r'(?:gpa|cgpa|sgpa|percentage)\s*[:\-]?\s*([\d.]+\s*(?:%|\/\s*\d+)?)'),
        ('Father Name',   r"(?:father(?:'s)?\s*name|parent)\s*[:\-]?\s*([A-Za-z ]{3,50})"),
        ('Gender',        r'(?:gender|sex)\s*[:\-]?\s*(male|female|other)'),
        ('Blood Group',   r'(?:blood\s*group|blood\s*type)\s*[:\-]?\s*([ABO]{1,2}[+-])'),
        ('Aadhaar',       r'(?:aadhaar|aadhar|uid)\s*[:\-]?\s*([\d]{4}\s*[\d]{4}\s*[\d]{4})'),
    ]
    for key, pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m and m.group(1) and 1 < len(m.group(1).strip()) < 150:
            fields[key] = m.group(1).strip().replace('\n', ' ')

    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'^([A-Za-z][A-Za-z\s\/\.]{2,28})\s*[:\-]\s*(.{2,100})$', line)
        if m:
            k, v = m.group(1).strip(), m.group(2).strip()
            if k not in fields and len(v) > 1 and not re.match(r'^[:\-\.\|]+$', v):
                fields[k] = v

    if not fields:
        for i, line in enumerate([l.strip() for l in text.split('\n') if l.strip()][:20]):
            if len(line) > 3:
                fields[f'Line {i+1}'] = line
    return fields
