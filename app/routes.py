from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory
import os
from werkzeug.utils import secure_filename
from app.models import db, User, Project, Phase, Item, SubItem, Image
from flask_login import login_required, current_user, login_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import csv
import io
import zipfile
from flask import send_file

main = Blueprint('main', __name__, url_prefix='')
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
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        phase = Phase(title=title, start_date=start_date_obj, duration=duration, is_milestone=is_milestone, internal_external=internal_external, project_id=project_id)
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
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        item = Item(title=title, start_date=start_date_obj, duration=duration, dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, phase_id=phase_id)
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
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        subitem = SubItem(title=title, start_date=start_date_obj, duration=duration, dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, item_id=item_id)
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

@main.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Logged in successfully')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid credentials')
            return redirect(url_for('main.login'))
    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Username and password required')
            return redirect(url_for('main.register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('main.register'))
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@main.route('/edit_project/<int:project_id>', methods=['POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    title = request.form.get('project-title')
    if title:
        project.title = title
        db.session.commit()
        flash('Project updated!')
    return redirect(url_for('main.index'))

@main.route('/edit_phase/<int:phase_id>', methods=['POST'])
@login_required
def edit_phase(phase_id):
    phase = Phase.query.get_or_404(phase_id)
    title = request.form.get('phase-title')
    start_date = request.form.get('phase-start')
    duration = request.form.get('phase-duration')
    is_milestone = bool(request.form.get('phase-milestone'))
    internal_external = request.form.get('phase-type')
    if title and start_date and duration:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_int = int(duration)
        phase.title = title
        phase.start_date = start_date_obj
        phase.duration = duration_int
        phase.is_milestone = is_milestone
        phase.internal_external = internal_external
        # Cascade update: ensure all items fit within phase
        phase_end = start_date_obj + timedelta(days=duration_int)
        for item in phase.items:
            # If item starts before phase, move it
            if item.start_date < start_date_obj:
                item.start_date = start_date_obj
            # If item ends after phase, shorten duration
            item_end = item.start_date + timedelta(days=int(item.duration))
            if item_end > phase_end:
                item.duration = (phase_end - item.start_date).days
            # Cascade to subitems
            item_end = item.start_date + timedelta(days=int(item.duration))
            for subitem in item.subitems:
                if subitem.start_date < item.start_date:
                    subitem.start_date = item.start_date
                subitem_end = subitem.start_date + timedelta(days=int(subitem.duration))
                if subitem_end > item_end:
                    subitem.duration = (item_end - subitem.start_date).days
        db.session.commit()
        flash('Phase updated and children validated!')
    return redirect(url_for('main.index'))

@main.route('/edit_item/<int:item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    title = request.form.get('item-title')
    start_date = request.form.get('item-start')
    duration = request.form.get('item-duration')
    dependencies = request.form.get('item-dependencies')
    is_milestone = bool(request.form.get('item-milestone'))
    internal_external = request.form.get('item-type')
    if title and start_date and duration:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_int = int(duration)
        item.title = title
        item.start_date = start_date_obj
        item.duration = duration_int
        item.dependencies = dependencies
        item.is_milestone = is_milestone
        item.internal_external = internal_external
        # Cascade update: ensure all subitems fit within item
        item_end = start_date_obj + timedelta(days=duration_int)
        for subitem in item.subitems:
            if subitem.start_date < start_date_obj:
                subitem.start_date = start_date_obj
            subitem_end = subitem.start_date + timedelta(days=int(subitem.duration))
            if subitem_end > item_end:
                subitem.duration = (item_end - subitem.start_date).days
        db.session.commit()
        flash('Item updated and children validated!')
    return redirect(url_for('main.index'))

@main.route('/delete_project/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted!')
    return redirect(url_for('main.index'))

@main.route('/delete_phase/<int:phase_id>', methods=['POST'])
@login_required
def delete_phase(phase_id):
    phase = Phase.query.get_or_404(phase_id)
    db.session.delete(phase)
    db.session.commit()
    flash('Phase deleted!')
    return redirect(url_for('main.index'))

@main.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted!')
    return redirect(url_for('main.index'))

@main.route('/delete_subitem/<int:subitem_id>', methods=['POST'])
@login_required
def delete_subitem(subitem_id):
    subitem = SubItem.query.get_or_404(subitem_id)
    db.session.delete(subitem)
    db.session.commit()
    flash('Sub-Item deleted!')
    return redirect(url_for('main.index'))

@main.route('/export_project/<int:project_id>')
@login_required
def export_project(project_id):
    project = Project.query.get_or_404(project_id)
    # Prepare CSV data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'ID', 'Title', 'Start Date', 'Duration', 'Dependencies', 'Milestone', 'Internal/External', 'Parent ID'])
    writer.writerow(['Project', project.id, project.title, '', '', '', '', '', ''])
    for phase in project.phases:
        writer.writerow(['Phase', phase.id, phase.title, phase.start_date, phase.duration, '', phase.is_milestone, phase.internal_external, project.id])
        for item in phase.items:
            writer.writerow(['Item', item.id, item.title, item.start_date, item.duration, item.dependencies, item.is_milestone, item.internal_external, phase.id])
            for subitem in item.subitems:
                writer.writerow(['SubItem', subitem.id, subitem.title, subitem.start_date, subitem.duration, subitem.dependencies, subitem.is_milestone, subitem.internal_external, item.id])
    csv_bytes = io.BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    # Prepare ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        zipf.writestr('project_data.csv', csv_bytes.read())
        # Add images
        for phase in project.phases:
            for img in phase.images:
                img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                if os.path.exists(img_path):
                    zipf.write(img_path, f'images/{img.filename}')
            for item in phase.items:
                for img in item.images:
                    img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                    if os.path.exists(img_path):
                        zipf.write(img_path, f'images/{img.filename}')
                for subitem in item.subitems:
                    for img in subitem.images:
                        img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                        if os.path.exists(img_path):
                            zipf.write(img_path, f'images/{img.filename}')
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f'project_{project.id}_export.zip')
