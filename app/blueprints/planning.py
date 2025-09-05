from flask import Blueprint, render_template, session, redirect, url_for, request, flash, send_file, current_app
from flask_login import login_required, current_user
from app.models import db, Project, Phase, Item, SubItem, Image, DraftPart, UserSession
import os, json, io, csv, zipfile
from datetime import datetime, timedelta
import uuid as _uuid

planning_bp = Blueprint('planning', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')

@planning_bp.route('/')
@login_required
def index():
    """Temporary minimal planning index while full migration of advanced endpoints proceeds.

    NOTE: Critical path, dependency logic, draft promotion, reorder & export endpoints
    are pending re-introduction. This stub keeps UI loading with basic Gantt data.
    """
    projects = Project.query.all()
    selected_project_id = session.get('selected_project_id')
    # Filter hierarchy by selected project (if chosen)
    if selected_project_id:
        phases = (Phase.query.filter_by(project_id=selected_project_id)
                  .order_by(Phase.sort_order.asc(), Phase.id.asc()).all())
        items = (Item.query.join(Phase).filter(Phase.project_id == selected_project_id).all())
        subitems = (SubItem.query.join(Item).join(Phase)
                    .filter(Phase.project_id == selected_project_id).all())
    else:
        phases = Phase.query.order_by(Phase.project_id.asc(), Phase.sort_order.asc(), Phase.id.asc()).all()
        items = Item.query.all()
        subitems = SubItem.query.all()

    # Basic Gantt construction (no dependency or critical path highlighting yet)
    gantt_tasks = []
    for phase in phases:
        phase_start = phase.start_date.strftime('%Y-%m-%d') if phase.start_date else None
        phase_end = (phase.start_date + timedelta(days=phase.duration)).strftime('%Y-%m-%d') if phase.start_date else None
        gantt_tasks.append({
            'id': f'phase-{phase.id}', 'name': f'Phase: {phase.title}',
            'start': phase_start, 'end': phase_end, 'progress': 0,
            'custom_class': 'phase-bar'
        })
        for item in phase.items:
            item_start = item.start_date.strftime('%Y-%m-%d') if item.start_date else None
            item_end = (item.start_date + timedelta(days=item.duration)).strftime('%Y-%m-%d') if item.start_date else None
            gantt_tasks.append({
                'id': f'item-{item.id}', 'name': f'Item: {item.title}',
                'start': item_start, 'end': item_end, 'progress': 0,
                'custom_class': 'item-bar'
            })
            for sub in item.subitems:
                sub_start = sub.start_date.strftime('%Y-%m-%d') if sub.start_date else None
                sub_end = (sub.start_date + timedelta(days=sub.duration)).strftime('%Y-%m-%d') if sub.start_date else None
                gantt_tasks.append({
                    'id': f'subitem-{sub.id}', 'name': f'Sub: {sub.title}',
                    'start': sub_start, 'end': sub_end, 'progress': 0,
                    'custom_class': 'subitem-bar'
                })

    gantt_json_js = json.dumps(gantt_tasks)
    draft_parts = DraftPart.query.order_by(DraftPart.created_at.asc()).all()
    draft_json_js = json.dumps([
        {'id': d.id, 'title': d.title, 'type': d.part_type, 'internal_external': d.internal_external, 'project_id': d.project_id}
        for d in draft_parts
    ])
    images = Image.query.all()
    return render_template(
        'index.html',
        projects=projects, phases=phases, items=items, subitems=subitems,
        images=images, uploads_folder=UPLOAD_FOLDER, gantt_json_js=gantt_json_js,
        draft_json_js=draft_json_js, calendar_events_json='[]',
        critical_path_ids=[], active_usernames=[],
        critical_filter_active=False, selected_project_id=selected_project_id
    )

