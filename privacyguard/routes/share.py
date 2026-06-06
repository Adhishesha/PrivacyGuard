"""routes/share.py — Share request creation and data viewing"""
from flask import Blueprint, render_template, redirect, url_for, session, flash, request
from database import db
from models import Student, DataField, ShareRequest, ShareRequestField, AccessLog
from datetime import datetime, timedelta
from functools import wraps

share_bp = Blueprint('share', __name__)


# ── Auth guard ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Requester dashboard ───────────────────────────────────────────────────────
@share_bp.route('/dashboard')
@login_required
def dashboard():
    my_requests = ShareRequest.query \
        .filter_by(requester_id=session['user_id']) \
        .order_by(ShareRequest.requested_at.desc()).all()
    return render_template('share/dashboard.html', requests=my_requests)


# ── Create a new share request ────────────────────────────────────────────────
@share_bp.route('/request', methods=['GET', 'POST'])
@login_required
def create_request():
    students = Student.query.order_by(Student.name).all()
    fields   = DataField.query.order_by(DataField.category, DataField.field_name).all()

    if request.method == 'POST':
        student_id  = request.form.get('student_id', type=int)
        purpose     = request.form.get('purpose', '').strip()
        field_ids   = request.form.getlist('field_ids', type=int)
        expire_days = request.form.get('expire_days', type=int, default=7)

        if not student_id or not purpose or not field_ids:
            flash('Please fill all required fields.', 'warning')
            return render_template('share/create_request.html',
                                   students=students, fields=fields)

        share_req = ShareRequest(
            requester_id=session['user_id'],
            student_id=student_id,
            purpose=purpose,
            status='pending',
            expires_at=datetime.utcnow() + timedelta(days=expire_days),
        )
        db.session.add(share_req)
        db.session.flush()

        for fid in field_ids:
            db.session.add(ShareRequestField(request_id=share_req.id, field_id=fid))

        db.session.commit()
        flash('Share request submitted and awaiting student consent.', 'success')
        return redirect(url_for('share.dashboard'))

    return render_template('share/create_request.html',
                           students=students, fields=fields)


# ── View approved shared data ─────────────────────────────────────────────────
@share_bp.route('/view/<int:request_id>')
@login_required
def view_data(request_id):
    share_req = ShareRequest.query.get_or_404(request_id)

    # Only the original requester (or admin) may view
    if share_req.requester_id != session['user_id'] and session.get('role') != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('share.dashboard'))

    if share_req.status != 'approved':
        flash('Access not permitted — request is not approved.', 'warning')
        return redirect(url_for('share.dashboard'))

    # Check expiry
    if share_req.expires_at and datetime.utcnow() > share_req.expires_at:
        share_req.status = 'expired'
        db.session.commit()
        flash('This share request has expired.', 'warning')
        return redirect(url_for('share.dashboard'))

    student    = share_req.student
    field_names= share_req.field_names
    data       = student.to_dict(fields=field_names)

    # Audit log
    log = AccessLog(
        request_id=request_id,
        accessed_by=session['user_id'],
        action='viewed shared data',
    )
    db.session.add(log)
    db.session.commit()

    return render_template('share/view_data.html',
                           share_req=share_req, data=data, student=student)
