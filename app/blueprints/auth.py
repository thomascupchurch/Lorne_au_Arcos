from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    import time
    MAX_ATTEMPTS = 5
    LOCK_SECONDS = 300
    if current_user.is_authenticated:
        return redirect(url_for('planning.index'))
    locked_until = session.get('login_lock_until')
    if locked_until and locked_until > time.time():
        flash(f'Too many attempts. Try again in {int(locked_until - time.time())}s')
        return render_template('login.html')
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        attempts = session.get('login_attempts', 0)
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['login_attempts'] = 0
            session.pop('login_lock_until', None)
            login_user(user)
            flash('Signed in')
            return redirect(url_for('planning.index'))
        attempts += 1
        session['login_attempts'] = attempts
        remaining = MAX_ATTEMPTS - attempts
        if remaining <= 0:
            session['login_lock_until'] = time.time() + LOCK_SECONDS
            flash('Account locked for 5 minutes due to repeated failures.')
        else:
            flash(f'Invalid credentials. {remaining} attempts left.')
        return redirect(url_for('auth.login'))
    return render_template('login.html')

@auth_bp.route('/signin', methods=['GET','POST'])
def signin():
    return login()

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Username and password required')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('auth.register'))
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user); db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change_password', methods=['GET','POST'])
def change_password():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        old = request.form.get('old-password')
        new = request.form.get('new-password')
        confirm = request.form.get('confirm-password')
        if not old or not new or not confirm:
            flash('All fields required')
            return redirect(url_for('auth.change_password'))
        from werkzeug.security import check_password_hash, generate_password_hash
        if not check_password_hash(current_user.password_hash, old):
            flash('Current password incorrect')
            return redirect(url_for('auth.change_password'))
        if new != confirm:
            flash('Passwords do not match')
            return redirect(url_for('auth.change_password'))
        if len(new) < 6:
            flash('Password must be at least 6 characters')
            return redirect(url_for('auth.change_password'))
        current_user.password_hash = generate_password_hash(new)
        db.session.commit()
        flash('Password updated')
        return redirect(url_for('planning.index'))
    return render_template('change_password.html')
