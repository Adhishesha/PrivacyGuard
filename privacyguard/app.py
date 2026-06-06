import json, os
from flask import Flask, redirect, url_for
from database import db
from routes.auth import auth_bp
from routes.student import student_bp
from routes.share import share_bp
from routes.admin import admin_bp


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:///student_privacy.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    app.register_blueprint(auth_bp,    url_prefix='/auth')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(share_bp,   url_prefix='/share')
    app.register_blueprint(admin_bp,   url_prefix='/admin')

    @app.template_filter('fromjson')
    def fromjson_filter(value):
        try:
            return json.loads(value or '{}')
        except Exception:
            return {}

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()          # creates any missing tables
        _auto_migrate()          # adds any missing columns to existing tables
        _seed_data()

    return app


def _auto_migrate():
    """
    Safely add columns / tables that were introduced in newer versions.
    Uses raw SQL so it works even when models have changed.
    """
    import sqlalchemy as sa
    engine = db.engine

    def has_column(table, col):
        insp = sa.inspect(engine)
        try:
            return any(c['name'] == col for c in insp.get_columns(table))
        except Exception:
            return False

    def has_table(table):
        insp = sa.inspect(engine)
        return table in insp.get_table_names()

    with engine.connect() as conn:
        # scan_history — add 'encrypted' column if missing
        if has_table('scan_history') and not has_column('scan_history', 'encrypted'):
            conn.execute(sa.text("ALTER TABLE scan_history ADD COLUMN encrypted TEXT DEFAULT ''"))
            print("[migrate] Added scan_history.encrypted column")

        # scan_history — add 'scan_type' column if missing
        if has_table('scan_history') and not has_column('scan_history', 'scan_type'):
            conn.execute(sa.text("ALTER TABLE scan_history ADD COLUMN scan_type TEXT DEFAULT 'id_card'"))
            print("[migrate] Added scan_history.scan_type column")

        # scan_history — make sure 'extracted' exists (plain text JSON)
        if has_table('scan_history') and not has_column('scan_history', 'extracted'):
            conn.execute(sa.text("ALTER TABLE scan_history ADD COLUMN extracted TEXT DEFAULT '{}'"))
            print("[migrate] Added scan_history.extracted column")

        # scan_request table — create if missing
        if not has_table('scan_request'):
            conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS scan_request (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id   INTEGER NOT NULL REFERENCES student(id),
                    scan_id      INTEGER NOT NULL REFERENCES scan_history(id),
                    purpose      TEXT,
                    status       TEXT DEFAULT 'pending',
                    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at  DATETIME
                )
            """))
            print("[migrate] Created scan_request table")

        conn.commit()


def _seed_data():
    from models import DataField, User
    from werkzeug.security import generate_password_hash

    if DataField.query.first():
        return

    fields = [
        DataField(field_name='Full Name',    category='Identity', description='Student legal name',       is_sensitive=False),
        DataField(field_name='Email',        category='Contact',  description='Institutional email',      is_sensitive=False),
        DataField(field_name='Phone',        category='Contact',  description='Mobile / home phone',      is_sensitive=True),
        DataField(field_name='Address',      category='Contact',  description='Residential address',      is_sensitive=True),
        DataField(field_name='Date of Birth',category='Identity', description='DOB for age verification', is_sensitive=True),
        DataField(field_name='Department',   category='Academic', description='Enrolled department',      is_sensitive=False),
        DataField(field_name='Year',         category='Academic', description='Academic year / semester', is_sensitive=False),
    ]
    admin = User(username='admin',
                 password_hash=generate_password_hash('admin123'),
                 role='admin')
    from database import db as _db
    _db.session.add_all(fields)
    _db.session.add(admin)
    _db.session.commit()


if __name__ == '__main__':
    application = create_app()
    application.run(debug=True)
