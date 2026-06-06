"""models.py — ORM models for PrivacyGuard"""
from database import db
from datetime import datetime
import base64, json


def _xor_encrypt(text: str, key: str = 'privacyguard2024') -> str:
    key_bytes  = key.encode()
    text_bytes = text.encode()
    encrypted  = bytes([text_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(text_bytes))])
    return base64.b64encode(encrypted).decode()

def _xor_decrypt(token: str, key: str = 'privacyguard2024') -> str:
    try:
        encrypted = base64.b64decode(token.encode())
        key_bytes = key.encode()
        decrypted = bytes([encrypted[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(encrypted))])
        return decrypted.decode()
    except Exception:
        return token


class Student(db.Model):
    __tablename__ = 'student'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    phone      = db.Column(db.String(20))
    address    = db.Column(db.Text)
    dob        = db.Column(db.String(20))
    department = db.Column(db.String(80))
    year       = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user           = db.relationship('User',         back_populates='student',  uselist=False)
    share_requests = db.relationship('ShareRequest', back_populates='student',  lazy='dynamic')
    consent_logs   = db.relationship('ConsentLog',   back_populates='student',  lazy='dynamic')
    scan_histories = db.relationship('ScanHistory',  back_populates='student',  lazy='dynamic')
    scan_requests  = db.relationship('ScanRequest',  back_populates='student',  lazy='dynamic')

    def to_dict(self, fields=None):
        full = {'Full Name': self.name,'Email': self.email,'Phone': self.phone,
                'Address': self.address,'Date of Birth': self.dob,
                'Department': self.department,'Year': self.year}
        return {k: v for k, v in full.items() if k in fields} if fields else full


class User(db.Model):
    __tablename__ = 'user'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='requester')
    student_id    = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    student        = db.relationship('Student',      back_populates='user')
    share_requests = db.relationship('ShareRequest', back_populates='requester', lazy='dynamic')
    access_logs    = db.relationship('AccessLog',    back_populates='accessed_by_user', lazy='dynamic')


class DataField(db.Model):
    __tablename__ = 'data_field'
    id           = db.Column(db.Integer, primary_key=True)
    field_name   = db.Column(db.String(80), unique=True, nullable=False)
    category     = db.Column(db.String(40))
    description  = db.Column(db.String(200))
    is_sensitive = db.Column(db.Boolean, default=False)
    request_fields = db.relationship('ShareRequestField', back_populates='field', lazy='dynamic')


class ShareRequest(db.Model):
    __tablename__ = 'share_request'
    id           = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'),    nullable=False)
    student_id   = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    purpose      = db.Column(db.Text, nullable=False)
    status       = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at   = db.Column(db.DateTime, nullable=True)

    requester      = db.relationship('User',              back_populates='share_requests')
    student        = db.relationship('Student',           back_populates='share_requests')
    request_fields = db.relationship('ShareRequestField', back_populates='request', cascade='all, delete-orphan')
    consent_logs   = db.relationship('ConsentLog',        back_populates='request', lazy='dynamic')
    access_logs    = db.relationship('AccessLog',         back_populates='request', lazy='dynamic')

    @property
    def field_names(self):
        return [rf.field.field_name for rf in self.request_fields]


class ShareRequestField(db.Model):
    __tablename__ = 'share_request_field'
    id         = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('share_request.id'), nullable=False)
    field_id   = db.Column(db.Integer, db.ForeignKey('data_field.id'),    nullable=False)
    request    = db.relationship('ShareRequest', back_populates='request_fields')
    field      = db.relationship('DataField',    back_populates='request_fields')
    __table_args__ = (db.UniqueConstraint('request_id', 'field_id', name='uq_request_field'),)


class ConsentLog(db.Model):
    __tablename__ = 'consent_log'
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'),       nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('share_request.id'), nullable=False)
    decision   = db.Column(db.String(10), nullable=False)
    decided_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    student    = db.relationship('Student',      back_populates='consent_logs')
    request    = db.relationship('ShareRequest', back_populates='consent_logs')


class AccessLog(db.Model):
    __tablename__ = 'access_log'
    id           = db.Column(db.Integer, primary_key=True)
    request_id   = db.Column(db.Integer, db.ForeignKey('share_request.id'), nullable=False)
    accessed_by  = db.Column(db.Integer, db.ForeignKey('user.id'),          nullable=False)
    accessed_at  = db.Column(db.DateTime, default=datetime.utcnow)
    action       = db.Column(db.String(80))
    request          = db.relationship('ShareRequest', back_populates='access_logs')
    accessed_by_user = db.relationship('User',         back_populates='access_logs')


class ScanHistory(db.Model):
    __tablename__ = 'scan_history'
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    filename   = db.Column(db.String(255))
    extracted  = db.Column(db.Text, default='{}')   # public fields JSON
    encrypted  = db.Column(db.Text, default='')     # XOR-encrypted sensitive fields
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    scan_type  = db.Column(db.String(40), default='id_card')
    student    = db.relationship('Student', back_populates='scan_histories')

    SENSITIVE = {'phone','mobile','address','dob','date of birth','birth date',
                 'father','mother','guardian','aadhaar','pan','passport',
                 'id number','roll number','student id','blood'}

    def set_data(self, fields: dict):
        plain, secret = {}, {}
        for k, v in fields.items():
            if any(s in k.lower() for s in self.SENSITIVE):
                secret[k] = v
            else:
                plain[k] = v
        self.extracted = json.dumps(plain)
        self.encrypted = _xor_encrypt(json.dumps(secret)) if secret else ''

    def get_plain(self) -> dict:
        try:
            return json.loads(self.extracted or '{}')
        except Exception:
            return {}

    def get_secret(self) -> dict:
        if not self.encrypted:
            return {}
        try:
            return json.loads(_xor_decrypt(self.encrypted))
        except Exception:
            return {}

    def get_all(self) -> dict:
        d = self.get_plain()
        d.update(self.get_secret())
        return d


class ScanRequest(db.Model):
    __tablename__ = 'scan_request'
    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey('student.id'),      nullable=False)
    scan_id      = db.Column(db.Integer, db.ForeignKey('scan_history.id'), nullable=False)
    purpose      = db.Column(db.Text)
    status       = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at  = db.Column(db.DateTime, nullable=True)
    student      = db.relationship('Student',     back_populates='scan_requests')
    scan         = db.relationship('ScanHistory')
