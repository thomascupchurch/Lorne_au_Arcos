# Lorne au Arcos Planning App

## Overview
Modular Flask application providing project planning (Gantt, calendar, hierarchy), media asset association, authentication, administration, and presence tracking. Refactored from a monolith into blueprints:

- `auth`: login, logout, password change
- `admin`: user administration
- `utility`: health & active user sessions
- `media`: image/PDF uploads and multi-association to project parts
- `planning`: projects, phases, items, subitems, drafts, dependencies, critical path, exports

## Key Features
- Hierarchical structure: Project → Phase → Item → SubItem
- Draft holding area for title-only parts before promotion
- Dependencies (item/subitem) with naive critical path computation
- Drag-and-drop reordering of phases/items/subitems
- Drag date adjustment with cascade to dependents
- Calendar (ICS export) & Gantt (PNG export) views
- Critical path filtering (persisted in session)
- Media library: upload (PNG/JPG/PDF), drag-drop associate with any number of parts
- Project export (ZIP JSON), critical path CSV export
- Active user presence panel

## Tech Stack
Python / Flask / Flask-Login / SQLAlchemy / Alembic
Front-end: Frappe Gantt, FullCalendar, vanilla JS
DB via `DATABASE_URL` (SQLite default)

## Quick Start
```
pip install -r requirements.txt
python -m alembic upgrade head  # ensure schema
python run.py
```
Create a `.env` (see `.env.example`) with:
```
SECRET_KEY=dev-insecure
DATABASE_URL=sqlite:///app.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me
```

## Tests
Pytest suite (seed user) covers media association lifecycle and part creation / critical path presence.
```
pytest -q
```

## Implementation Notes
- Critical path: simplified longest-duration path across dependencies (items/subitems). No cycle detection yet.
- Drag cascade: adjusts dependent starts to follow latest predecessor end.
- Multi-association images via three M2M tables.
- Session state: `selected_project_id`, `critical_filter`.
- Active users derived from recent `UserSession` rows.

## Roadmap
- Dependency validation & cycle detection
- Richer draft promotion (items, subitems)
- Additional export formats (PDF, Excel)
- Reorder & cascade tests (expand coverage)
- Per-project authorization controls

## Automation Scripts
Windows: `scripts/manage.ps1`  (Upgrade, Run, Revision helpers)
Unix:    `scripts/manage.sh`

## Deployment (PythonAnywhere)
1. Create Python 3.11+ web app (manual config).
2. Clone repo -> `~/Lorne_au_Arcos`.
3. Virtualenv & install: `python -m venv ~/.venvs/lorne && source ~/.venvs/lorne/bin/activate && pip install -r requirements.txt`.
4. WSGI file snippet:
```python
import sys, os
project_root = os.path.expanduser('~/Lorne_au_Arcos')
if project_root not in sys.path: sys.path.append(project_root)
from wsgi import application
```
5. Set env vars (SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, DATABASE_URL, FLASK_ENV=production).
6. `alembic upgrade head` once.
7. Reload web app; map `/static` to `static/` for performance.

### Hardening
- Provide strong SECRET_KEY
- Move to MySQL/Postgres for concurrency
- Add HTTPS termination & security headers (reverse proxy)

## License
Copyright 2025 © LSI Graphics, LLC. All Rights Reserved.
