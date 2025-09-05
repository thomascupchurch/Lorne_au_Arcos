## Deployment (PythonAnywhere)

Minimal steps:
1. Create a new Python 3.11+ web app (manual config) on PythonAnywhere.
2. Clone this repo into your PythonAnywhere account (e.g. under `~/Lorne_au_Arcos`).
3. Create a virtualenv: `python -m venv ~/.venvs/lorne` then `source ~/.venvs/lorne/bin/activate` and `pip install -r requirements.txt`.
4. Point the WSGI file to import `application` from `wsgi.py`:
	```python
	import sys, os
	project_root = os.path.expanduser('~/Lorne_au_Arcos')
	if project_root not in sys.path: sys.path.append(project_root)
	from wsgi import application
	```
5. Set environment variables in the PythonAnywhere web UI (SECRET_KEY, FLASK_ENV=production, ADMIN_USERNAME, ADMIN_PASSWORD, DATABASE_URL if using MySQL/Postgres later).
6. Run Alembic migrations once: in a Bash console:
	```bash
	cd ~/Lorne_au_Arcos
	source ~/.venvs/lorne/bin/activate
	alembic upgrade head
	```
7. Reload the web app.

Structure notes:
- `config.py` centralizes tunables (DB URL, timeouts, flags).
- App factory now avoids silent schema patching; rely on Alembic.
- Future flags can be added to `BaseConfig` without touching core modules.

Optional production hardening:
- Use a stronger SECRET_KEY.
- Move from SQLite to a managed MySQL/Postgres (set DATABASE_URL accordingly).
- Serve static via PythonAnywhere's static mapping pointing `/static` to the repo `static/` folder.

### New Utilities

- `scripts/manage.ps1` (Windows) and `scripts/manage.sh` (Unix) provide unified commands.
- Health endpoint: `GET /healthz` returns `{status:"ok"}` for monitors.
- `.env.example` added; copy to `.env` and customize secrets.

Example (Unix):
```
./scripts/manage.sh -Upgrade
./scripts/manage.sh -Run
```

Example (Windows PowerShell):
```
./scripts/manage.ps1 -Upgrade
./scripts/manage.ps1 -Run
```

## Deployment (PythonAnywhere)

1. Create a virtualenv on PythonAnywhere matching your local Python version.
2. Upload the project folder or pull from Git.
3. Install requirements:
	pip install -r requirements.txt
4. Run initial migrations (first time only):
	alembic upgrade head
5. Set up a Web app in the PythonAnywhere dashboard:
	- WSGI file should point to: project_path/wsgi.py (it exposes `application`).
6. Set environment variables in the web app config (e.g. ADMIN_USERNAME, ADMIN_PASSWORD, FLASK_DEBUG=0, SECRET_KEY=... ).
7. Reload the web app.
8. (Optional) For schema changes later: generate new migration and apply:
	alembic revision --autogenerate -m "desc"
	alembic upgrade head

Static files are under `static/`; PythonAnywhere can serve them directly if you map the directory, else Flask will serve them.

# Project Planning App MVP

A modular Flask app for project planning, designed for easy extensibility. Deployable on PythonAnywhere.

## Features (MVP)
- User authentication (to be added)
- Project creation (to be added)
- Task management (to be added)

## How to run locally
1. Install requirements: `pip install -r requirements.txt`
2. Run: `python run.py`

## Automation Script (Windows PowerShell)
Convenience script at `scripts/manage.ps1` wraps common tasks:

Examples:
```
./scripts/manage.ps1 -Upgrade                # Apply migrations (alembic upgrade head)
./scripts/manage.ps1 -Revision -RevisionMessage "add feature X"
./scripts/manage.ps1 -Current                # Show current revision
./scripts/manage.ps1 -Verify                 # Verify image table columns (legacy links removed)
./scripts/manage.ps1 -Run                    # Start development server
```
Flags can be combined (order independent). Use `-NoInstall` to skip dependency install step.

## Extending
Add new features as blueprints/modules in the `app/` directory.
