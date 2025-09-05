from flask import Blueprint, render_template, session, redirect, url_for, request, flash, send_file, current_app
from flask_login import login_required, current_user
from app.models import db, Project, Phase, Feature, Item, Image, DraftPart, UserSession
import os, json, io, csv, zipfile, re
from datetime import datetime, timedelta, date
import uuid as _uuid

planning_bp = Blueprint('planning', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')

# -------------------- Core Scheduling Utilities (Phase 1 migration) --------------------
def _parse_dep_ids(raw: str):
    """Parse dependency token list; accept raw numeric or prefixed like item-3, feature-5, phase-2.
    Returns list of integer IDs (IDs are treated as global-ish across features/items for naive CP calc).
    """
    if not raw:
        return []
    out = []
    for token in re.split(r'[;,]', raw):
        token = token.strip()
        if not token:
            continue
        # Extract trailing digits
        m = re.search(r'(\d+)$', token)
        if not m:
            continue
        try:
            out.append(int(m.group(1)))
        except ValueError:
            continue
    return out

def _task_window(obj):
    if not obj.start_date:
        return None, None
    start = obj.start_date
    end = obj.start_date + timedelta(days=getattr(obj, 'duration', 0))
    return start, end

def compute_critical_path(phases, features, items):
    """Compute a naive critical path across phases/features/items.

    Treat each phase/feature/item as a node. Dependencies only on features/items.
    Returns list like ['phase-1','feature-2','item-5'].
    """
    # Build adjacency via dependency references; phases currently have no explicit dependencies.
    nodes = []
    id_map = {}
    def add_node(prefix, obj, deps):
        sid = f"{prefix}-{obj.id}"
        duration = getattr(obj, 'duration', 0) or 0
        start, end = _task_window(obj)
        nodes.append({
            'sid': sid,
            'obj': obj,
            'deps': deps,
            'duration': duration,
            'start': start,
            'end': end
        })
        id_map[sid] = nodes[-1]
    for ph in phases:
        add_node('phase', ph, [])
    for ft in features:
        add_node('feature', ft, _parse_dep_ids(ft.dependencies))
    for it in items:
        add_node('item', it, _parse_dep_ids(it.dependencies))

    # DP over nodes: we need quick lookup by numeric id irrespective of type, so we flatten
    # and allow dependencies to reference any id (feature/item IDs). We'll map int IDs to possible nodes.
    numeric_index = {}
    for n in nodes:
        base_obj = n['obj']
        numeric_index.setdefault(base_obj.id, []).append(n)

    # Longest path weight (using duration) ending at node
    best_len = {}
    predecessor = {}
    # Simple DAG assumption; we iterate multiple passes up to N times or until stable.
    changed = True
    passes = 0
    while changed and passes < len(nodes):
        changed = False
        passes += 1
        for n in nodes:
            deps = []
            for dep_id in n['deps']:
                deps.extend(numeric_index.get(dep_id, []))
            if not deps:
                cand = n['duration']
                if best_len.get(n['sid']) != cand:
                    best_len[n['sid']] = cand
                    predecessor[n['sid']] = None
                    changed = True
            else:
                # choose predecessor giving max length
                best_pred = None
                best_val = -1
                for d in deps:
                    val = best_len.get(d['sid'], 0) + n['duration']
                    if val > best_val:
                        best_val = val
                        best_pred = d['sid']
                if best_len.get(n['sid']) != best_val:
                    best_len[n['sid']] = best_val
                    predecessor[n['sid']] = best_pred
                    changed = True
    if not best_len:
        return []
    # Find terminal node with max length and backtrack
    end_sid = max(best_len.items(), key=lambda kv: kv[1])[0]
    path = []
    cur = end_sid
    seen = set()
    while cur and cur not in seen:
        path.append(cur)
        seen.add(cur)
        cur = predecessor.get(cur)
    return list(reversed(path))

# -------------------- Placeholder endpoints being restored incrementally --------------------
@planning_bp.route('/set_project', methods=['POST'])
@login_required
def set_project():
    pid = request.form.get('project-id')
    if pid and pid.isdigit():
        session['selected_project_id'] = int(pid)
    return redirect(url_for('planning.index'))

@planning_bp.route('/create_part', methods=['POST'])
@login_required
def create_part():
    """Unified create endpoint for phase/feature/item.

    Supports dependency field for feature/item (comma numeric IDs). Returns JSON if
    X-Requested-With header present (AJAX), else redirects with flash.
    """
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    ptype = request.form.get('part-type')
    title = (request.form.get('part-title') or '').strip()
    internal_external = request.form.get('internal-external','internal')
    dependencies_raw = request.form.get('part-dependencies','')
    project_id = session.get('selected_project_id')
    if not title or not ptype:
        msg = 'Title and part type required'
        if ajax: return {'error': msg}, 400
        flash(msg); return redirect(url_for('planning.index'))
    # Accept either part-start or start-date naming (template uses part-start)
    start_raw = request.form.get('start-date') or request.form.get('part-start')
    try:
        start_date = datetime.strptime(start_raw, '%Y-%m-%d').date() if start_raw else None
    except Exception:
        start_date = None
    try:
        duration = int(request.form.get('duration') or 0)
    except ValueError:
        duration = 0

    created = None
    if ptype == 'phase':
        if not (project_id and start_date is not None):
            msg='Project and start date required for phase'
            if ajax: return {'error':msg},400
            flash(msg); return redirect(url_for('planning.index'))
        created = Phase(title=title, start_date=start_date, duration=duration,
                        project_id=project_id, internal_external=internal_external)
    elif ptype == 'feature':
        phase_id = request.form.get('phase-id') or request.form.get('parent-phase-id')
        if not (phase_id and start_date is not None):
            msg='Phase and start date required for feature'
            if ajax: return {'error':msg},400
            flash(msg); return redirect(url_for('planning.index'))
        created = Feature(title=title, start_date=start_date, duration=duration,
                          phase_id=int(phase_id), internal_external=internal_external,
                          dependencies=dependencies_raw or None)
    elif ptype == 'item':
        feature_id = request.form.get('feature-id') or request.form.get('parent-feature-id') or request.form.get('item-id')
        if not (feature_id and start_date is not None):
            msg='Feature and start date required for item'
            if ajax: return {'error':msg},400
            flash(msg); return redirect(url_for('planning.index'))
        created = Item(title=title, start_date=start_date, duration=duration,
                        feature_id=int(feature_id), internal_external=internal_external,
                        dependencies=dependencies_raw or None)
    else:
        msg='Unsupported part type'
        if ajax: return {'error':msg},400
        flash(msg); return redirect(url_for('planning.index'))

    db.session.add(created)
    db.session.commit()
    # Recompute critical path (rough) for response data
    phases = Phase.query.filter_by(project_id=project_id).all() if project_id else Phase.query.all()
    features = Feature.query.join(Phase).filter(Phase.project_id==project_id).all() if project_id else Feature.query.all()
    leafs = Item.query.join(Feature).join(Phase).filter(Phase.project_id==project_id).all() if project_id else Item.query.all()
    critical_ids = compute_critical_path(phases, features, leafs)
    resp_created = {
        'id': created.id,
        'type': ptype,
        'title': created.title,
        'start': created.start_date.strftime('%Y-%m-%d') if created.start_date else None,
        'duration': getattr(created,'duration',0),
        'dependencies': getattr(created,'dependencies',None)
    }
    # Build gantt task object expected client-side as resp.task
    end_date = (created.start_date + timedelta(days=getattr(created,'duration',0))).strftime('%Y-%m-%d') if created.start_date else None
    custom_cls = f"{ptype}-bar"
    if getattr(created,'internal_external','internal') == 'external':
        custom_cls += ' external-bar'
    task = {
        'id': f'{ptype}-{created.id}',
        'name': f'{ptype.capitalize()}: {created.title}',
        'start': resp_created['start'],
        'end': end_date,
        'progress': 0,
        'custom_class': custom_cls
    }
    if ajax:
        return {'status':'ok','created':resp_created,'task':task,'critical_path':critical_ids}
    flash(f'{ptype.capitalize()} created')
    return redirect(url_for('planning.index'))

@planning_bp.route('/create_draft_part', methods=['POST'])
@login_required
def create_draft_part():
    """Create a lightweight draft part. Type is optional in holding area.

    If omitted, part_type is stored as NULL and can be assigned during promotion.
    """
    title = request.form.get('draft-title','').strip()
    ptype = request.form.get('draft-type') or None
    internal_external = request.form.get('draft-internal-external','internal')
    # Optional extended fields
    start_raw = request.form.get('draft-start')
    duration_raw = request.form.get('draft-duration')
    milestone_flag = bool(request.form.get('draft-milestone'))
    dependencies = request.form.get('draft-dependencies') or None
    notes = request.form.get('draft-notes') or None
    # Allow drafts without project context; use optional explicit project override
    project_id_form = request.form.get('draft-project-id')
    try:
        project_id = int(project_id_form) if project_id_form else session.get('selected_project_id')
    except Exception:
        project_id = session.get('selected_project_id')
    if not title:
        return {'error':'missing title'}, 400
    start_date = None
    if start_raw:
        try:
            from datetime import datetime
            start_date = datetime.strptime(start_raw, '%Y-%m-%d').date()
        except Exception:
            start_date = None
    try:
        duration = int(duration_raw) if duration_raw else None
    except ValueError:
        duration = None
    # Optional pre-assigned parents to guide promotion
    phase_id = request.form.get('draft-phase-id'); feature_id = request.form.get('draft-feature-id')
    try:
        phase_id_val = int(phase_id) if phase_id else None
    except ValueError:
        phase_id_val = None
    try:
        feature_id_val = int(feature_id) if feature_id else None
    except ValueError:
        feature_id_val = None
    d = DraftPart(title=title, part_type=ptype, internal_external=internal_external, project_id=project_id,
                  start_date=start_date, duration=duration, is_milestone=milestone_flag,
                  dependencies=dependencies, notes=notes, phase_id=phase_id_val, feature_id=feature_id_val)
    db.session.add(d)
    db.session.commit()
    return {'status':'ok','draft':{
        'id': d.id, 'title': d.title, 'type': d.part_type,
        'internal_external': d.internal_external, 'project_id': d.project_id,
        'start': d.start_date.isoformat() if d.start_date else None,
        'duration': d.duration,
        'milestone': bool(d.is_milestone),
        'dependencies': d.dependencies,
        'notes': d.notes,
        'needs_type': d.part_type is None
    }}

@planning_bp.route('/promote_draft/<int:draft_id>', methods=['POST'])
@login_required
def promote_draft(draft_id):
    """Promote a draft into a concrete part (phase only for now)."""
    draft = DraftPart.query.get_or_404(draft_id)
    if draft.part_type != 'phase':
        return {'error':'Only phase promotion implemented in partial migration'}, 400
    project_id = draft.project_id or session.get('selected_project_id')
    if not project_id:
        return {'error':'project context required'}, 400
    try:
        start_date = datetime.strptime(request.form.get('start-date'), '%Y-%m-%d').date()
    except Exception:
        return {'error':'invalid start date'}, 400
    try:
        duration = int(request.form.get('duration') or 0)
    except ValueError:
        duration = 0
    ph = Phase(title=draft.title, start_date=start_date, duration=duration, project_id=project_id,
               internal_external=draft.internal_external)
    db.session.add(ph)
    db.session.delete(draft)
    db.session.commit()
    return {'status':'ok','created':{'id':ph.id,'type':'phase','title':ph.title}, 'removed_draft_id':draft_id}

@planning_bp.route('/promote_draft_auto', methods=['POST'])
@login_required
def promote_draft_auto():
    """Promote a draft with an inferred type & parent context via drag/drop.

    Expected JSON:
    { draft_id, inferred_type (phase|feature|item), start, duration, phase_id?, feature_id? }
    If draft.part_type is NULL we assign inferred_type. If it is set and differs, we return error.
    """
    data = request.get_json() or {}
    draft_id = data.get('draft_id'); inferred = data.get('inferred_type')
    start_raw = data.get('start'); duration = data.get('duration') or 1
    if not (draft_id and inferred):
        return {'error':'missing fields'}, 400
    draft = DraftPart.query.get_or_404(int(draft_id))
    if draft.part_type and draft.part_type != inferred:
        return {'error':'draft type conflict'}, 400
    if not draft.part_type:
        draft.part_type = inferred
    # Prefer provided start; else use draft.start_date if available
    if start_raw:
        try:
            start_date = datetime.strptime(start_raw, '%Y-%m-%d').date()
        except Exception:
            return {'error':'invalid start'}, 400
    else:
        start_date = draft.start_date or date.today()
    try:
        duration = int(duration)
    except ValueError:
        duration = 1
    if duration < 1: duration = 1
    if not data.get('duration') and draft.duration and isinstance(draft.duration, int):
        duration = max(1, draft.duration)
    created = None
    project_id = draft.project_id or session.get('selected_project_id')
    if inferred == 'phase':
        if not project_id:
            return {'error':'project context required'}, 400
        created = Phase(title=draft.title, start_date=start_date, duration=duration,
                         project_id=project_id, internal_external=draft.internal_external)
    elif inferred == 'feature':
        phase_id = data.get('phase_id') or draft.phase_id
        if not phase_id:
            return {'error':'phase_id required'}, 400
        created = Feature(title=draft.title, start_date=start_date, duration=duration,
                          phase_id=int(phase_id), internal_external=draft.internal_external)
    elif inferred == 'item':
        feature_id = data.get('feature_id') or draft.feature_id
        item_id = data.get('item_id') or draft.item_id
        resolved_feature_id = None
        if feature_id:
            try:
                resolved_feature_id = int(feature_id)
            except Exception:
                resolved_feature_id = None
        if not resolved_feature_id and item_id:
            try:
                it_ref = Item.query.get(int(item_id))
                if it_ref:
                    resolved_feature_id = it_ref.feature_id
            except Exception:
                resolved_feature_id = None
        if not resolved_feature_id:
            return {'error':'feature_id required'}, 400
        created = Item(title=draft.title, start_date=start_date, duration=duration,
                        feature_id=resolved_feature_id, internal_external=draft.internal_external)
    else:
        return {'error':'unsupported inferred type'}, 400
    db.session.add(created)
    db.session.delete(draft)
    db.session.commit()
    # critical path recompute limited to project scope when possible
    phases = Phase.query.filter_by(project_id=project_id).all() if project_id else Phase.query.all()
    features = Feature.query.join(Phase).filter(Phase.project_id==project_id).all() if project_id else Feature.query.all()
    leafs = Item.query.join(Feature).join(Phase).filter(Phase.project_id==project_id).all() if project_id else Item.query.all()
    critical_ids = compute_critical_path(phases, features, leafs)
    end_date = (created.start_date + timedelta(days=getattr(created,'duration',0))).strftime('%Y-%m-%d') if created.start_date else None
    custom_cls = f"{inferred}-bar"
    if getattr(created,'internal_external','internal') == 'external':
        custom_cls += ' external-bar'
    task = {
        'id': f'{inferred}-{created.id}',
        'name': f'{inferred.capitalize()}: {created.title}',
        'start': created.start_date.strftime('%Y-%m-%d'),
        'end': end_date,
        'progress': 0,
        'custom_class': custom_cls
    }
    return {'status':'ok','created':{
                'id': created.id, 'type': inferred, 'title': created.title,
                'start': task['start'], 'duration': getattr(created,'duration',0)
            }, 'task': task, 'critical_path': critical_ids, 'removed_draft_id': draft_id}

# -------------------- Reorder Endpoints (Phase 2 migration) --------------------
def _apply_new_positions(model, siblings, new_position):
    """Utility to reassign sequential sort_order with one element moved to new_position."""
    if new_position < 0: new_position = 0
    if new_position >= len(siblings): new_position = len(siblings)-1
    target = siblings.pop(siblings.index(model)) if model in siblings else model
    siblings.insert(new_position, target)
    for idx, s in enumerate(siblings):
        s.sort_order = idx

@planning_bp.route('/reorder_phase', methods=['POST'])
@login_required
def reorder_phase():
    data = request.get_json() or {}
    phase_id = data.get('phase_id'); project_id = data.get('project_id'); new_pos = data.get('new_position')
    if not all(v is not None for v in (phase_id, project_id, new_pos)):
        return {'error':'missing fields'}, 400
    ph = Phase.query.get(phase_id)
    if not ph or ph.project_id != int(project_id):
        return {'error':'phase not found'},404
    sibs = Phase.query.filter_by(project_id=project_id).order_by(Phase.sort_order.asc(), Phase.id.asc()).all()
    _apply_new_positions(ph, sibs, int(new_pos))
    db.session.commit()
    return {'status':'ok'}

@planning_bp.route('/reorder_feature', methods=['POST'])
@login_required
def reorder_feature():
    data = request.get_json() or {}
    feature_id=data.get('feature_id'); phase_id=data.get('phase_id'); new_pos=data.get('new_position')
    if not all(v is not None for v in (feature_id, phase_id, new_pos)):
        return {'error':'missing fields'},400
    ft = Feature.query.get(feature_id)
    if not ft or ft.phase_id != int(phase_id):
        return {'error':'feature not found'},404
    sibs = Feature.query.filter_by(phase_id=phase_id).order_by(Feature.sort_order.asc(), Feature.id.asc()).all()
    _apply_new_positions(ft, sibs, int(new_pos))
    db.session.commit()
    return {'status':'ok'}

@planning_bp.route('/reorder_item', methods=['POST'])
@login_required
def reorder_item():
    data = request.get_json() or {}
    item_id=data.get('item_id'); feature_id=data.get('feature_id'); new_pos=data.get('new_position')
    if not all(v is not None for v in (item_id, feature_id, new_pos)):
        return {'error':'missing fields'},400
    it = Item.query.get(item_id)
    if not it or it.feature_id != int(feature_id):
        return {'error':'item not found'},404
    sibs = Item.query.filter_by(feature_id=feature_id).order_by(Item.sort_order.asc(), Item.id.asc()).all()
    _apply_new_positions(it, sibs, int(new_pos))
    db.session.commit()
    return {'status':'ok'}

# -------------------- Critical Filter State --------------------
@planning_bp.route('/set_critical_filter', methods=['POST'])
@login_required
def set_critical_filter():
    data = request.get_json() or {}
    state = data.get('state')
    if state in ('on','off'):
        session['critical_filter'] = state
        return {'status':'ok','state':state}
    return {'error':'invalid state'},400

# -------------------- Export Placeholders (Phase 3 upcoming full implementation) --------------------
@planning_bp.route('/export_critical_csv')
@login_required
def export_critical_csv():
    # Minimal CSV export with current critical path IDs
    project_id = session.get('selected_project_id')
    phases = Phase.query.filter_by(project_id=project_id).all() if project_id else Phase.query.all()
    features = Feature.query.join(Phase).filter(Phase.project_id==project_id).all() if project_id else Feature.query.all()
    leafs = Item.query.join(Feature).join(Phase).filter(Phase.project_id==project_id).all() if project_id else Item.query.all()
    critical_ids = compute_critical_path(phases, features, leafs)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['order','id'])
    for idx, cid in enumerate(critical_ids, start=1):
        writer.writerow([idx, cid])
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='critical_path.csv')

