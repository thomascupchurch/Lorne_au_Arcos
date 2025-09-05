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

## Extending
Add new features as blueprints/modules in the `app/` directory.
