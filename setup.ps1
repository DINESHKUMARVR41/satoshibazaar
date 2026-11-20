$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPath = Join-Path $ProjectRoot 'backend'
$FrontendPath = Join-Path $ProjectRoot 'frontend'
$EnvFile = Join-Path $ProjectRoot '.env'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.11 is required. Install it and reopen PowerShell.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js 20.19+ or 22.12+ and npm are required. Install them and reopen PowerShell.' }
$NodeVersion = [version](& node -p "process.versions.node")
if (($NodeVersion.Major -eq 20 -and $NodeVersion -lt [version]'20.19') -or ($NodeVersion.Major -eq 22 -and $NodeVersion -lt [version]'22.12') -or ($NodeVersion.Major -lt 20) -or $NodeVersion.Major -eq 21) { throw "Vite 8 requires Node.js 20.19+ or 22.12+; found $NodeVersion." }
$PythonVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$PythonVersion -lt [version]'3.11') { throw "Python 3.11 or newer is required; found $PythonVersion." }
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $ProjectRoot '.env.example') $EnvFile }

$VenvPython = Join-Path $BackendPath '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) { & python -m venv (Join-Path $BackendPath '.venv') }
$ExistingEnv = Get-Content -Raw $EnvFile
if ($ExistingEnv -match '(?m)^JWT_SECRET=replace-with-') {
  $GeneratedSecret = & $VenvPython -c "import secrets; print(secrets.token_urlsafe(48))"
  $ExistingEnv = [regex]::Replace($ExistingEnv, '(?m)^JWT_SECRET=.*$', "JWT_SECRET=$GeneratedSecret")
  Set-Content -Path $EnvFile -Value $ExistingEnv -NoNewline -Encoding utf8
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip.' }
& $VenvPython -m pip install -r (Join-Path $BackendPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
Push-Location $BackendPath
try {
  & $VenvPython -c "import models; from database import Base, engine, SessionLocal, upgrade_existing_sqlite_schema; from seed import run_seed; upgrade_existing_sqlite_schema(engine); Base.metadata.create_all(bind=engine); db=SessionLocal(); run_seed(db); db.close()"
  if ($LASTEXITCODE -ne 0) { throw 'Database initialization or demo seeding failed.' }
} finally { Pop-Location }
Push-Location $FrontendPath
try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } } finally { Pop-Location }
Write-Host 'Setup complete. Run .\run.ps1 to start the application.' -ForegroundColor Green
