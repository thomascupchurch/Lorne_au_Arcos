
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, send_file, session
import os
from werkzeug.utils import secure_filename
from app.models import db, User, Project, Phase, Item, SubItem, Image, DraftPart, UserSession
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import csv
import io
import zipfile

# Critical path computation (moved to module level for reuse)
def compute_critical_path(tasks):
    """Compute critical path for list of task dicts each having id,start,end and optional dependencies."""
    from datetime import datetime as _dt
    deps = {}
    rev = {}
    dur = {}
    for t in tasks:
        s = _dt.strptime(t['start'], '%Y-%m-%d')
        e = _dt.strptime(t['end'], '%Y-%m-%d')
        dur[t['id']] = max(1, (e - s).days)
        raw = t.get('dependencies') or ''
        arr = [d for d in raw.replace(';', ' ').replace(',', ' ').split() if d]
        deps[t['id']] = arr
        for d in arr:
            rev.setdefault(d, []).append(t['id'])
    in_deg = {t['id']: 0 for t in tasks}
    for k, arr in deps.items():
        for d in arr:
            if k in in_deg:
                in_deg[k] += 1
    queue = [k for k, v in in_deg.items() if v == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for s in rev.get(n, []):
            in_deg[s] -= 1
            if in_deg[s] == 0:
                queue.append(s)
    if len(order) != len(tasks):  # cycle fallback
        order = [t['id'] for t in tasks]
    es, ef = {}, {}
    for tid in order:
        predecessors = deps.get(tid, [])
        if not predecessors:
            es[tid] = 0
        else:
            es[tid] = max(ef.get(p, 0) for p in predecessors)
        ef[tid] = es[tid] + dur[tid]
    project_finish = max(ef.values()) if ef else 0
    lf, ls = {}, {}
    for tid in reversed(order):
        succ = rev.get(tid, [])
        if not succ:
            lf[tid] = project_finish
        else:
            lf[tid] = min(ls[s] for s in succ)
        ls[tid] = lf[tid] - dur[tid]
    critical = [tid for tid in order if (ls[tid] - es[tid]) == 0]
    crit_set = set(critical)
    path = []
    start_node = next((c for c in critical if es[c] == 0), None)
    guard = 0
    cur = start_node
    while cur and guard < len(critical):
        path.append(cur)
        successors = rev.get(cur, [])
        nxt = None
        for s in successors:
            if s in crit_set and es[s] == ef[cur]:
                nxt = s
                break
        cur = nxt
        guard += 1
    if not path:
        path = critical
    return path

# ---------- Dependency Utilities ----------
def _parse_dependency_ids(raw: str):
    if not raw:
        return []
    return [d.strip() for d in raw.replace(';', ' ').replace(',', ' ').split() if d.strip()]

def _get_task_dates(dep_id):
    """Return (start_date, end_date) for phase-/item-/subitem-* id or (None,None). end_date is inclusive finish date."""
    if dep_id.startswith('phase-'):
        ph = Phase.query.get(int(dep_id.split('-')[1]))
        if ph:
            return ph.start_date, ph.start_date + timedelta(days=ph.duration)
    elif dep_id.startswith('item-'):
        it = Item.query.get(int(dep_id.split('-')[1]))
        if it:
            return it.start_date, it.start_date + timedelta(days=it.duration)
    elif dep_id.startswith('subitem-'):
        si = SubItem.query.get(int(dep_id.split('-')[1]))
        if si:
            return si.start_date, si.start_date + timedelta(days=si.duration)
    return None, None

def _enforce_dependencies_and_containment(obj):
    """Adjust start_date of Item/SubItem (and recompute duration unchanged) to satisfy dependencies and parent containment.
    Returns True if modified."""
    changed = False
    if isinstance(obj, Item):
        # dependency
        dep_ids = _parse_dependency_ids(obj.dependencies)
        if dep_ids:
            latest_end = None
            for did in dep_ids:
                _, e = _get_task_dates(did)
                if e and (latest_end is None or e > latest_end):
                    latest_end = e
            if latest_end and obj.start_date < latest_end:
                shift = (latest_end - obj.start_date).days
                obj.start_date = latest_end
                # keep duration
                changed = True
        # containment (phase)
        if obj.phase:
            p_start = obj.phase.start_date
            p_end = obj.phase.start_date + timedelta(days=obj.phase.duration)
            if obj.start_date < p_start:
                obj.start_date = p_start; changed = True
            end_date = obj.start_date + timedelta(days=obj.duration)
            if end_date > p_end:
                # clamp by shortening duration (or could shift back; shorten simpler)
                new_dur = max(1, (p_end - obj.start_date).days)
                if new_dur != obj.duration:
                    obj.duration = new_dur; changed = True
    elif isinstance(obj, SubItem):
        dep_ids = _parse_dependency_ids(obj.dependencies)
        if dep_ids:
            latest_end = None
            for did in dep_ids:
                _, e = _get_task_dates(did)
                if e and (latest_end is None or e > latest_end):
                    latest_end = e
            if latest_end and obj.start_date < latest_end:
                obj.start_date = latest_end; changed = True
        if obj.item:
            i_start = obj.item.start_date
            i_end = obj.item.start_date + timedelta(days=obj.item.duration)
            if obj.start_date < i_start:
                obj.start_date = i_start; changed = True
            end_date = obj.start_date + timedelta(days=obj.duration)
            if end_date > i_end:
                new_dur = max(1, (i_end - obj.start_date).days)
                if new_dur != obj.duration:
                    obj.duration = new_dur; changed = True
    return changed

def _cascade_dependents(changed_ids):
    """Propagate dependency shifts forward. changed_ids: iterable of task ids (phase-/item-/subitem-*)."""
    queue = list(changed_ids)
    visited = set()
    adjusted = []
    # Preload all items/subitems for dependency parsing
    all_items = Item.query.all()
    all_subs = SubItem.query.all()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        # find dependents
        for obj in list(all_items) + list(all_subs):
            dep_ids = _parse_dependency_ids(getattr(obj, 'dependencies', ''))
            if current in dep_ids:
                before_start = obj.start_date
                before_dur = obj.duration
                if _enforce_dependencies_and_containment(obj):
                    adjusted.append({'id': f'item-{obj.id}' if isinstance(obj, Item) else f'subitem-{obj.id}',
                                     'start': str(obj.start_date),
                                     'duration': obj.duration})
                    queue.append(('item-' if isinstance(obj, Item) else 'subitem-') + str(obj.id))
    if adjusted:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            adjusted = []
    return adjusted

main = Blueprint('main', __name__, url_prefix='')
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# --- Simple active user presence tracking (memory-only) ---
from time import time as _time
from datetime import datetime as _dt, timedelta as _td
import uuid as _uuid

from flask import current_app as _ca
SESSION_TIMEOUT_MINUTES = lambda: int(_ca.config.get('SESSION_TIMEOUT_MINUTES', 15))

@main.before_app_request
def _track_presence():
    from flask_login import current_user as _cu
    if not getattr(_cu, 'is_authenticated', False):
        return
    now = _dt.utcnow()
    # Persist user last_seen
    try:
        _cu.last_seen = now
        # Ensure a session UUID stored in flask session
        sid = session.get('presence_session_id')
        if not sid:
            sid = _uuid.uuid4().hex
            session['presence_session_id'] = sid
            us = UserSession(user_id=_cu.id, session_uuid=sid, last_seen=now)
            db.session.add(us)
        else:
            us = UserSession.query.filter_by(session_uuid=sid).first()
            if not us:
                us = UserSession(user_id=_cu.id, session_uuid=sid, last_seen=now)
                db.session.add(us)
            else:
                us.last_seen = now
        # Cleanup stale sessions (older than timeout)
        cutoff = now - _td(minutes=SESSION_TIMEOUT_MINUTES())
        try:
            UserSession.query.filter(UserSession.last_seen < cutoff).delete(synchronize_session=False)
        except Exception:
            pass
        db.session.commit()
    except Exception:
        db.session.rollback()

def _get_active_usernames():
    cutoff = _dt.utcnow() - _td(minutes=SESSION_TIMEOUT_MINUTES())
    try:
        q = (db.session.query(User.username)
             .join(UserSession, User.id==UserSession.user_id)
             .filter(UserSession.last_seen >= cutoff)
             .distinct())
        return sorted([r[0] for r in q.all()])
    except Exception:
        return []

@main.route('/set_project', methods=['POST'])
@login_required
def set_project():
    project_id = request.form.get('project-id')
    session['selected_project_id'] = project_id
    return redirect(url_for('main.index'))

@main.route('/')
@login_required
def index():
    projects = Project.query.all()
    selected_project_id = session.get('selected_project_id')
    if selected_project_id:
        phases = Phase.query.filter_by(project_id=selected_project_id).order_by(Phase.sort_order.asc(), Phase.id.asc()).all()
        items = Item.query.join(Phase).filter(Phase.project_id==selected_project_id).all()
        subitems = SubItem.query.join(Item).join(Phase).filter(Phase.project_id==selected_project_id).all()
    else:
        phases = Phase.query.order_by(Phase.project_id.asc(), Phase.sort_order.asc(), Phase.id.asc()).all()
        items = Item.query.all()
        subitems = SubItem.query.all()
    # Build Gantt chart data in Python
    import json
    from datetime import datetime, timedelta
    gantt_tasks = []
    for phase in phases:
        phase_start = phase.start_date if isinstance(phase.start_date, str) else str(phase.start_date)
        phase_end = (datetime.strptime(phase_start, '%Y-%m-%d') + timedelta(days=int(phase.duration))).strftime('%Y-%m-%d')
        # Always include structural class (phase-bar) and append external-bar if external
        phase_class = 'phase-bar' + (' external-bar' if getattr(phase, 'internal_external', None) == 'external' else '')
        gantt_tasks.append({
            'id': f'phase-{phase.id}',
            'name': f'Phase: {phase.title}',
            'start': phase_start,
            'end': phase_end,
            'progress': 0,
            'custom_class': phase_class
        })
        for item in phase.items:
            item_start = item.start_date if isinstance(item.start_date, str) else str(item.start_date)
            item_end = (datetime.strptime(item_start, '%Y-%m-%d') + timedelta(days=int(item.duration))).strftime('%Y-%m-%d')
            item_class = 'item-bar' + (' external-bar' if getattr(item, 'internal_external', None) == 'external' else '')
            gantt_tasks.append({
                'id': f'item-{item.id}',
                'name': f'Item: {item.title}',
                'start': item_start,
                'end': item_end,
                'progress': 0,
                'custom_class': item_class
            })
            for sub in item.subitems:
                sub_start = sub.start_date if isinstance(sub.start_date, str) else str(sub.start_date)
                sub_end = (datetime.strptime(sub_start, '%Y-%m-%d') + timedelta(days=int(sub.duration))).strftime('%Y-%m-%d')
                sub_class = 'subitem-bar' + (' external-bar' if getattr(sub, 'internal_external', None) == 'external' else '')
                gantt_tasks.append({
                    'id': f'subitem-{sub.id}',
                    'name': f'Sub: {sub.title}',
                    'start': sub_start,
                    'end': sub_end,
                    'progress': 0,
                    'custom_class': sub_class
                })
    critical_path_ids = compute_critical_path(gantt_tasks)
    # Annotate tasks with critical path class
    crit_set = set(critical_path_ids)
    for t in gantt_tasks:
        if t['id'] in crit_set:
            existing = t.get('custom_class','')
            t['custom_class'] = (existing + ' critical-path').strip()
    gantt_json_js = json.dumps(gantt_tasks)
    # Draft (holding) parts
    draft_parts = DraftPart.query.order_by(DraftPart.created_at.asc()).all()
    draft_json_js = json.dumps([
        {
            'id': d.id,
            'title': d.title,
            'type': d.part_type,
            'internal_external': d.internal_external,
            'project_id': d.project_id
        } for d in draft_parts
    ])

    # Build calendar events in Python
    calendar_events = []
    for phase in phases:
        phase_start = phase.start_date if isinstance(phase.start_date, str) else str(phase.start_date)
        phase_end = (datetime.strptime(phase_start, '%Y-%m-%d') + timedelta(days=int(phase.duration))).strftime('%Y-%m-%d')
        calendar_events.append({
            'title': f'Phase: {phase.title}',
            'start': phase_start,
            'end': phase_end,
            'color': '#4B4B4B' if getattr(phase, 'internal_external', None) == 'external' else '#FF8200'
        })
        for item in phase.items:
            item_start = item.start_date if isinstance(item.start_date, str) else str(item.start_date)
            item_end = (datetime.strptime(item_start, '%Y-%m-%d') + timedelta(days=int(item.duration))).strftime('%Y-%m-%d')
            calendar_events.append({
                'title': f'Item: {item.title}',
                'start': item_start,
                'end': item_end,
                'color': '#4B4B4B' if getattr(item, 'internal_external', None) == 'external' else '#FF8200'
            })
    calendar_events_json = json.dumps(calendar_events)
    images = Image.query.all()
    active_usernames = _get_active_usernames()
    critical_filter_active = session.get('critical_filter') == 'on'
    return render_template('index.html', projects=projects, phases=phases, items=items, subitems=subitems, images=images, uploads_folder=UPLOAD_FOLDER, gantt_json_js=gantt_json_js, draft_json_js=draft_json_js, calendar_events_json=calendar_events_json, critical_path_ids=critical_path_ids, active_usernames=active_usernames, critical_filter_active=critical_filter_active, selected_project_id=selected_project_id)

@main.route('/create_draft_part', methods=['POST'])
@login_required
def create_draft_part():
    title = request.form.get('draft-title')
    part_type = request.form.get('draft-type')
    internal_external = request.form.get('draft-internal-external') or 'internal'
    if not title or not part_type:
        return {'error':'Missing title or type'}, 400
    # Enforce project selection context
    selected_project_id = session.get('selected_project_id')
    if not selected_project_id:
        return {'error':'Select a project first'}, 400
    # For phase drafts we attach project_id now; for item/subitem we still record project for context
    draft = DraftPart(title=title, part_type=part_type, internal_external=internal_external, project_id=selected_project_id)
    db.session.add(draft); db.session.commit()
    return {'status':'ok','draft':{'id':draft.id,'title':draft.title,'type':draft.part_type,'internal_external':draft.internal_external,'project_id':draft.project_id}}, 200

@main.route('/promote_draft/<int:draft_id>', methods=['POST'])
@login_required
def promote_draft(draft_id):
    draft = DraftPart.query.get_or_404(draft_id)
    part_type = draft.part_type
    project_id = request.form.get('project-id')
    phase_id = request.form.get('phase-id')
    item_id = request.form.get('item-id')
    start = request.form.get('start-date')
    duration = request.form.get('duration')
    if not start or not duration:
        return {'error':'Start and duration required to promote'}, 400
    try:
        start_obj = datetime.strptime(start, '%Y-%m-%d').date(); dur = int(duration)
    except Exception:
        return {'error':'Invalid date/duration'}, 400
    created=None
    parent_ids={}
    if part_type=='phase':
        if not project_id: return {'error':'Project required'}, 400
        created = Phase(title=draft.title,start_date=start_obj,duration=dur,project_id=project_id,internal_external=draft.internal_external,is_milestone=False)
        db.session.add(created)
        parent_ids['project_id']=project_id
    elif part_type=='item':
        if not phase_id: return {'error':'Phase required'}, 400
        created = Item(title=draft.title,start_date=start_obj,duration=dur,phase_id=phase_id,internal_external=draft.internal_external,is_milestone=False)
        db.session.add(created); db.session.flush(); _enforce_dependencies_and_containment(created)
        parent_ids['phase_id']=phase_id
    elif part_type=='subitem':
        if not item_id: return {'error':'Item required'}, 400
        created = SubItem(title=draft.title,start_date=start_obj,duration=dur,item_id=item_id,internal_external=draft.internal_external,is_milestone=False)
        db.session.add(created); db.session.flush(); _enforce_dependencies_and_containment(created)
        parent_ids['item_id']=item_id
    else:
        return {'error':'Unknown type'}, 400
    db.session.delete(draft); db.session.commit()
    end = (start_obj + timedelta(days=dur)).strftime('%Y-%m-%d')
    cid = ('phase-' if part_type=='phase' else 'item-' if part_type=='item' else 'subitem-') + str(created.id)
    # Build hierarchy snippet similar to unified create handler
    snippet=''
    if part_type=='phase':
        snippet=(f'<div style="margin:4px 0;" data-wrapper="phase-{created.id}">'
                 f'<div class="node-line assoc-node" data-type="phase" data-id="{created.id}">'
                 f'<span class="tree-toggle" onclick="toggleNode(this)">[–]</span>'
                 f'<strong>Phase:</strong> {created.title} '
                 f'<span class="meta">{created.start_date} / {created.duration}d</span>'
                 f'<span class="actions"><button type="button" class="small" disabled>Edit</button></span>'
                 '</div>'
                 f'<div class="tree-children" data-phase-children="{created.id}"></div>'
                 '</div>')
    elif part_type=='item':
        snippet=(f'<div style="margin:4px 0;" data-wrapper="item-{created.id}">'
                 f'<div class="node-line assoc-node" data-type="item" data-id="{created.id}">'
                 f'<span class="tree-toggle" onclick="toggleNode(this)">[–]</span>'
                 f'<strong>Item:</strong> {created.title} '
                 f'<span class="meta">{created.start_date} / {created.duration}d</span>'
                 f'<span class="actions"><button type="button" class="small" disabled>Edit</button></span>'
                 '</div>'
                 f'<div class="tree-children" data-item-children="{created.id}"></div>'
                 '</div>')
    elif part_type=='subitem':
        snippet=(f'<div style="margin:4px 0;" data-wrapper="subitem-{created.id}">'
                 f'<div class="node-line assoc-node" data-type="subitem" data-id="{created.id}">'
                 f'<strong>Sub:</strong> {created.title} '
                 f'<span class="meta">{created.start_date} / {created.duration}d</span>'
                 '</div>'
                 '</div>')
    return {'status':'ok','part_type':part_type,'task':{'id':cid,'name':('Phase: ' if part_type=='phase' else 'Item: ' if part_type=='item' else 'Sub: ')+draft.title,'start':start,'end':end,'duration':dur,'custom_class':('phase-bar' if part_type=='phase' else 'item-bar' if part_type=='item' else 'subitem-bar') + (' external-bar' if created.internal_external=='external' else '')},'hierarchy_snippet':snippet,'parent_ids':parent_ids}, 200

@main.route('/reorder_phase', methods=['POST'])
@login_required
def reorder_phase():
    data = request.get_json() or {}
    phase_id = data.get('phase_id'); project_id = data.get('project_id'); new_position = data.get('new_position')
    if phase_id is None or project_id is None or new_position is None:
        return {'error':'missing fields'},400
    phase = Phase.query.get_or_404(int(phase_id))
    if str(phase.project_id)!=str(project_id):
        # move phase to new project
        phase.project_id = project_id
    siblings = Phase.query.filter_by(project_id=project_id).order_by(Phase.sort_order.asc(), Phase.id.asc()).all()
    # remove current phase from list (will reinsert)
    siblings = [p for p in siblings if p.id!=phase.id]
    new_position = max(0, min(len(siblings), int(new_position)))
    siblings.insert(new_position, phase)
    for idx, s in enumerate(siblings): s.sort_order = idx
    db.session.commit()
    return {'status':'ok'},200

@main.route('/reorder_item', methods=['POST'])
@login_required
def reorder_item():
    data = request.get_json() or {}
    item_id = data.get('item_id'); phase_id = data.get('phase_id'); new_position = data.get('new_position')
    if item_id is None or phase_id is None or new_position is None:
        return {'error':'missing fields'},400
    item = Item.query.get_or_404(int(item_id))
    if str(item.phase_id)!=str(phase_id):
        item.phase_id = phase_id
    siblings = Item.query.filter_by(phase_id=phase_id).order_by(Item.sort_order.asc(), Item.id.asc()).all()
    siblings = [i for i in siblings if i.id!=item.id]
    new_position = max(0, min(len(siblings), int(new_position)))
    siblings.insert(new_position, item)
    for idx, s in enumerate(siblings): s.sort_order = idx
    db.session.commit()
    return {'status':'ok'},200

@main.route('/reorder_subitem', methods=['POST'])
@login_required
def reorder_subitem():
    data = request.get_json() or {}
    sub_id = data.get('subitem_id'); item_id = data.get('item_id'); new_position = data.get('new_position')
    if sub_id is None or item_id is None or new_position is None:
        return {'error':'missing fields'},400
    sub = SubItem.query.get_or_404(int(sub_id))
    if str(sub.item_id)!=str(item_id):
        sub.item_id = item_id
    siblings = SubItem.query.filter_by(item_id=item_id).order_by(SubItem.sort_order.asc(), SubItem.id.asc()).all()
    siblings = [s for s in siblings if s.id!=sub.id]
    new_position = max(0, min(len(siblings), int(new_position)))
    siblings.insert(new_position, sub)
    for idx, s in enumerate(siblings): s.sort_order = idx
    db.session.commit()
    return {'status':'ok'},200

@main.route('/export_calendar_ics')
@login_required
def export_calendar_ics():
    """Export current (filtered) phases, items, and subitems as an ICS (Outlook) calendar."""
    selected_project_id = session.get('selected_project_id')
    if selected_project_id:
        phases = Phase.query.filter_by(project_id=selected_project_id).all()
    else:
        phases = Phase.query.all()
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//PlanningApp//EN',
        'CALSCALE:GREGORIAN'
    ]
    def add_event(uid_prefix, title, start_date, duration):
        try:
            s = start_date if isinstance(start_date, str) else str(start_date)
            from datetime import datetime as _dt, timedelta as _td
            d1 = _dt.strptime(s, '%Y-%m-%d')
            d2 = d1 + _td(days=int(duration))
            # ICS all-day DTEND is non-inclusive -> add one more day
            dtstart = d1.strftime('%Y%m%d')
            dtend = (d2).strftime('%Y%m%d')
            uid = f"{uid_prefix}-{dtstart}@planningapp"
            summary = title.replace('\n',' ').replace('\r',' ')
            lines.extend([
                'BEGIN:VEVENT',
                f'UID:{uid}',
                f"DTSTAMP:{_dt.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                f'DTSTART;VALUE=DATE:{dtstart}',
                f'DTEND;VALUE=DATE:{dtend}',
                f'SUMMARY:{summary}',
                'END:VEVENT'
            ])
        except Exception:
            pass
    for ph in phases:
        add_event(f'phase-{ph.id}', f'Phase: {ph.title}', ph.start_date, ph.duration)
        for it in ph.items:
            add_event(f'item-{it.id}', f'Item: {it.title}', it.start_date, it.duration)
            for sub in it.subitems:
                add_event(f'subitem-{sub.id}', f'Sub: {sub.title}', sub.start_date, sub.duration)
    lines.append('END:VCALENDAR')
    ics_data = '\r\n'.join(lines)
    from flask import Response
    return Response(ics_data, mimetype='text/calendar', headers={'Content-Disposition':'attachment; filename="planning_export.ics"'})