# -------------------- Project & Part CRUD Endpoints (ported) --------------------
@planning_bp.route('/create_project', methods=['POST'])
@login_required
def create_project():
    title = (request.form.get('project-title') or '').strip()
    if not title:
        flash('Project title required')
        return redirect(url_for('planning.index'))
    proj = Project(title=title, owner_id=current_user.id)
    db.session.add(proj)
    db.session.commit()
    session['selected_project_id'] = proj.id
    return redirect(url_for('planning.index'))

@planning_bp.route('/edit_project/<int:project_id>', methods=['POST'])
@login_required
def edit_project(project_id):
    proj = Project.query.get_or_404(project_id)
    title = (request.form.get('project-title') or '').strip()
    if title:
        proj.title = title
        db.session.commit()
    return redirect(url_for('planning.index'))

@planning_bp.route('/delete_project/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    proj = Project.query.get_or_404(project_id)
    # Naive cascade: delete phases -> features -> items manually
    for ph in proj.phases:
        for ft in ph.features:
            for it in ft.items:
                db.session.delete(it)
            db.session.delete(ft)
        db.session.delete(ph)
    db.session.delete(proj)
    db.session.commit()
    if session.get('selected_project_id') == project_id:
        session.pop('selected_project_id')
    return redirect(url_for('planning.index'))

# Phase CRUD
@planning_bp.route('/edit_phase/<int:phase_id>', methods=['POST'])
@login_required
def edit_phase(phase_id):
    ph = Phase.query.get_or_404(phase_id)
    ph.title = (request.form.get('phase-title') or ph.title).strip()
    try:
        ph.start_date = datetime.strptime(request.form.get('phase-start'), '%Y-%m-%d').date()
    except Exception:
        pass
    try:
        ph.duration = int(request.form.get('phase-duration') or ph.duration)
    except ValueError:
        pass
    ph.is_milestone = bool(request.form.get('phase-milestone'))
    ph.internal_external = request.form.get('phase-type') or ph.internal_external
    ph.notes = request.form.get('phase-notes') or ph.notes
    db.session.commit()
    return redirect(url_for('planning.index'))

@planning_bp.route('/delete_phase/<int:phase_id>', methods=['POST'])
@login_required
def delete_phase(phase_id):
    ph = Phase.query.get_or_404(phase_id)
    for ft in ph.features:
        for it in ft.items:
            db.session.delete(it)
        db.session.delete(ft)
    db.session.delete(ph)
    db.session.commit()
    return redirect(url_for('planning.index'))

# Feature CRUD
@planning_bp.route('/edit_feature/<int:feature_id>', methods=['POST'])
@login_required
def edit_feature(feature_id):
    ft = Feature.query.get_or_404(feature_id)
    ft.title = (request.form.get('feature-title') or ft.title).strip()
    try:
        ft.start_date = datetime.strptime(request.form.get('feature-start'), '%Y-%m-%d').date()
    except Exception:
        pass
    try:
        ft.duration = int(request.form.get('feature-duration') or ft.duration)
    except ValueError:
        pass
    ft.dependencies = request.form.get('feature-dependencies') or ft.dependencies
    ft.is_milestone = bool(request.form.get('feature-milestone'))
    ft.internal_external = request.form.get('feature-type') or ft.internal_external
    ft.notes = request.form.get('feature-notes') or ft.notes
    db.session.commit()
    return redirect(url_for('planning.index'))

@planning_bp.route('/delete_feature/<int:feature_id>', methods=['POST'])
@login_required
def delete_feature(feature_id):
    ft = Feature.query.get_or_404(feature_id)
    for it in ft.items:
        db.session.delete(it)
    db.session.delete(ft)
    db.session.commit()
    return redirect(url_for('planning.index'))

# Item (leaf) CRUD
@planning_bp.route('/edit_item/<int:item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    it = Item.query.get_or_404(item_id)
    it.title = (request.form.get('item-title') or it.title).strip()
    try:
        it.start_date = datetime.strptime(request.form.get('item-start'), '%Y-%m-%d').date()
    except Exception:
        pass
    try:
        it.duration = int(request.form.get('item-duration') or it.duration)
    except ValueError:
        pass
    it.dependencies = request.form.get('item-dependencies') or it.dependencies
    it.is_milestone = bool(request.form.get('item-milestone'))
    it.internal_external = request.form.get('item-type') or it.internal_external
    it.notes = request.form.get('item-notes') or it.notes
    db.session.commit()
    return redirect(url_for('planning.index'))

@planning_bp.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    it = Item.query.get_or_404(item_id)
    db.session.delete(it)
    db.session.commit()
    return redirect(url_for('planning.index'))

# -------------------- Calendar (ICS) & Project Export --------------------
def _iter_project_parts(project_id=None):
    if project_id:
        phases = Phase.query.filter_by(project_id=project_id).all()
        features = Feature.query.join(Phase).filter(Phase.project_id==project_id).all()
        items = Item.query.join(Feature).join(Phase).filter(Phase.project_id==project_id).all()
    else:
        phases, features, items = Phase.query.all(), Feature.query.all(), Item.query.all()
    return phases, features, items

@planning_bp.route('/export_calendar_ics')
@login_required
def export_calendar_ics():
    project_id = session.get('selected_project_id')
    phases, features, items = _iter_project_parts(project_id)
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//LSI Graphics Planning//EN"]
    def add_event(prefix, obj):
        if not obj.start_date:
            return
        start = obj.start_date.strftime('%Y%m%d')
        # End is exclusive: add duration days
        end_dt = obj.start_date + timedelta(days=getattr(obj,'duration',0))
        end = end_dt.strftime('%Y%m%d')
        uid = f"{prefix}-{obj.id}@lsi-graphics"
        title = f"{prefix.capitalize()}: {obj.title}".replace('\n',' ')
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}", f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}", f"SUMMARY:{title}", "END:VEVENT"])
    for ph in phases: add_event('phase', ph)
    for ft in features: add_event('feature', ft)
    for it in items: add_event('item', it)
    lines.append('END:VCALENDAR')
    data = '\r\n'.join(lines).encode('utf-8')
    bio = io.BytesIO(data); bio.seek(0)
    fname = 'project_calendar.ics'
    return send_file(bio, mimetype='text/calendar', as_attachment=True, download_name=fname)

