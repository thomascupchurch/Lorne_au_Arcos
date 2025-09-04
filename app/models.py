from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    projects = db.relationship('Project', backref='owner', lazy=True)

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
    images = db.relationship('Image', backref='subitem', lazy=True)

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    subitem_id = db.Column(db.Integer, db.ForeignKey('subitem.id'))