@main.route('/active_users')
@login_required
def active_users():
    return {'users': _get_active_usernames()}

@main.route('/healthz')
def healthz():
    """Basic health check for uptime monitors (no auth)."""
    try:
        # Simple DB check
        db.session.execute('SELECT 1')
        return {'status':'ok'}, 200
    except Exception:
        return {'status':'degraded'}, 500

@main.route('/set_critical_filter', methods=['POST'])
@login_required
def set_critical_filter():
    state = request.json.get('state') if request.is_json else request.form.get('state')
    if state in ('on','off'):
        session['critical_filter'] = state
        return {'status':'ok','state':state}
    return {'error':'invalid state'}, 400

@main.route('/export_critical_csv')
@login_required
def export_critical_csv():
    # Build current tasks (phases + items + subitems) & compute critical again to ensure up-to-date
    phases = Phase.query.all()
    tasks = []
    from datetime import datetime as _dt
    for ph in phases:
        p_start = str(ph.start_date)
        p_end = (ph.start_date + timedelta(days=ph.duration)).strftime('%Y-%m-%d')
        tasks.append({'id': f'phase-{ph.id}', 'start': p_start, 'end': p_end, 'dependencies': ''})
        for it in ph.items:
            i_start = str(it.start_date)
            i_end = (it.start_date + timedelta(days=it.duration)).strftime('%Y-%m-%d')
            tasks.append({'id': f'item-{it.id}', 'start': i_start, 'end': i_end, 'dependencies': it.dependencies or ''})
    cp_ids = compute_critical_path(tasks)
    # Map id -> object/type/title/dates
    rows = []
    order_map = {tid: idx+1 for idx, tid in enumerate(cp_ids)}
    for tid in cp_ids:
        if tid.startswith('phase-'):
            obj = Phase.query.get(int(tid.split('-')[1]))
            if obj:
                rows.append(('Phase', order_map[tid], obj.title, obj.start_date, obj.duration))
        elif tid.startswith('item-'):
            obj = Item.query.get(int(tid.split('-')[1]))
            if obj:
                rows.append(('Item', order_map[tid], obj.title, obj.start_date, obj.duration))
    import csv, io
    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(['Type','Order','Title','Start','Duration (days)'])
    for r in rows:
        w.writerow(r)
    csv_bytes = io.BytesIO(sio.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    return send_file(csv_bytes, mimetype='text/csv', as_attachment=True, download_name='critical_path.csv')

@main.route('/power_t_inline')
def power_t_inline():
    # Quick inline SVG fallback response
    svg_path = os.path.join(current_app.root_path, '..', 'static', 'Power_T.svg')
    if os.path.exists(svg_path):
        return send_file(svg_path, mimetype='image/svg+xml')
    # minimal inline T shape fallback
    fallback = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 70'><rect width='120' height='70' fill='#FF8200'/><rect x='50' y='20' width='20' height='40' fill='#fff'/></svg>"""
    return fallback, 200, { 'Content-Type':'image/svg+xml' }

@main.route('/lsi_logo')
def lsi_logo():
    """Serve LSI_Graphics_OE.png from repo root; provide tiny transparent fallback if missing."""
    png_path = os.path.abspath(os.path.join(current_app.root_path, '..', 'LSI_Graphics_OE.png'))
    if os.path.exists(png_path):
        try:
            return send_file(png_path, mimetype='image/png')
        except Exception as e:
            print('Error sending LSI logo:', e)
    # 1x1 transparent PNG fallback
    transparent_png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`````\x00\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    return send_file(io.BytesIO(transparent_png), mimetype='image/png')

@main.route('/debug_lsi_logo')
@login_required
def debug_lsi_logo():
    """Return JSON diagnostics about LSI logo availability (admin only)."""
    if not current_user.is_admin:
        return {'error':'admin required'}, 403
    repo_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
    paths = {
        'static_config': current_app.static_folder,
        'expected_static_file': os.path.join(current_app.static_folder, 'LSI_Graphics_OE.png'),
        'legacy_root_file': os.path.join(repo_root, 'LSI_Graphics_OE.png')
    }
    exists = { k: os.path.exists(v) for k,v in paths.items() }
    return { 'paths': paths, 'exists': exists }

@main.route('/admin/run_migrations')
@login_required
def run_migrations():
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    from sqlalchemy import text
    added = []
    try:
        engine = db.engine
        def ensure(table,col_def):
            col = col_def.split()[0]
            with engine.connect() as conn:
                info = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in info}
                if col not in existing:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                        added.append(f"{table}.{col}")
                    except Exception:
                        pass
        ensure('phase','notes TEXT')
        ensure('item','notes TEXT')
        ensure('sub_item','notes TEXT')
    except Exception as e:
        flash(f'Migration error: {e}')
        return redirect(url_for('main.index'))
    if added:
        flash('Added columns: ' + ', '.join(added))
    else:
        flash('No migration changes needed.')
    return redirect(url_for('main.index'))

@main.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('main.index'))
    files = request.files.getlist('file')
    if not files:
        flash('No files selected')
        return redirect(url_for('main.index'))
    association_type = request.form.get('association-type')  # deprecated (single-link); retained for backward compatibility but ignored
    association_id = request.form.get('association-id')
    uploaded = 0
    for file in files:
        if not file or file.filename == '':
            continue
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            project_id = session.get('selected_project_id')
            # Initial creation without part links; use /associate_image or batch endpoint afterwards
            img = Image(filename=filename, project_id=project_id)
            db.session.add(img)
            uploaded += 1
    if uploaded:
        db.session.commit()
        flash(f'Uploaded {uploaded} file(s)')
    else:
        flash('No valid files uploaded')
    return redirect(url_for('main.index'))

@main.route('/associate_image', methods=['POST'])
@login_required
def associate_image():
    data = request.get_json() or {}
    image_id = data.get('image_id')
    target_type = data.get('target_type')
    target_id = data.get('target_id')
    if not all([image_id, target_type, target_id]):
        return {'error':'missing fields'}, 400
    img = Image.query.get(image_id)
    if not img:
        return {'error':'not found'}, 404
    try:
        added = False
        if target_type=='phase':
            ph = Phase.query.get(int(target_id))
            if not ph: return {'error':'phase not found'},404
            if ph not in img.phases:
                img.phases.append(ph); added=True
        elif target_type=='item':
            it = Item.query.get(int(target_id))
            if not it: return {'error':'item not found'},404
            if it not in img.items:
                img.items.append(it); added=True
        elif target_type=='subitem':
            si = SubItem.query.get(int(target_id))
            if not si: return {'error':'subitem not found'},404
            if si not in img.subitems:
                img.subitems.append(si); added=True
        else:
            return {'error':'bad target_type'},400
        db.session.commit()
        return {'status':'ok','image_id':img.id,'target_type':target_type,'target_id':target_id,'added':added}
    except Exception:
        db.session.rollback()
        return {'error':'associate failed'}, 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main.route('/uploads/<filename>')
def uploaded_file(filename):
    import os
    abs_file_path = os.path.join(UPLOAD_FOLDER, filename)
    print(f"Serving image: {abs_file_path}")
    if not os.path.exists(abs_file_path):
        print(f"File not found: {abs_file_path}")
        from flask import abort
        abort(404)
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
    notes = request.form.get('phase-notes')
    if title and start_date and duration and project_id:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        phase = Phase(title=title, start_date=start_date_obj, duration=duration, is_milestone=is_milestone, internal_external=internal_external, project_id=project_id, notes=notes)
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
    notes = request.form.get('item-notes')
    if title and start_date and duration and phase_id:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        item = Item(title=title, start_date=start_date_obj, duration=int(duration), dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, phase_id=phase_id, notes=notes)
        db.session.add(item)
        db.session.flush()
        _enforce_dependencies_and_containment(item)
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
    notes = request.form.get('subitem-notes')
    if title and start_date and duration and item_id:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        subitem = SubItem(title=title, start_date=start_date_obj, duration=int(duration), dependencies=dependencies, is_milestone=is_milestone, internal_external=internal_external, item_id=item_id, notes=notes)
        db.session.add(subitem)
        db.session.flush()
        _enforce_dependencies_and_containment(subitem)
        db.session.commit()
        flash('Sub-Item added!')
    return redirect(url_for('main.index'))

# Unified creation endpoint for phases, items, and subitems
@main.route('/create_part', methods=['POST'])
@login_required
def create_part():
    """Create a phase, item, or subitem from a single unified form.
    Expected form fields:
      part-type: phase|item|subitem
      part-title, part-start (YYYY-MM-DD), part-duration (int)
      part-milestone (optional checkbox), part-internal-external (internal|external)
      part-dependencies (optional, items & subitems only)
      project-id (for phase), phase-id (for item), item-id (for subitem)
      part-notes (optional)
    """
    ptype = request.form.get('part-type')
    title = request.form.get('part-title')
    start_date = request.form.get('part-start')
    duration = request.form.get('part-duration')
    is_milestone = bool(request.form.get('part-milestone'))
    internal_external = request.form.get('part-internal-external') or 'internal'
    dependencies = (request.form.get('part-dependencies') or '').strip()
    notes = request.form.get('part-notes')
    if not (ptype and title and start_date and duration):
        flash('Missing required fields.')
        return redirect(url_for('main.index'))
    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_val = int(duration)
    except Exception:
        flash('Invalid date or duration.')
        return redirect(url_for('main.index'))
    ajax = 'application/json' in (request.headers.get('Accept','').lower()) or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    created_obj = None
    parent_ids = {}
    try:
        if ptype == 'phase':
            # Accept explicit form project-id or fall back to session selection
            project_id = request.form.get('project-id') or session.get('selected_project_id')
            if not project_id:
                if not ajax: flash('Project is required for a phase.')
                return ( {'error':'Project required'}, 400 ) if ajax else redirect(url_for('main.index'))
            created_obj = Phase(title=title, start_date=start_date_obj, duration=duration_val,
                                is_milestone=is_milestone, internal_external=internal_external,
                                project_id=project_id, notes=notes)
            db.session.add(created_obj)
            db.session.commit()
            parent_ids['project_id'] = project_id
            if not ajax: flash('Phase added!')
        elif ptype == 'item':
            phase_id = request.form.get('phase-id')
            if not phase_id:
                if not ajax: flash('Phase is required for an item.')
                return ( {'error':'Phase required'}, 400 ) if ajax else redirect(url_for('main.index'))
            created_obj = Item(title=title, start_date=start_date_obj, duration=duration_val,
                               dependencies=dependencies, is_milestone=is_milestone,
                               internal_external=internal_external, phase_id=phase_id, notes=notes)
            db.session.add(created_obj); db.session.flush(); _enforce_dependencies_and_containment(created_obj); db.session.commit()
            parent_ids['phase_id'] = phase_id
            if not ajax: flash('Item added!')
        elif ptype == 'subitem':
            item_id = request.form.get('item-id')
            if not item_id:
                if not ajax: flash('Item is required for a sub-item.')
                return ( {'error':'Item required'}, 400 ) if ajax else redirect(url_for('main.index'))
            created_obj = SubItem(title=title, start_date=start_date_obj, duration=duration_val,
                                  dependencies=dependencies, is_milestone=is_milestone,
                                  internal_external=internal_external, item_id=item_id, notes=notes)
            db.session.add(created_obj); db.session.flush(); _enforce_dependencies_and_containment(created_obj); db.session.commit()
            parent_ids['item_id'] = item_id
            if not ajax: flash('Sub-Item added!')
        else:
            if not ajax: flash('Unknown part type.')
            return ( {'error':'Unknown part type'}, 400 ) if ajax else redirect(url_for('main.index'))
    except Exception:
        db.session.rollback()
        if ajax:
            return {'error':'Creation failed'}, 500
        else:
            flash('Error creating part.')
            return redirect(url_for('main.index'))

    if not ajax:
        return redirect(url_for('main.index'))

    # Build snippet HTML patterns matching existing structure (minimal)
    snippet = ''
    obj_id = None
    if isinstance(created_obj, Phase):
        obj_id = f'phase-{created_obj.id}'
        snippet = (
            f'<div style="margin:4px 0;" data-wrapper="phase-{created_obj.id}">'
            f'<div class="node-line assoc-node" data-type="phase" data-id="{created_obj.id}">' \
            f'<span class="tree-toggle" onclick="toggleNode(this)">[–]</span>' \
            f'<strong>Phase:</strong> {created_obj.title} ' \
            f'<span class="meta">{created_obj.start_date} / {created_obj.duration}d</span>' \
            f'<span class="actions"><button type="button" class="small" disabled>Edit</button></span>' \
            '</div>' \
            f'<div class="tree-children" data-phase-children="{created_obj.id}"></div>' \
            '</div>'
        )
    elif isinstance(created_obj, Item):
        obj_id = f'item-{created_obj.id}'
        snippet = (
            f'<div style="margin:4px 0;" data-wrapper="item-{created_obj.id}">'
            f'<div class="node-line assoc-node" data-type="item" data-id="{created_obj.id}">' \
            f'<span class="tree-toggle" onclick="toggleNode(this)">[–]</span>' \
            f'<strong>Item:</strong> {created_obj.title} ' \
            f'<span class="meta">{created_obj.start_date} / {created_obj.duration}d</span>' \
            f'<span class="actions"><button type="button" class="small" disabled>Edit</button></span>' \
            '</div>' \
            f'<div class="tree-children" data-item-children="{created_obj.id}"></div>' \
            '</div>'
        )
    elif isinstance(created_obj, SubItem):
        obj_id = f'subitem-{created_obj.id}'
        snippet = (
            f'<div style="margin:4px 0;" data-wrapper="subitem-{created_obj.id}">'
            f'<div class="node-line assoc-node" data-type="subitem" data-id="{created_obj.id}">' \
            f'<strong>Sub:</strong> {created_obj.title} ' \
            f'<span class="meta">{created_obj.start_date} / {created_obj.duration}d</span>' \
            '</div>' \
            '</div>'
        )

    # Recompute critical path (phases + items)
    phases_all = Phase.query.all()
    tasks_for_cp = []
    for ph in phases_all:
        p_start = str(ph.start_date)
        p_end = (ph.start_date + timedelta(days=ph.duration)).strftime('%Y-%m-%d')
        tasks_for_cp.append({'id': f'phase-{ph.id}', 'start': p_start, 'end': p_end, 'dependencies': ''})
        for it in ph.items:
            i_start = str(it.start_date)
            i_end = (it.start_date + timedelta(days=it.duration)).strftime('%Y-%m-%d')
            tasks_for_cp.append({'id': f'item-{it.id}', 'start': i_start, 'end': i_end, 'dependencies': it.dependencies or ''})
    cp_ids = compute_critical_path(tasks_for_cp)

    # Build task object for front-end
    start_final = str(created_obj.start_date)
    end_final = (created_obj.start_date + timedelta(days=created_obj.duration)).strftime('%Y-%m-%d')
    custom_class = ('phase-bar' if isinstance(created_obj, Phase) else 'item-bar' if isinstance(created_obj, Item) else 'subitem-bar')
    if getattr(created_obj, 'internal_external', None) == 'external':
        custom_class += ' external-bar'

    return {
        'status':'ok',
        'part_type': ptype,
        'task': {
            'id': obj_id,
            'name': ('Phase: ' if isinstance(created_obj, Phase) else 'Item: ' if isinstance(created_obj, Item) else 'Sub: ') + created_obj.title,
            'start': start_final,
            'end': end_final,
            'duration': created_obj.duration,
            'custom_class': custom_class
        },
        'hierarchy_snippet': snippet,
        'parent_ids': parent_ids,
        'critical_path': cp_ids
    }, 200

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

@main.route('/revoke_admin/<int:user_id>')
@login_required
def revoke_admin(user_id):
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    user = User.query.get(user_id)
    if user and user.id != current_user.id:  # prevent self-revoke
        user.is_admin = False
        db.session.commit()
        flash(f'Admin rights revoked for {user.username}.')
    else:
        flash('Cannot revoke this user.')
    return redirect(url_for('main.admin_users'))

@main.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    q = request.args.get('q','').strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(User.username.ilike(like))
    users = query.order_by(User.username.asc()).all()
    return render_template('admin_users.html', users=users, q=q)

@main.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
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

@main.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    # Basic session-based throttle
    import time
    MAX_ATTEMPTS = 5
    LOCK_SECONDS = 300
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
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
            return redirect(url_for('main.index'))
        attempts += 1
        session['login_attempts'] = attempts
        remaining = MAX_ATTEMPTS - attempts
        if remaining <= 0:
            session['login_lock_until'] = time.time() + LOCK_SECONDS
            flash('Account locked for 5 minutes due to repeated failures.')
        else:
            flash(f'Invalid credentials. {remaining} attempts left.')
        return redirect(url_for('main.login'))
    return render_template('login.html')

@main.route('/signin', methods=['GET','POST'])
def signin():
    return login()

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

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('main.login'))

@main.route('/change_password', methods=['GET','POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old = request.form.get('old-password')
        new = request.form.get('new-password')
        confirm = request.form.get('confirm-password')
        if not old or not new or not confirm:
            flash('All fields required')
            return redirect(url_for('main.change_password'))
        if not check_password_hash(current_user.password_hash, old):
            flash('Current password incorrect')
            return redirect(url_for('main.change_password'))
        if new != confirm:
            flash('Passwords do not match')
            return redirect(url_for('main.change_password'))
        if len(new) < 6:
            flash('Password must be at least 6 characters')
            return redirect(url_for('main.change_password'))
        current_user.password_hash = generate_password_hash(new)
        db.session.commit()
        flash('Password updated')
        return redirect(url_for('main.index'))
    return render_template('change_password.html')

@main.route('/admin/create_user', methods=['POST'])
@login_required
def admin_create_user():
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    username = request.form.get('new-username')
    password = request.form.get('new-password')
    if not username or not password:
        flash('Username and password required')
        return redirect(url_for('main.admin_users'))
    if User.query.filter_by(username=username).first():
        flash('Username already exists')
        return redirect(url_for('main.admin_users'))
    if len(password) < 6:
        flash('Password must be at least 6 characters')
        return redirect(url_for('main.admin_users'))
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    flash('User created')
    return redirect(url_for('main.admin_users'))

@main.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    if current_user.id == user_id:
        flash('You cannot delete yourself.')
        return redirect(url_for('main.admin_users'))
    user = User.query.get_or_404(user_id)
    if user.projects and len(user.projects) > 0:
        flash('Cannot delete user who owns projects.')
        return redirect(url_for('main.admin_users'))
    db.session.delete(user)
    db.session.commit()
    flash('User deleted')
    return redirect(url_for('main.admin_users'))

@main.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@login_required
def admin_reset_password(user_id):
    if not current_user.is_admin:
        flash('Admin access required.')
        return redirect(url_for('main.index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Use Change Password for your own account.')
        return redirect(url_for('main.admin_users'))
    new_pw = request.form.get('new-password')
    if not new_pw or len(new_pw) < 6:
        flash('Provide a new password (min 6 chars).')
        return redirect(url_for('main.admin_users'))
    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    flash(f'Password reset for {user.username}.')
    return redirect(url_for('main.admin_users'))

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
    notes = request.form.get('phase-notes')
    if title and start_date and duration:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_int = int(duration)
        phase.title = title
        phase.start_date = start_date_obj
        phase.duration = duration_int
        phase.is_milestone = is_milestone
        phase.internal_external = internal_external
        if notes is not None:
            phase.notes = notes
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
    notes = request.form.get('item-notes')
    if title and start_date and duration:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_int = int(duration)
        item.title = title
        item.start_date = start_date_obj
        item.duration = duration_int
        item.dependencies = dependencies
        item.is_milestone = is_milestone
        item.internal_external = internal_external
        if notes is not None:
            item.notes = notes
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

@main.route('/edit_subitem/<int:subitem_id>', methods=['POST'])
@login_required
def edit_subitem(subitem_id):
    subitem = SubItem.query.get_or_404(subitem_id)
    title = request.form.get('subitem-title')
    start_date = request.form.get('subitem-start')
    duration = request.form.get('subitem-duration')
    dependencies = request.form.get('subitem-dependencies')
    is_milestone = bool(request.form.get('subitem-milestone'))
    internal_external = request.form.get('subitem-type')
    notes = request.form.get('subitem-notes')
    if title and start_date and duration:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        duration_int = int(duration)
        subitem.title = title
        subitem.start_date = start_date_obj
        subitem.duration = duration_int
        subitem.dependencies = dependencies
        subitem.is_milestone = is_milestone
        subitem.internal_external = internal_external
        if notes is not None:
            subitem.notes = notes
        db.session.commit()
        flash('Sub-Item updated!')
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

@main.route('/delete_image/<int:image_id>', methods=['POST'])
@login_required
def delete_image(image_id):
    img = Image.query.get_or_404(image_id)
    # Remove file from disk
    import os
    file_path = os.path.join(current_app.root_path, 'uploads', img.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    # Remove from DB
    db.session.delete(img)
    db.session.commit()
    return redirect(request.referrer or url_for('main.index'))

@main.route('/unlink_image', methods=['POST'])
@login_required
def unlink_image():
    data = request.get_json() or {}
    image_id = data.get('image_id')
    context_type = data.get('context_type')  # phase|item|subitem
    context_id = data.get('context_id')
    if not image_id:
        return {'error':'image_id required'}, 400
    img = Image.query.get(image_id)
    if not img:
        return {'error':'not found'}, 404
    # Only clear the association that matches the provided context (if supplied)
    changed = False
    try:
        if context_type == 'phase' and context_id:
            ph = Phase.query.get(int(context_id))
            if ph and ph in img.phases:
                img.phases.remove(ph); changed=True
        elif context_type == 'item' and context_id:
            it = Item.query.get(int(context_id))
            if it and it in img.items:
                img.items.remove(it); changed=True
        elif context_type == 'subitem' and context_id:
            si = SubItem.query.get(int(context_id))
            if si and si in img.subitems:
                img.subitems.remove(si); changed=True
        elif not context_type:  # fallback: clear all links
            if img.phases or img.items or img.subitems:
                img.phases.clear(); img.items.clear(); img.subitems.clear(); changed=True
        if changed:
            db.session.commit()
        return {'status':'ok','image_id':img.id,'cleared':changed}
    except Exception:
        db.session.rollback()
        return {'error':'unlink failed'}, 500

@main.route('/image_links/<int:image_id>')
@login_required
def image_links(image_id):
    img = Image.query.get_or_404(image_id)
    def simple_phase(p): return {'id':p.id,'title':p.title,'type':'phase'}
    def simple_item(i): return {'id':i.id,'title':i.title,'type':'item'}
    def simple_sub(s): return {'id':s.id,'title':s.title,'type':'subitem'}
    data = {
        'image_id': img.id,
        'filename': img.filename,
        'project_id': img.project_id,
        'phases': [simple_phase(p) for p in img.phases],
        'items': [simple_item(i) for i in img.items],
        'subitems': [simple_sub(s) for s in img.subitems]
    }
    return data

@main.route('/batch_associate_images', methods=['POST'])
@login_required
def batch_associate_images():
    data = request.get_json() or {}
    links = data.get('links')  # list of {image_id, target_type, target_id}
    if not isinstance(links, list):
        return {'error':'links list required'}, 400
    results=[]; errors=0
    for link in links:
        iid = link.get('image_id'); ttype=link.get('target_type'); tid=link.get('target_id')
        if not all([iid,ttype,tid]):
            results.append({'image_id':iid,'status':'skipped','reason':'missing field'}); errors+=1; continue
        img = Image.query.get(iid)
        if not img:
            results.append({'image_id':iid,'status':'skipped','reason':'image not found'}); errors+=1; continue
        try:
            added=False
            if ttype=='phase':
                ph=Phase.query.get(int(tid));
                if ph and ph not in img.phases: img.phases.append(ph); added=True
            elif ttype=='item':
                it=Item.query.get(int(tid));
                if it and it not in img.items: img.items.append(it); added=True
            elif ttype=='subitem':
                si=SubItem.query.get(int(tid));
                if si and si not in img.subitems: img.subitems.append(si); added=True
            else:
                results.append({'image_id':iid,'status':'skipped','reason':'bad target_type'}); errors+=1; continue
            results.append({'image_id':iid,'status':'ok','added':added})
        except Exception as e:
            results.append({'image_id':iid,'status':'error','reason':str(e)}); errors+=1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback(); return {'error':'commit failed','results':results}, 500
    return {'results':results,'errors':errors}

@main.route('/batch_unassociate_images', methods=['POST'])
@login_required
def batch_unassociate_images():
    data = request.get_json() or {}
    links = data.get('links')  # list of {image_id, context_type, context_id}
    if not isinstance(links, list):
        return {'error':'links list required'}, 400
    results=[]; errors=0
    for link in links:
        iid=link.get('image_id'); ctype=link.get('context_type'); cid=link.get('context_id')
        if not iid:
            results.append({'image_id':iid,'status':'skipped','reason':'missing image_id'}); errors+=1; continue
        img=Image.query.get(iid)
        if not img:
            results.append({'image_id':iid,'status':'skipped','reason':'image not found'}); errors+=1; continue
        try:
            changed=False
            if ctype=='phase' and cid:
                ph=Phase.query.get(int(cid));
                if ph and ph in img.phases: img.phases.remove(ph); changed=True
            elif ctype=='item' and cid:
                it=Item.query.get(int(cid));
                if it and it in img.items: img.items.remove(it); changed=True
            elif ctype=='subitem' and cid:
                si=SubItem.query.get(int(cid));
                if si and si in img.subitems: img.subitems.remove(si); changed=True
            elif not ctype: # clear all
                if img.phases or img.items or img.subitems:
                    img.phases.clear(); img.items.clear(); img.subitems.clear(); changed=True
            else:
                results.append({'image_id':iid,'status':'skipped','reason':'bad context_type'}); errors+=1; continue
            results.append({'image_id':iid,'status':'ok','cleared':changed})
        except Exception as e:
            results.append({'image_id':iid,'status':'error','reason':str(e)}); errors+=1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback(); return {'error':'commit failed','results':results}, 500
    return {'results':results,'errors':errors}

@main.route('/export_project/<int:project_id>')
@login_required
def export_project(project_id):
    project = Project.query.get_or_404(project_id)
    # Prepare CSV data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'ID', 'Title', 'Start Date', 'Duration', 'Dependencies', 'Milestone', 'Internal/External', 'Parent ID', 'Notes'])
    writer.writerow(['Project', project.id, project.title, '', '', '', '', '', '', ''])
    for phase in project.phases:
        writer.writerow(['Phase', phase.id, phase.title, phase.start_date, phase.duration, '', phase.is_milestone, phase.internal_external, project.id, (phase.notes or '')])
        for item in phase.items:
            writer.writerow(['Item', item.id, item.title, item.start_date, item.duration, item.dependencies, item.is_milestone, item.internal_external, phase.id, (item.notes or '')])
            for subitem in item.subitems:
                writer.writerow(['SubItem', subitem.id, subitem.title, subitem.start_date, subitem.duration, subitem.dependencies, subitem.is_milestone, subitem.internal_external, item.id, (subitem.notes or '')])
    csv_bytes = io.BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    # Prepare ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        zipf.writestr('project_data.csv', csv_bytes.read())
        # Add images
        # Collect unique image filenames across many-to-many relations
        added=set()
        for phase in project.phases:
            for img in getattr(phase,'images_multi',[]):
                if img.filename in added: continue
                img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                if os.path.exists(img_path):
                    zipf.write(img_path, f'images/{img.filename}'); added.add(img.filename)
            for item in phase.items:
                for img in getattr(item,'images_multi',[]):
                    if img.filename in added: continue
                    img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                    if os.path.exists(img_path):
                        zipf.write(img_path, f'images/{img.filename}'); added.add(img.filename)
                for subitem in item.subitems:
                    for img in getattr(subitem,'images_multi',[]):
                        if img.filename in added: continue
                        img_path = os.path.join(UPLOAD_FOLDER, img.filename)
                        if os.path.exists(img_path):
                            zipf.write(img_path, f'images/{img.filename}'); added.add(img.filename)
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f'project_{project.id}_export.zip')

@main.route('/init_sample_data')
@login_required
def init_sample_data():
    # Remove all existing data
    Image.query.delete()
    SubItem.query.delete()
    Item.query.delete()
    Phase.query.delete()
    Project.query.delete()
    db.session.commit()
    # Create sample project
    project = Project(title='Sample Project', owner_id=current_user.id)
    db.session.add(project)
    db.session.commit()
    # Create sample phases
    phase1 = Phase(title='Design', start_date='2025-09-01', duration=10, is_milestone=False, internal_external='internal', project_id=project.id)
    phase2 = Phase(title='Build', start_date='2025-09-11', duration=15, is_milestone=True, internal_external='external', project_id=project.id)
    db.session.add_all([phase1, phase2])
    db.session.commit()
    # Create sample items
    item1 = Item(title='Wireframes', start_date='2025-09-01', duration=5, dependencies='', is_milestone=False, internal_external='internal', phase_id=phase1.id)
    item2 = Item(title='Blueprints', start_date='2025-09-06', duration=5, dependencies='', is_milestone=True, internal_external='external', phase_id=phase1.id)
    item3 = Item(title='Foundation', start_date='2025-09-11', duration=7, dependencies='', is_milestone=False, internal_external='internal', phase_id=phase2.id)
    db.session.add_all([item1, item2, item3])
    db.session.commit()
    # Create sample sub-items
    subitem1 = SubItem(title='Sketch', start_date='2025-09-01', duration=2, dependencies='', is_milestone=False, internal_external='internal', item_id=item1.id)
    subitem2 = SubItem(title='CAD', start_date='2025-09-03', duration=3, dependencies='', is_milestone=True, internal_external='external', item_id=item1.id)
    subitem3 = SubItem(title='Pour Concrete', start_date='2025-09-11', duration=3, dependencies='', is_milestone=False, internal_external='internal', item_id=item3.id)
    db.session.add_all([subitem1, subitem2, subitem3])
    db.session.commit()
    # Add sample images (use placeholder images)
    # Download placeholder images if not present
    import requests
    import os
    img_urls = [
        'https://via.placeholder.com/80x80.png?text=Sample1',
        'https://via.placeholder.com/80x80.png?text=Sample2',
        'https://via.placeholder.com/80x80.png?text=Sample3'
    ]
    img_files = ['sample1.png', 'sample2.png', 'sample3.png']
    for url, fname in zip(img_urls, img_files):
        fpath = os.path.join(current_app.root_path, 'uploads', fname)
        if not os.path.exists(fpath):
            r = requests.get(url)
            if r.status_code == 200:
                with open(fpath, 'wb') as f:
                    f.write(r.content)
    img1 = Image(filename='sample1.png', item_id=item1.id)
    img2 = Image(filename='sample2.png', phase_id=phase2.id)
    img3 = Image(filename='sample3.png', subitem_id=subitem3.id)
    db.session.add_all([img1, img2, img3])
    db.session.commit()
    flash('Sample data initialized!')
    return redirect(url_for('main.index'))

@main.route('/update_gantt_task', methods=['POST'])
@login_required
def update_gantt_task():
    data = request.get_json()
    tid = data.get('id')
    start = data.get('start')
    end = data.get('end')
    duration = None
    # Calculate duration from start and end
    from datetime import datetime, timedelta
    try:
        d1 = datetime.strptime(start, '%Y-%m-%d')
        d2 = datetime.strptime(end, '%Y-%m-%d')
        duration = (d2 - d1).days
    except Exception:
        return 'Invalid date', 400
    # Update phase/item/subitem
    updated = False
    new_title = data.get('title')
    changed_ids = []
    if tid.startswith('phase-'):
        obj = Phase.query.get(int(tid.split('-')[1]))
        if obj:
            obj.start_date = d1.date()
            obj.duration = duration
            if new_title:
                if new_title.startswith('Phase: '):
                    obj.title = new_title.replace('Phase: ', '', 1)
                else:
                    obj.title = new_title
            db.session.commit()
            updated = True
            changed_ids.append(f'phase-{obj.id}')
    elif tid.startswith('item-'):
        obj = Item.query.get(int(tid.split('-')[1]))
        if obj:
            obj.start_date = d1.date(); obj.duration = duration
            if new_title:
                if new_title.startswith('Item: '):
                    obj.title = new_title.replace('Item: ', '', 1)
                else:
                    obj.title = new_title
            _enforce_dependencies_and_containment(obj)
            db.session.commit()
            updated = True
            changed_ids.append(f'item-{obj.id}')
    elif tid.startswith('subitem-'):
        obj = SubItem.query.get(int(tid.split('-')[1]))
        if obj:
            obj.start_date = d1.date(); obj.duration = duration
            if new_title:
                if new_title.startswith('Sub: '):
                    obj.title = new_title.replace('Sub: ', '', 1)
                else:
                    obj.title = new_title
            _enforce_dependencies_and_containment(obj)
            db.session.commit()
            updated = True
            changed_ids.append(f'subitem-{obj.id}')
    # (Optional: add subitem support if needed)
    print('GANTT UPDATE:', tid, start, end, duration, updated)
    cascade_adjustments = []
    if updated:
        # Cascade forward if necessary (skip for phase until needed)
        cascade_adjustments = _cascade_dependents(changed_ids)
        # Rebuild task list for fresh critical path computation (phases + items only like index)
        phases = Phase.query.all()
        tasks = []
        from datetime import datetime as _dt
        for phase in phases:
            p_start = str(phase.start_date)
            p_end = (_dt.strptime(p_start, '%Y-%m-%d') + timedelta(days=int(phase.duration))).strftime('%Y-%m-%d')
            tasks.append({'id': f'phase-{phase.id}', 'start': p_start, 'end': p_end, 'dependencies': ''})
            for item in phase.items:
                i_start = str(item.start_date)
                i_end = (_dt.strptime(i_start, '%Y-%m-%d') + timedelta(days=int(item.duration))).strftime('%Y-%m-%d')
                tasks.append({'id': f'item-{item.id}', 'start': i_start, 'end': i_end, 'dependencies': item.dependencies or ''})
        cp_ids = compute_critical_path(tasks)
        return {
            'id': tid,
            'start': start,
            'end': end,
            'duration': duration,
            'title': new_title or '',
            'critical_path': cp_ids,
            'cascade': cascade_adjustments
        }, 200
    return 'Not found', 404
