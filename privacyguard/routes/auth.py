"""routes/auth.py — Login, Logout, Registration, Account Switcher"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User, Student

auth_bp = Blueprint('auth', __name__)


def _set_session(user):
    session['user_id']    = user.id
    session['username']   = user.username
    session['role']       = user.role
    session['student_id'] = user.student_id


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            _set_session(user)
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student.dashboard'))
            else:
                return redirect(url_for('share.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role     = request.form.get('role', 'requester')

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'warning')
            return render_template('auth/register.html')

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
        )

        if role == 'student':
            name  = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            dept  = request.form.get('department', '').strip()
            year  = request.form.get('year', 1)
            phone = request.form.get('phone', '').strip()
            dob   = request.form.get('dob', '').strip()
            addr  = request.form.get('address', '').strip()

            student = Student(name=name, email=email, department=dept,
                              year=int(year), phone=phone, dob=dob, address=addr)
            db.session.add(student)
            db.session.flush()
            user.student_id = student.id

        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ── Account switcher API ──────────────────────────────────────────────────────
@auth_bp.route('/accounts')
def accounts():
    """Return all registered users for the switcher dropdown."""
    users = User.query.order_by(User.role, User.username).all()
    current_id = session.get('user_id')
    return jsonify({'accounts': [
        {
            'id':       u.id,
            'username': u.username,
            'role':     u.role,
            'current':  u.id == current_id,
        }
        for u in users
    ]})


@auth_bp.route('/switch', methods=['POST'])
def switch():
    """Switch to another account without password (in-session switching)."""
    user_id = request.form.get('user_id', type=int)
    user    = User.query.get_or_404(user_id)
    _set_session(user)
    flash(f'Switched to <strong>{user.username}</strong> ({user.role}).', 'info')
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'student':
        return redirect(url_for('student.dashboard'))
    else:
        return redirect(url_for('share.dashboard'))
