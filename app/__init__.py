import os
from flask import Flask
from werkzeug.security import generate_password_hash
from flask_login import LoginManager
from app.models import db, User
from app.routes import main

def create_app():
    # Explicitly set static_folder to top-level 'static' directory if not auto-detected
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-insecure')
    if app.config['SECRET_KEY'] == 'dev-insecure':
        print('WARNING: Using fallback dev SECRET_KEY; set SECRET_KEY in .env for production.')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'main.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(main)

    def ensure_admin():
        username = os.getenv('ADMIN_USERNAME')
        password = os.getenv('ADMIN_PASSWORD')
        if not username or not password:
            return
        user = User.query.filter_by(username=username).first()
        created = False
        if not user:
            user = User(username=username, password_hash=generate_password_hash(password), is_admin=True)
            db.session.add(user)
            created = True
        else:
            if not user.is_admin:
                user.is_admin = True
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        # Optional: you could print/log creation, but avoid noisy stdout in production.

    with app.app_context():
        # Make sure tables exist then ensure admin
        db.create_all()
        # Lightweight migration: add notes columns if database existed before (SQLite only)
        from sqlalchemy import text
        try:
            engine = db.engine
            def ensure_column(table, column_def):
                col_name = column_def.split()[0]
                with engine.connect() as conn:
                    info = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                    existing_cols = {r[1] for r in info}
                    if col_name not in existing_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))
                        except Exception as e:
                            # Silent for now; could log e
                            pass
            ensure_column('phase', 'notes TEXT')
            ensure_column('item', 'notes TEXT')
            ensure_column('sub_item', 'notes TEXT')
        except Exception:
            # Ignore migration issues silently to avoid startup failure
            pass
        ensure_admin()
    return app
