# MFScope Launcher
$Root = $PSScriptRoot
Set-Location $Root

function Write-Step($msg) { Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !! $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  MFScope -- India MF Intelligence Engine" -ForegroundColor Cyan
Write-Host ""

$venvPython  = Join-Path $Root ".venv\Scripts\python.exe"
$venvPip     = Join-Path $Root ".venv\Scripts\pip.exe"
$venvAlembic = Join-Path $Root ".venv\Scripts\alembic.exe"
$venvUvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
$seedScript  = Join-Path $Root "seed.py"
$frontendDir = Join-Path $Root "frontend"
$dbFile      = Join-Path $Root "mfscope.db"

# ── 1. Virtual environment ────────────────────────────────────────────────────
if (-not (Test-Path $venvPython)) {
    Write-Host "  ERROR: .venv not found. Creating it now..." -ForegroundColor Red
    python -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAILED to create venv. Install Python 3.11+ first." -ForegroundColor Red
        Read-Host "Press Enter to exit"; exit 1
    }
}
Write-Ok "Virtual environment ready."

# ── 2. Backend packages ───────────────────────────────────────────────────────
$pipCheck = & $venvPip show fastapi 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Step "Installing backend packages (first run)..."
    & $venvPip install fastapi "uvicorn[standard]" sqlalchemy alembic aiosqlite httpx `
        beautifulsoup4 lxml feedparser pydantic pydantic-settings python-dotenv `
        apscheduler loguru tenacity pandas numpy scikit-learn xgboost vaderSentiment `
        asyncpg psycopg2-binary 2>&1 | Out-Null
    Write-Ok "Packages installed."
} else {
    Write-Ok "Backend packages already installed."
}

# ── 3. .env ───────────────────────────────────────────────────────────────────
$envFile    = Join-Path $Root ".env"
$envExample = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Ok ".env created from .env.example"
} else {
    Write-Ok ".env exists."
}

# ── 4. DB tables ──────────────────────────────────────────────────────────────
Write-Step "Initialising database tables..."
& $venvPython -c "import asyncio; from backend.db.session import init_db; asyncio.run(init_db())" 2>&1 | Out-Null
Write-Ok "Database tables ready."

# ── 5. Seed if DB is empty (<100KB means no data yet) ─────────────────────────
if (-not (Test-Path $dbFile) -or (Get-Item $dbFile).Length -lt 100000) {
    Write-Step "Seeding database from AMFI (takes ~30 seconds on first run)..."
    & $venvPython $seedScript
    Write-Ok "Seed complete."
} else {
    Write-Ok "Database already seeded."
}

# ── 6. Node / frontend ────────────────────────────────────────────────────────
$noFrontend = $false
try {
    $null = node --version 2>&1
} catch {
    $noFrontend = $true
}

if (-not $noFrontend -and -not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Step "Installing frontend packages..."
    Push-Location $frontendDir
    npm install 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $noFrontend = $true }
    Pop-Location
    Write-Ok "Frontend packages installed."
} elseif (-not $noFrontend) {
    Write-Ok "Frontend packages already installed."
} else {
    Write-Warn "Node.js not found. Get it from https://nodejs.org/"
}

# ── 7. Write helper scripts (avoids quoting hell in Start-Process) ────────────
$backendScript = Join-Path $Root "_launch_backend.ps1"
$frontendScript = Join-Path $Root "_launch_frontend.ps1"

Set-Content $backendScript @"
Set-Location '$Root'
Write-Host 'Backend starting on http://localhost:8000' -ForegroundColor Cyan
& '$venvUvicorn' backend.api.main:app --reload --port 8000
Read-Host 'Press Enter to close'
"@

Set-Content $frontendScript @"
Set-Location '$frontendDir'
Write-Host 'Frontend starting on http://localhost:5173' -ForegroundColor Cyan
npm run dev
Read-Host 'Press Enter to close'
"@

# ── 8. Launch backend ─────────────────────────────────────────────────────────
Write-Step "Launching backend on http://localhost:8000 ..."
Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$backendScript`""
Start-Sleep -Seconds 4

# ── 9. Launch frontend ────────────────────────────────────────────────────────
if (-not $noFrontend) {
    Write-Step "Launching frontend on http://localhost:5173 ..."
    Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$frontendScript`""
    Start-Sleep -Seconds 5
    Start-Process "http://localhost:5173"
} else {
    Start-Process "http://localhost:8000/docs"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  MFScope is running!" -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:5173" -ForegroundColor White
Write-Host "  API Docs  : http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to close this launcher"
