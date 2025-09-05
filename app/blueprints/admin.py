from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash
from app.models import db, User, Project, Phase, Item, SubItem, Image

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def _require_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('Admin access required.')
        return False
    return True

@admin_bp.route('/')
@login_required
def dashboard():
    if not _require_admin():
        return redirect(url_for('planning.index'))
    stats = {
        'users': User.query.count(),
        'projects': Project.query.count(),
        'phases': Phase.query.count(),
        'items': Item.query.count(),
        'subitems': SubItem.query.count(),
        'images': Image.query.count()
    }
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    return render_template('admin_dashboard.html', stats=stats, recent_users=recent_users)

@admin_bp.route('/users')
@login_required
def users():
    if not _require_admin():
        return redirect(url_for('planning.index'))
    q = request.args.get('q','').strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(User.username.ilike(like))
    users = query.order_by(User.username.asc()).all()
    return render_template('admin_users.html', users=users, q=q)

@admin_bp.route('/create_user', methods=['POST'])
@login_required
def create_user():
    if not _require_admin():
        return redirect(url_for('planning.index'))
    username = request.form.get('new-username')
    password = request.form.get('new-password')
    if not username or not password:
        flash('Username and password required')
        return redirect(url_for('admin.users'))
    if User.query.filter_by(username=username).first():
        flash('Username already exists')
        return redirect(url_for('admin.users'))
    if len(password) < 6:
        flash('Password must be at least 6 characters')
        return redirect(url_for('admin.users'))
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user); db.session.commit()
    flash('User created')
    return redirect(url_for('admin.users'))

@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not _require_admin():
        return redirect(url_for('planning.index'))
    if current_user.id == user_id:
        flash('You cannot delete yourself.')
        return redirect(url_for('admin.users'))
    user = User.query.get_or_404(user_id)
    if user.projects and len(user.projects) > 0:
        flash('Cannot delete user who owns projects.')
        return redirect(url_for('admin.users'))
    db.session.delete(user); db.session.commit()
    flash('User deleted')
    return redirect(url_for('admin.users'))

@admin_bp.route('/reset_password/<int:user_id>', methods=['POST'])
@login_required
def reset_password(user_id):
    if not _require_admin():
        return redirect(url_for('planning.index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Use Change Password for your own account.')
        return redirect(url_for('admin.users'))
    new_pw = request.form.get('new-password')
    if not new_pw or len(new_pw) < 6:
        flash('Provide a new password (min 6 chars).')
        return redirect(url_for('admin.users'))
    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    flash(f'Password reset for {user.username}.')
    return redirect(url_for('admin.users'))

@admin_bp.route('/make_admin/<int:user_id>')
@login_required
def make_admin(user_id):
    if not _require_admin():
        return redirect(url_for('planning.index'))
    user = User.query.get(user_id)
    if user:
        user.is_admin = True; db.session.commit(); flash(f'User {user.username} is now an admin.')
    return redirect(url_for('admin.users'))

@admin_bp.route('/revoke_admin/<int:user_id>')
@login_required
def revoke_admin(user_id):
    if not _require_admin():
        return redirect(url_for('planning.index'))
    user = User.query.get(user_id)
    if user and user.id != current_user.id:
        user.is_admin = False; db.session.commit(); flash(f'Admin rights revoked for {user.username}.')
    else:
        flash('Cannot revoke this user.')
    return redirect(url_for('admin.users'))
