from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory
import os
from werkzeug.utils import secure_filename
from app.models import db, User, Project, Phase, Item, SubItem, Image
from flask_login import login_required, current_user

main = Blueprint('main', __name__)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

@main.route('/')
@login_required
def index():
    projects = Project.query.all()
    phases = Phase.query.all()
    items = Item.query.all()
    subitems = SubItem.query.all()
    return render_template('index.html', projects=projects, phases=phases, items=items, subitems=subitems)

@main.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('main.index'))
    file = request.files['file']
    association_type = request.form.get('association-type')
    association_id = request.form.get('association-id')
    if file.filename == '' or not association_type or not association_id:
        flash('Missing file or association info')
        return redirect(url_for('main.index'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        # Parse association
        phase_id = item_id = subitem_id = None
        if association_type == 'phase' and association_id.startswith('phase-'):
            phase_id = int(association_id.split('-')[1])
        elif association_type == 'item' and association_id.startswith('item-'):
            item_id = int(association_id.split('-')[1])
        elif association_type == 'subitem' and association_id.startswith('subitem-'):
            subitem_id = int(association_id.split('-')[1])
        # Save image association
        img = Image(filename=filename, phase_id=phase_id, item_id=item_id, subitem_id=subitem_id)
        db.session.add(img)
        db.session.commit()
        flash('File uploaded and associated successfully')
    return redirect(url_for('main.index'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Project creation
@main.route('/create_project', methods=['POST'])
@login_required
def create_project():
    title = request.form.get('project-title')
    if title:
        # Assign to current user
        owner = current_user
        project = Project(title=title, owner=owner)
        db.session.add(project)
        db.session.commit()
        flash('Project created!')
    return redirect(url_for('main.index'))

# Phase creation
@main.route('/create_phase', methods=['POST'])
@login_required
def create_phase():
    title = request.form.get('phase-title')
    start_date = request.form.get('phase-start')
    duration = request.form.get('phase-duration')
    is_milestone = bool(request.form.get('phase-milestone'))
    internal_external = request.form.get('phase-type')
    project_id = request.form.get('project-id')
    if title and start_date and duration and project_id:
        phase = Phase(title=title, start_date=start_date, duration=duration, is_milestone=is_milestone, internal_external=internal_external, project_id=project_id)
        db.session.add(phase)
        db.session.commit()
        flash('Phase added!')
    return redirect(url_for('main.index'))

# Item creation
@main.route('/create_item', methods=['POST'])
@login_required
def create_item():
    title = request.form.get('item-title')
    start_date = request.form.get('item-start')
    duration = request.form.get('item-duration')
    dependencies = request.form.get('item-dependencies')
    is_milestone = bool(request.form.get('item-milestone'))
    internal_external = request.form.get('item-type')
    phase_id = request.form.get('phase-id')
    if title and start_date and duration and phase_id:
        item = Item(title=title, start_date=start_date, duration=duration, dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, phase_id=phase_id)
        db.session.add(item)
        db.session.commit()
        flash('Item added!')
    return redirect(url_for('main.index'))

# SubItem creation
@main.route('/create_subitem', methods=['POST'])
@login_required
def create_subitem():
    title = request.form.get('subitem-title')
    start_date = request.form.get('subitem-start')
    duration = request.form.get('subitem-duration')
    dependencies = request.form.get('subitem-dependencies')
    is_milestone = bool(request.form.get('subitem-milestone'))
    internal_external = request.form.get('subitem-type')
    item_id = request.form.get('item-id')
    if title and start_date and duration and item_id:
        subitem = SubItem(title=title, start_date=start_date, duration=duration, dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, item_id=item_id)
        db.session.add(subitem)
        db.session.commit()
        flash('Sub-Item added!')
    return redirect(url_for('main.index'))

@main.route('/make_admin/<int:user_id>')
@login_required
def make_admin(user_id):
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    user = User.query.get(user_id)
    if user:
        user.is_admin = True
        db.session.commit()
        flash(f'User {user.username} is now an admin.')
    return redirect(url_for('main.index'))

@main.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    users = User.query.all()
    return render_template('admin_users.html', users=users)
