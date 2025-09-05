import os, io, zipfile, csv
from flask import Blueprint, request, redirect, url_for, flash, send_from_directory, current_app, send_file
from flask_login import login_required
from app.models import db, Image, Phase, Feature, Item, Project

media_bp = Blueprint('media', __name__, url_prefix='/media')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@media_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('planning.index'))
    files = request.files.getlist('file')
    if not files:
        flash('No files selected')
        return redirect(url_for('planning.index'))
    uploaded = 0
    from flask import session
    for file in files:
        if not file or file.filename == '':
            continue
        if allowed_file(file.filename):
            filename = file.filename.replace(' ', '_')
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            project_id = session.get('selected_project_id')
            img = Image(filename=filename, project_id=project_id)
            db.session.add(img)
            uploaded += 1
    if uploaded:
        db.session.commit(); flash(f'Uploaded {uploaded} file(s)')
    else:
        flash('No valid files uploaded')
    return redirect(url_for('planning.index'))

@media_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    abs_file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(abs_file_path):
        from flask import abort; abort(404)
    return send_from_directory(UPLOAD_FOLDER, filename)

@media_bp.route('/associate', methods=['POST'])
@login_required
def associate_image():
    data = request.get_json() or {}
    image_id = data.get('image_id'); target_type = data.get('target_type'); target_id = data.get('target_id')
    if not all([image_id, target_type, target_id]):
        return {'error':'missing fields'}, 400
    img = Image.query.get(image_id)
    if not img: return {'error':'not found'},404
    try:
        added=False
        if target_type=='phase':
            ph=Phase.query.get(int(target_id));
            if not ph: return {'error':'phase not found'},404
            if ph not in img.phases: img.phases.append(ph); added=True
        elif target_type=='feature':
            ft=Feature.query.get(int(target_id));
            if not ft: return {'error':'feature not found'},404
            if ft not in img.features: img.features.append(ft); added=True
        elif target_type=='item':
            it=Item.query.get(int(target_id));
            if not it: return {'error':'item not found'},404
            if it not in img.items: img.items.append(it); added=True
        else:
            return {'error':'bad target_type'},400
        db.session.commit(); return {'status':'ok','image_id':img.id,'target_type':target_type,'target_id':target_id,'added':added}
    except Exception:
        db.session.rollback(); return {'error':'associate failed'},500

@media_bp.route('/unlink', methods=['POST'])
@login_required
def unlink_image():
    data = request.get_json() or {}
    image_id = data.get('image_id'); context_type=data.get('context_type'); context_id=data.get('context_id')
    if not image_id: return {'error':'image_id required'},400
    img = Image.query.get(image_id)
    if not img: return {'error':'not found'},404
    changed=False
    try:
        if context_type=='phase' and context_id:
            ph=Phase.query.get(int(context_id));
            if ph and ph in img.phases: img.phases.remove(ph); changed=True
        elif context_type=='feature' and context_id:
            ft=Feature.query.get(int(context_id));
            if ft and ft in img.features: img.features.remove(ft); changed=True
        elif context_type=='item' and context_id:
            it=Item.query.get(int(context_id));
            if it and it in img.items: img.items.remove(it); changed=True
        elif not context_type:
            if img.phases or img.features or img.items:
                img.phases.clear(); img.features.clear(); img.items.clear(); changed=True
        if changed: db.session.commit()
        return {'status':'ok','image_id':img.id,'cleared':changed}
    except Exception:
        db.session.rollback(); return {'error':'unlink failed'},500

@media_bp.route('/links/<int:image_id>')
@login_required
def image_links(image_id):
    img = Image.query.get_or_404(image_id)
    def simple_phase(p): return {'id':p.id,'title':p.title,'type':'phase'}
    def simple_feature(f): return {'id':f.id,'title':f.title,'type':'feature'}
    def simple_item(i): return {'id':i.id,'title':i.title,'type':'item'}
    return {
        'image_id': img.id,
        'filename': img.filename,
        'project_id': img.project_id,
        'phases': [simple_phase(p) for p in img.phases],
        'features': [simple_feature(f) for f in img.features],
        'items': [simple_item(i) for i in img.items]
    }
