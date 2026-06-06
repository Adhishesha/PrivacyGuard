"""routes/admin.py — Admin panel with scan request management"""
from flask import Blueprint, render_template, redirect, url_for, session, flash, request
from database import db
from models import User, Student, ShareRequest, AccessLog, ConsentLog, ScanHistory, ScanRequest
from functools import wraps
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    stats = {
        'students':    Student.query.count(),
        'users':       User.query.count(),
        'requests':    ShareRequest.query.count(),
        'pending':     ShareRequest.query.filter_by(status='pending').count(),
        'approved':    ShareRequest.query.filter_by(status='approved').count(),
        'denied':      ShareRequest.query.filter_by(status='denied').count(),
        'scan_reqs':   ScanRequest.query.filter_by(status='pending').count(),
        'total_scans': ScanHistory.query.count(),
    }
    recent_logs  = AccessLog.query.order_by(AccessLog.accessed_at.desc()).limit(8).all()
    scan_requests= ScanRequest.query.filter_by(status='pending')\
                              .order_by(ScanRequest.requested_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', stats=stats,
                           recent_logs=recent_logs, scan_requests=scan_requests)

@admin_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)

@admin_bp.route('/requests')
@admin_required
def requests():
    all_requests = ShareRequest.query.order_by(ShareRequest.requested_at.desc()).all()
    return render_template('admin/requests.html', requests=all_requests)

@admin_bp.route('/audit')
@admin_required
def audit():
    access_logs  = AccessLog.query.order_by(AccessLog.accessed_at.desc()).all()
    consent_logs = ConsentLog.query.order_by(ConsentLog.decided_at.desc()).all()
    return render_template('admin/audit.html', access_logs=access_logs, consent_logs=consent_logs)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('Cannot delete admin accounts.', 'danger')
        return redirect(url_for('admin.users'))
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" deleted.', 'success')
    return redirect(url_for('admin.users'))

# ── Scan Requests (student → admin) ──────────────────────────────────────────
@admin_bp.route('/scan-requests')
@admin_required
def scan_requests():
    pending  = ScanRequest.query.filter_by(status='pending')\
                          .order_by(ScanRequest.requested_at.desc()).all()
    reviewed = ScanRequest.query.filter(ScanRequest.status != 'pending')\
                          .order_by(ScanRequest.reviewed_at.desc()).limit(30).all()
    return render_template('admin/scan_requests.html', pending=pending, reviewed=reviewed)

@admin_bp.route('/scan-requests/view/<int:sreq_id>')
@admin_required
def view_scan(sreq_id):
    sreq = ScanRequest.query.get_or_404(sreq_id)
    scan = sreq.scan
    plain  = scan.get_plain()
    secret = scan.get_secret()
    return render_template('admin/view_scan.html', sreq=sreq, scan=scan,
                           plain=plain, secret=secret)

@admin_bp.route('/scan-requests/approve/<int:sreq_id>', methods=['POST'])
@admin_required
def approve_scan_request(sreq_id):
    sreq = ScanRequest.query.get_or_404(sreq_id)
    sreq.status      = 'approved'
    sreq.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f'Scan request from {sreq.student.name} approved.', 'success')
    return redirect(url_for('admin.view_scan', sreq_id=sreq_id))

@admin_bp.route('/scan-requests/deny/<int:sreq_id>', methods=['POST'])
@admin_required
def deny_scan_request(sreq_id):
    sreq = ScanRequest.query.get_or_404(sreq_id)
    sreq.status      = 'denied'
    sreq.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash('Scan request denied.', 'info')
    return redirect(url_for('admin.scan_requests'))

# ── All students with scans ───────────────────────────────────────────────────
@admin_bp.route('/students')
@admin_required
def students():
    all_students = Student.query.order_by(Student.name).all()
    return render_template('admin/students.html', students=all_students)
