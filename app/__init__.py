
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.routes import main
from app.models import db

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'replace-this-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(main)
    return app
