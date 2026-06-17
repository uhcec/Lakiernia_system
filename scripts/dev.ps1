# dev.ps1 -- check migrations then start backend + frontend
# Usage: .\scripts\dev.ps1
#        .\scripts\dev.ps1 -SkipMigrationCheck

param(
    [switch]$SkipMigrationCheck
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

$venvPython  = Join-Path $repoRoot ".venv\Scripts\python.exe"
$venvAlembic = Join-Path $repoRoot ".venv\Scripts\alembic.exe"
$venvUvicorn = Join-Path $repoRoot ".venv\Scripts\uvicorn.exe"
$frontendDir = Join-Path $repoRoot "frontend"

function Write-Step { param([string]$msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "    ERR $msg" -ForegroundColor Red }

# Stop any stale dev servers from a previous run. uvicorn --reload and npm/vite spawn child
# processes that survive Stop-Job and keep holding :8000 / :5173 — so a new run would fail to bind
# and the browser would be served STALE code. We match this repo's backend (app.main:app) and
# frontend (vite under this repo) and tree-kill them (/T also kills the reload worker child).
function Stop-DevServers {
    param([string]$root)
    $frontend = [regex]::Escape((Join-Path $root "frontend"))
    $stale = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'app\.main:app' -or
            ($_.CommandLine -match 'vite' -and $_.CommandLine -match $frontend)
        )
    }
    foreach ($p in $stale) {
        Write-Host ("    stopping stale dev process PID {0}" -f $p.ProcessId) -ForegroundColor DarkYellow
        & taskkill /PID $p.ProcessId /T /F *> $null
    }
    if ($stale) { Start-Sleep -Milliseconds 700 }
}

$backendJob  = $null
$frontendJob = $null

try {
    # -- 1. Alembic checks ---------------------------------------------------
    if (-not $SkipMigrationCheck) {
        Write-Step "Alembic: applying pending migrations"
        & $venvAlembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed" }
        Write-Ok "upgrade head"

        Write-Step "Alembic: verifying no unapplied migrations"
        & $venvAlembic check
        $alembicCheckExit = $LASTEXITCODE
        if ($alembicCheckExit -ne 0) {
            Write-Fail "alembic check failed -- models and migrations are out of sync"
            throw "alembic check failed"
        }
        Write-Ok "check passed -- migrations are up to date"
    } else {
        Write-Host "`n    [skipping migration check]" -ForegroundColor DarkGray
    }

    # -- 2. Start backend ----------------------------------------------------
    Write-Step "Reclaiming dev ports (stopping any stale servers from a previous run)"
    Stop-DevServers -root $repoRoot

    Write-Step "Starting backend (uvicorn) on http://127.0.0.1:8000"
    $backendJob = Start-Job -ScriptBlock {
        param($root, $uvicorn)
        Set-Location $root
        & $uvicorn app.main:app --reload 2>&1
    } -ArgumentList $repoRoot, $venvUvicorn

    # wait for /health to respond (up to 15 s)
    $backendReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { $backendReady = $true; break }
        } catch {}
    }

    if (-not $backendReady) {
        Write-Fail "backend did not respond within 15 s"
        Receive-Job $backendJob | Select-Object -Last 20 | ForEach-Object { Write-Host "    $_" }
        throw "backend failed to start"
    }
    Write-Ok "backend is up -> http://127.0.0.1:8000"

    # -- 3. Start frontend ---------------------------------------------------
    Write-Step "Starting frontend (vite) on http://127.0.0.1:5173"
    $frontendJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location $dir
        npm run dev 2>&1
    } -ArgumentList $frontendDir

    # wait for Vite ready line (up to 15 s)
    $frontendReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        $out = Receive-Job $frontendJob -Keep
        if ($out -match "localhost|127\.0\.0\.1|ready in") { $frontendReady = $true; break }
    }

    if (-not $frontendReady) {
        Write-Host "    (frontend may still be starting -- check browser)" -ForegroundColor DarkGray
    } else {
        Write-Ok "frontend is up -> http://127.0.0.1:5173"
    }

    # -- 4. Summary ----------------------------------------------------------
    Write-Host ""
    Write-Host "  Backend  ->  http://127.0.0.1:8000" -ForegroundColor White
    Write-Host "  API docs ->  http://127.0.0.1:8000/docs" -ForegroundColor White
    Write-Host "  Frontend ->  http://127.0.0.1:5173" -ForegroundColor White
    Write-Host ""
    Write-Host "  Press Ctrl+C to stop both servers." -ForegroundColor DarkGray

    # stream output from both jobs until interrupted
    while ($true) {
        Start-Sleep -Seconds 1
        Receive-Job $backendJob  | ForEach-Object { Write-Host "[backend]  $_" -ForegroundColor DarkGray }
        Receive-Job $frontendJob | ForEach-Object { Write-Host "[frontend] $_" -ForegroundColor DarkGray }

        if ($backendJob.State  -eq "Failed") { throw "backend process exited unexpectedly" }
        if ($frontendJob.State -eq "Failed") { throw "frontend process exited unexpectedly" }
    }

} finally {
    if ($backendJob)  { Stop-Job $backendJob;  Remove-Job $backendJob  -ErrorAction SilentlyContinue }
    if ($frontendJob) { Stop-Job $frontendJob; Remove-Job $frontendJob -ErrorAction SilentlyContinue }
    # Stop-Job kills the job wrappers but the uvicorn reload worker / vite child can survive and keep
    # holding the ports. Kill them too so the next run starts clean (and never serves stale code).
    Stop-DevServers -root $repoRoot
    Pop-Location
}
