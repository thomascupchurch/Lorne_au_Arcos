import os
import tempfile
import pytest
from app import create_app
from app.models import db, User, Project, Phase, Item, SubItem, Image
from werkzeug.security import generate_password_hash

@pytest.fixture(scope='function')
def app():
    # Use a temporary SQLite DB in memory
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['SECRET_KEY'] = 'test-key'
    test_app = create_app()
    with test_app.app_context():
        db.create_all()
        # seed user only if not present (app factory may also create one depending on env vars)
        if not User.query.filter_by(username='tester').first():
            user = User(username='tester', password_hash=generate_password_hash('pass'), is_admin=True)
            db.session.add(user)
            db.session.commit()
    yield test_app

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def auth_client(client, app):
    with app.app_context():
        client.post('/login', data={'username':'tester','password':'pass'})
    return client
