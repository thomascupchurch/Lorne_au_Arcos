import os
import logging
from flask import Flask
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from flask_login import LoginManager
from app.models import db, User
from app.blueprints.auth import auth_bp
from app.blueprints.admin import admin_bp
from app.blueprints.utility import utility_bp
from app.blueprints.planning import planning_bp
from app.blueprints.media import media_bp
from config import get_config

def create_app():
    # Load .env early
    load_dotenv()
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    # Load config
    app.config.from_object(get_config())
    if app.config['SECRET_KEY'] == 'dev-insecure':
        app.logger.warning('Using fallback dev SECRET_KEY; set SECRET_KEY in .env for production.')
    # Basic logging config (can be overridden by gunicorn/host)
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(utility_bp)
    app.register_blueprint(planning_bp)
    app.register_blueprint(media_bp)

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
        # Avoid create_all when Alembic is managing schema (prevents duplicate tables during migrations)
        alembic_running = os.getenv('ALEMBIC_RUNNING') == '1'
        if not alembic_running:
            # For first-run (no migrations run yet) allow create_all, but prefer Alembic afterwards.
            if not os.path.exists(os.path.join(app.root_path, '..', 'app.db')):
                db.create_all()
        ensure_admin()
    return app
