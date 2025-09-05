#!/usr/bin/env bash
set -euo pipefail
CMD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$CMD_DIR/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
export FLASK_APP=run.py
export FLASK_ENV=${FLASK_ENV:-development}
function info(){ echo -e "\e[36m[INFO]\e[0m $*"; }
function warn(){ echo -e "\e[33m[WARN]\e[0m $*"; }
function err(){ echo -e "\e[31m[ERROR]\e[0m $*"; }
if [[ ! -d "$VENV_DIR" ]]; then
  warn ".venv not found, creating"
  python -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
NO_INSTALL=0
ACTION=""
REV_MSG=""
for arg in "$@"; do
  case "$arg" in
    -Upgrade) ACTION="upgrade";;
    -Downgrade) ACTION="downgrade";;
    -Revision) ACTION="revision";;
    -Current) ACTION="current";;
    -Verify) ACTION="verify";;
    -Run) ACTION="run";;
    -Integrity) ACTION="integrity";;
    -NoInstall) NO_INSTALL=1;;
    -RevisionMessage=*) REV_MSG="${arg#*=}";;
  esac
done
if [[ $NO_INSTALL -eq 0 ]]; then
  info "Installing deps"
  pip install --upgrade pip >/dev/null
  pip install -r "$ROOT_DIR/requirements.txt" >/dev/null
fi
function do_revision(){ [[ -z "$REV_MSG" ]] && { err "Provide -RevisionMessage=msg"; exit 1; }; info "Generating revision: $REV_MSG"; alembic revision --autogenerate -m "$REV_MSG"; }
function do_upgrade(){ info "Upgrading"; alembic upgrade head; do_current; do_verify; do_integrity; }
function do_downgrade(){ info "Downgrading one step"; alembic downgrade -1; }
function do_current(){ info "Current revision"; alembic current; }
function do_verify(){ info "Verifying schema"; python - <<'PY'
import sqlite3, json
conn=sqlite3.connect('app.db')
cols=[r[1] for r in conn.execute('PRAGMA table_info(image)')]
print(json.dumps({'image_columns':cols,'legacy_present': any(c in cols for c in ('phase_id','item_id','subitem_id'))}))
PY
}
function do_integrity(){ info "Integrity check"; python - <<'PY'
import sqlite3, json
conn=sqlite3.connect('app.db'); cur=conn.cursor()
counts={}
for t in ('image_phase','image_item','image_subitem'):
    try:
        cur.execute(f'SELECT COUNT(1) FROM {t}')
        counts[t]=cur.fetchone()[0]
    except Exception:
        counts[t]='missing'
cols=[r[1] for r in cur.execute('PRAGMA table_info(image)')]
legacy=[c for c in ('phase_id','item_id','subitem_id') if c in cols]
print(json.dumps({'association_counts':counts,'legacy_columns_remaining':legacy}))
PY
}
function do_run(){ info "Running dev server"; python run.py; }
case "$ACTION" in
  revision) do_revision;;
  upgrade) do_upgrade;;
  downgrade) do_downgrade;;
  current) do_current;;
  verify) do_verify;;
  integrity) do_integrity;;
  run) do_run;;
  *) cat <<USAGE
Usage: ./scripts/manage.sh [options]
  -Upgrade            Run alembic upgrade head (with post checks)
  -Downgrade          Downgrade one revision
  -Revision -RevisionMessage="msg"  Create new revision
  -Current            Show current revision
  -Verify             Verify schema columns
  -Integrity          Association table counts
  -Run                Run development server
  -NoInstall          Skip dependency install
USAGE
  ;;
 esac