@planning_bp.route('/export_project/<int:project_id>')
@login_required
def export_project(project_id):
    proj = Project.query.get_or_404(project_id)
    payload = {
        'project': {'id': proj.id, 'title': proj.title},
        'phases': [], 'features': [], 'items': []
    }
    for ph in proj.phases:
        payload['phases'].append({'id': ph.id, 'title': ph.title, 'start': ph.start_date.isoformat(), 'duration': ph.duration, 'notes': ph.notes})
        for ft in ph.features:
            payload['features'].append({'id': ft.id, 'title': ft.title, 'start': ft.start_date.isoformat(), 'duration': ft.duration, 'phase_id': ph.id, 'deps': ft.dependencies, 'notes': ft.notes})
            for it in ft.items:
                payload['items'].append({'id': it.id, 'title': it.title, 'start': it.start_date.isoformat(), 'duration': it.duration, 'feature_id': ft.id, 'deps': it.dependencies, 'notes': it.notes})
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json', json.dumps(payload, indent=2))
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True, download_name=f'project_{proj.id}.zip')

# -------------------- Update (Drag) Endpoint with Cascade --------------------
def _build_dependency_graph(features, items):
    # Build mapping: id -> list of dependents across features+items by numeric IDs
    dependents = {}
    for collection in (features, items):
        for obj in collection:
            deps = _parse_dep_ids(obj.dependencies or '')
            for d in deps:
                dependents.setdefault(d, set()).add(obj.id)
    return dependents

