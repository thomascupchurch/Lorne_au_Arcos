from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='owner', lazy=True)
    def is_active(self):
        return True

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phases = db.relationship('Phase', backref='project', lazy=True)

class Phase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # days
    is_milestone = db.Column(db.Boolean, default=False)
    internal_external = db.Column(db.String(20), default='internal')
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    notes = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    items = db.relationship('Item', backref='phase', lazy=True)
    images = db.relationship('Image', backref='phase', lazy=True)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    dependencies = db.Column(db.String(256))  # comma-separated IDs
    is_milestone = db.Column(db.Boolean, default=False)
    internal_external = db.Column(db.String(20), default='internal')
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'), nullable=False)
    notes = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    subitems = db.relationship('SubItem', backref='item', lazy=True)
    images = db.relationship('Image', backref='item', lazy=True)

class SubItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    dependencies = db.Column(db.String(256))
    is_milestone = db.Column(db.Boolean, default=False)
    internal_external = db.Column(db.String(20), default='internal')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    notes = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    images = db.relationship('Image', backref='subitem', lazy=True)

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    subitem_id = db.Column(db.Integer, db.ForeignKey('sub_item.id'))

class DraftPart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    part_type = db.Column(db.String(20), nullable=False)  # phase|item|subitem
    internal_external = db.Column(db.String(20), default='internal')
    dependencies = db.Column(db.String(256))
    notes = db.Column(db.Text)
    # Optional pre-assignment references (may be null until promotion)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_uuid = db.Column(db.String(64), unique=True, nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, index=True)
