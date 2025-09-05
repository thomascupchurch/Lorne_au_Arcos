Param(
    [switch]$Upgrade,
    [switch]$Downgrade,
    [string]$RevisionMessage,
    [switch]$Revision,
    [switch]$Current,
    [switch]$Verify,
  [switch]$Run,
  [switch]$Integrity,
  [string]$BindHost = '127.0.0.1',
    [int]$Port = 5000,
    [switch]$NoInstall
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Ensure venv active
if(-not $env:VIRTUAL_ENV){
  Write-Warn 'Virtual environment not active. Attempting to use .venv.'
  $parent = Join-Path $PSScriptRoot '..'
  $venvPath = Join-Path $parent '.venv'
  $activate = Join-Path $venvPath 'Scripts/Activate.ps1'
  if(Test-Path $activate){ . $activate } else { Write-Warn "Could not auto-activate .venv at $activate" }
}

if(-not $NoInstall){
  Write-Info 'Installing/upgrading dependencies'
  $reqDir = Join-Path $PSScriptRoot '..'
  $reqPath = Join-Path $reqDir 'requirements.txt'
  if(-not (Test-Path $reqPath)){ Write-Warn "requirements.txt not found at $reqPath" } else {
    pip install --upgrade pip | Out-Null
    pip install -r "$reqPath" | Out-Null
  }
}

$env:FLASK_APP = 'run.py'
$env:FLASK_ENV = 'development'

function Do-Revision(){
  if(-not $RevisionMessage){ Write-Err 'Provide -RevisionMessage "message"'; exit 1 }
  Write-Info "Generating revision: $RevisionMessage"
  python -m alembic revision --autogenerate -m "$RevisionMessage"
}
function Do-Upgrade(){
  Write-Info 'Applying migrations (upgrade head)'
  python -m alembic upgrade head
  Write-Info 'Post-upgrade current revision'
  python -m alembic current
  Write-Info 'Running schema verification'
  Do-Verify
  Write-Info 'Running integrity check'
  Do-Integrity
}
function Do-Downgrade(){ param($Target='-1'); Write-Info "Downgrading to $Target"; python -m alembic downgrade $Target }
function Do-Current(){ Write-Info 'Current revision'; python -m alembic current }
function Do-Verify(){
  Write-Info 'Verifying schema (image table)'
  $code = @"
import sqlite3, json
conn=sqlite3.connect('app.db')
cols=[r[1] for r in conn.execute('PRAGMA table_info(image)')]
print(json.dumps({'image_columns':cols,'legacy_present': any(c in cols for c in ('phase_id','item_id','subitem_id'))}))
"@
  python -c $code
}
function Do-Integrity(){
  $code = @"
import sqlite3, json
conn=sqlite3.connect('app.db')
cur=conn.cursor()
tables=['image_phase','image_item','image_subitem']
counts={}
for t in tables:
  try:
    cur.execute(f'SELECT COUNT(1) FROM {t}')
    counts[t]=cur.fetchone()[0]
  except Exception:
    counts[t]='missing'
cols=[r[1] for r in cur.execute('PRAGMA table_info(image)')]
legacy=[c for c in ('phase_id','item_id','subitem_id') if c in cols]
print(json.dumps({'association_counts':counts,'legacy_columns_remaining':legacy}))
"@
  python -c $code
}
function Do-Run(){ Write-Info ("Starting app on http://{0}:{1}" -f $BindHost, $Port); python run.py }

if($Revision){ Do-Revision }
if($Upgrade){ Do-Upgrade }
if($Downgrade){ Do-Downgrade }
if($Current){ Do-Current }
if($Verify){ Do-Verify }
if($Run){ Do-Run }
if($Integrity){ Do-Integrity }

if(-not ($Upgrade -or $Downgrade -or $Revision -or $Current -or $Verify -or $Run -or $Integrity)){
  Write-Host 'Usage examples:' -ForegroundColor Green
  Write-Host '  ./scripts/manage.ps1 -Upgrade' -ForegroundColor Gray
  Write-Host '  ./scripts/manage.ps1 -Revision -RevisionMessage "add new table"' -ForegroundColor Gray
  Write-Host '  ./scripts/manage.ps1 -Verify' -ForegroundColor Gray
  Write-Host '  ./scripts/manage.ps1 -Run' -ForegroundColor Gray
  Write-Host '  ./scripts/manage.ps1 -Integrity' -ForegroundColor Gray
}
