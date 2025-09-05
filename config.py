import os
base_dir = os.path.abspath(os.path.dirname(__file__))
class BaseConfig:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-insecure')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(base_dir, 'app.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(base_dir, 'uploads'))
    SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', '15'))
    # Feature flags (future-proof)
    ENABLE_PRESENCE = os.getenv('ENABLE_PRESENCE', '1') == '1'
    ENABLE_DRAFTS = os.getenv('ENABLE_DRAFTS', '1') == '1'

class ProductionConfig(BaseConfig):
    pass

class DevelopmentConfig(BaseConfig):
    DEBUG = True

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

def get_config():
    env = os.getenv('FLASK_ENV', 'development').lower()
    return config_by_name.get(env, DevelopmentConfig)