def _index_objects(phases, features, items):
    by_numeric = {}
    for f in features:
        by_numeric[f.id] = ('feature', f)
    for i in items:
        by_numeric[i.id] = ('item', i)
    return by_numeric

def _recompute_critical(project_id=None):
    phases, features, items = _iter_project_parts(project_id)
    cp = compute_critical_path(phases, features, items)
    return cp, phases, features, items

@planning_bp.route('/update_gantt_task', methods=['POST'])
@login_required
def update_gantt_task():
    data = request.get_json() or {}
    sid = data.get('id')
    start_str = data.get('start')
    end_str = data.get('end')
    if not sid or not start_str:
        return {'error':'missing fields'}, 400
    m = re.match(r'^(phase|feature|item)-(\d+)$', sid)
    if not m:
        return {'error':'invalid id'},400
    kind, num = m.group(1), int(m.group(2))
    obj = None
    if kind=='phase': obj = Phase.query.get(num)
    elif kind=='feature': obj = Feature.query.get(num)
    else: obj = Item.query.get(num)
    if not obj:
        return {'error':'not found'},404
    try:
        new_start = datetime.strptime(start_str, '%Y-%m-%d').date()
    except Exception:
        return {'error':'bad start'},400
    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except Exception:
            end_date = new_start + timedelta(days=getattr(obj,'duration',0))
        duration = max(1, (end_date - new_start).days)
    else:
        duration = getattr(obj,'duration',1)
    obj.start_date = new_start
    if hasattr(obj,'duration'):
        obj.duration = duration
    db.session.commit()

    # Cascade (features/items only) recompute earliest starts for dependents
    project_id = session.get('selected_project_id')
    cp, phases, features, items = _recompute_critical(project_id)
    dependents_map = _build_dependency_graph(features, items)
    index_map = _index_objects(phases, features, items)
    adjustments = []
    # BFS from moved obj numeric id if feature/item
    start_numeric_ids = []
    if kind in ('feature','item'):
        start_numeric_ids.append(obj.id)
    visited = set()
    while start_numeric_ids:
        current = start_numeric_ids.pop(0)
        for dep in dependents_map.get(current, []):
            if dep in visited:
                continue
            visited.add(dep)
            kt, child = index_map.get(dep, (None,None))
            if not child:
                continue
            # Recompute earliest start
            deps = _parse_dep_ids(child.dependencies or '')
            if deps:
                latest_end = None
                for d in deps:
                    kt2, parent_obj = index_map.get(d, (None,None))
                    if parent_obj and parent_obj.start_date:
                        pend = parent_obj.start_date + timedelta(days=getattr(parent_obj,'duration',0))
                        if not latest_end or pend > latest_end:
                            latest_end = pend
                if latest_end and (latest_end != child.start_date):
                    # shift child if earlier than required; ensure not before dependency end
                    if latest_end > child.start_date:
                        child.start_date = latest_end
                        db.session.add(child)
            adjustments.append({
                'id': f'{kt}-{child.id}',
                'start': child.start_date.strftime('%Y-%m-%d'),
                'duration': getattr(child,'duration',0)
            })
            start_numeric_ids.append(dep)
    if adjustments:
        db.session.commit()
    return {'status':'ok','duration':duration,'critical_path':cp,'cascade':adjustments}

