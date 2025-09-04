

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory
import os
from werkzeug.utils import secure_filename
from app.models import db, User, Project, Phase, Item, SubItem, Image

main = Blueprint('main', __name__)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

@main.route('/')
def index():
    projects = Project.query.all()
    phases = Phase.query.all()
    items = Item.query.all()
    subitems = SubItem.query.all()
    return render_template('index.html', projects=projects, phases=phases, items=items, subitems=subitems)

@main.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('main.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('main.index'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        flash('File uploaded successfully')
    return redirect(url_for('main.index'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Project creation
@main.route('/create_project', methods=['POST'])
def create_project():
    title = request.form.get('project-title')
    if title:
        # For MVP, assign to first user or None
        owner = User.query.first()
        project = Project(title=title, owner=owner)
        db.session.add(project)
        db.session.commit()
        flash('Project created!')
    return redirect(url_for('main.index'))

# Phase creation
@main.route('/create_phase', methods=['POST'])
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
