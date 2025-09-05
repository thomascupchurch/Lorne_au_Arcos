from flask import Blueprint
from app.models import db, User, UserSession
from datetime import datetime, timedelta
from flask_login import login_required

utility_bp = Blueprint('utility', __name__)

@utility_bp.route('/healthz')
def healthz():
    try:
        db.session.execute('SELECT 1')
        return {'status':'ok'}, 200
    except Exception:
        return {'status':'degraded'}, 500

@utility_bp.route('/active_users')
@login_required
def active_users():
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    try:
        q = (db.session.query(User.username)
             .join(UserSession, User.id==UserSession.user_id)
             .filter(UserSession.last_seen >= cutoff)
             .distinct())
        users = sorted([r[0] for r in q.all()])
    except Exception:
        users=[]
    return {'users': users}
