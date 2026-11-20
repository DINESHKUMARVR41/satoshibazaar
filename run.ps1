$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPath = Join-Path $ProjectRoot 'backend'
$FrontendPath = Join-Path $ProjectRoot 'frontend'
$VenvPython = Join-Path $BackendPath '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) { throw 'Backend environment is missing. Run .\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $FrontendPath 'node_modules'))) { throw 'Frontend dependencies are missing. Run .\setup.ps1 first.' }
foreach ($Port in @(8000, 5173)) {
  if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port is already in use. Stop its process before starting SatoshiBazaar." }
}
$LogPath = Join-Path $ProjectRoot '.run-logs'
New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
$BackendOut = Join-Path $LogPath 'backend.out.log'
$BackendErr = Join-Path $LogPath 'backend.err.log'
$FrontendOut = Join-Path $LogPath 'frontend.out.log'
$FrontendErr = Join-Path $LogPath 'frontend.err.log'
$EnvFile = Join-Path $ProjectRoot '.env'
$BackendArgs = @('-m','uvicorn','main:app','--host','127.0.0.1','--port','8000')
if (Test-Path $EnvFile) { $BackendArgs += @('--env-file', $EnvFile) }
$Backend = Start-Process -FilePath $VenvPython -ArgumentList $BackendArgs -WorkingDirectory $BackendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr
$Frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev','--','--host','127.0.0.1') -WorkingDirectory $FrontendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput $FrontendOut -RedirectStandardError $FrontendErr
Set-Content -Path (Join-Path $LogPath 'processes.json') -Value (@{ backend = $Backend.Id; frontend = $Frontend.Id } | ConvertTo-Json)
Start-Sleep -Seconds 3
try {
  $Health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 5
  $ApiSpec = Invoke-RestMethod 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 5
  if ($ApiSpec.paths.PSObject.Properties.Name -notcontains '/api/auth/register') {
    throw 'The API on port 8000 is an older SatoshiBazaar instance without authentication routes. Stop that instance and run .\run.ps1 again.'
  }
  Write-Host "Backend ready: http://localhost:8000 (demo mode: $($Health.demo_mode))" -ForegroundColor Green
} catch { Write-Warning "Backend is still starting. See $BackendErr" }
$FrontendPort = 5173
$FrontendStartup = Get-Content -Path $FrontendOut -Raw -ErrorAction SilentlyContinue
if ($FrontendStartup -match 'http://127\.0\.0\.1:(\d+)/') { $FrontendPort = [int]$Matches[1] }
Write-Host "Frontend: http://localhost:$FrontendPort" -ForegroundColor Green
Write-Host 'API docs: http://localhost:8000/docs'
try { Start-Process "http://localhost:$FrontendPort" } catch { Write-Host "Open http://localhost:$FrontendPort in your browser." }