@planning_bp.route('/')
@login_required
def index():
    """Full planning index with critical path & calendar events."""
    projects = Project.query.all()
    selected_project_id = session.get('selected_project_id')
    if selected_project_id:
        phases = (Phase.query.filter_by(project_id=selected_project_id)
                  .order_by(Phase.sort_order.asc(), Phase.id.asc()).all())
        features = Feature.query.join(Phase).filter(Phase.project_id == selected_project_id).all()
        items = Item.query.join(Feature).join(Phase).filter(Phase.project_id == selected_project_id).all()
    else:
        phases = Phase.query.order_by(Phase.project_id.asc(), Phase.sort_order.asc(), Phase.id.asc()).all()
        features = Feature.query.all()
        items = Item.query.all()

    critical_path_ids = compute_critical_path(phases, features, items)
    critical_set = set(critical_path_ids)

    gantt_tasks = []
    for phase in phases:
        phase_start = phase.start_date.strftime('%Y-%m-%d') if phase.start_date else None
        phase_end = (phase.start_date + timedelta(days=phase.duration)).strftime('%Y-%m-%d') if phase.start_date else None
        cls = 'phase-bar'
        if phase.internal_external == 'external':
            cls += ' external-bar'
        if f'phase-{phase.id}' in critical_set:
            cls += ' critical-path'
        gantt_tasks.append({'id': f'phase-{phase.id}','name': f'Phase: {phase.title}','start': phase_start,'end': phase_end,'progress':0,'custom_class': cls})
        for feature in getattr(phase, 'features', []):
            f_start = feature.start_date.strftime('%Y-%m-%d') if feature.start_date else None
            f_end = (feature.start_date + timedelta(days=feature.duration)).strftime('%Y-%m-%d') if feature.start_date else None
            cls_f = 'feature-bar'
            if feature.internal_external=='external': cls_f += ' external-bar'
            if f'feature-{feature.id}' in critical_set: cls_f += ' critical-path'
            gantt_tasks.append({'id': f'feature-{feature.id}','name': f'Feature: {feature.title}','start': f_start,'end': f_end,'progress':0,'custom_class': cls_f})
            for item in getattr(feature, 'items', []):
                item_start = item.start_date.strftime('%Y-%m-%d') if item.start_date else None
                item_end = (item.start_date + timedelta(days=item.duration)).strftime('%Y-%m-%d') if item.start_date else None
                cls_i = 'item-bar'
                if item.internal_external=='external': cls_i += ' external-bar'
                if f'item-{item.id}' in critical_set: cls_i += ' critical-path'
                gantt_tasks.append({'id': f'item-{item.id}','name': f'Item: {item.title}','start': item_start,'end': item_end,'progress':0,'custom_class': cls_i})

    gantt_json_js = json.dumps(gantt_tasks)
    # Calendar events (simple mapping)
    calendar_events = []
    for t in gantt_tasks:
        if not t['start']:
            continue
        # End for calendar = end +1 day for exclusive range safety handled client-side; keep end
        calendar_events.append({'id': t['id'], 'title': t['name'], 'start': t['start'], 'end': t['end'], 'color': '#FF8200' if 'external' not in t['custom_class'] else '#4B4B4B'})
    calendar_events_json = json.dumps(calendar_events)
    draft_parts = DraftPart.query.order_by(DraftPart.created_at.asc()).all()
    draft_json_js = json.dumps([
        {'id': d.id, 'title': d.title, 'type': d.part_type, 'internal_external': d.internal_external, 'project_id': d.project_id, 'needs_type': d.part_type is None}
        for d in draft_parts
    ])
    images = Image.query.all()
    # Active users list (simple last_seen within 5 minutes)
    recent_cutoff = datetime.utcnow() - timedelta(minutes=5)
    active_sessions = UserSession.query.filter(UserSession.last_seen >= recent_cutoff).all()
    active_usernames = []
    if active_sessions:
        # Map to usernames via User model if available
        try:
            from app.models import User
            user_ids = {s.user_id for s in active_sessions}
            user_map = {u.id: u.username for u in User.query.filter(User.id.in_(user_ids)).all()}
            for s in active_sessions:
                uname = user_map.get(s.user_id)
                if uname and uname not in active_usernames:
                    active_usernames.append(uname)
        except Exception:
            pass
    critical_filter_active = (session.get('critical_filter') == 'on')
    return render_template('index.html',
                           projects=projects, phases=phases, features=features, items=items,
                           images=images, uploads_folder=UPLOAD_FOLDER, gantt_json_js=gantt_json_js,
                           draft_json_js=draft_json_js, calendar_events_json=calendar_events_json,
                           critical_path_ids=critical_path_ids, active_usernames=active_usernames,
                           critical_filter_active=critical_filter_active, selected_project_id=selected_project_id)

