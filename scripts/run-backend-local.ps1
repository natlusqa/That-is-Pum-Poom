# Run Flask backend on the HOST (for ONVIF camera discovery).
# Use with: docker compose -f docker-compose.yml -f docker-compose.local-backend.yml up -d
# Then run this script from the project root.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BackendDir = Join-Path $ProjectRoot "backend"
$EnvFile = Join-Path $ProjectRoot ".env"

# Load .env into process environment
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$' -and $_ -notmatch '^\s*#') {
            $key = $matches[1]
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

$pgPass = [Environment]::GetEnvironmentVariable("POSTGRES_PASSWORD", "Process")
if (-not $pgPass) { $pgPass = "surveillance_secure_pwd" }

$env:DATABASE_URL = "postgresql://surveillance:${pgPass}@localhost:5435/surveillance"
$env:FLASK_PORT = "5002"
$env:GO2RTC_HOST = "localhost"
$env:GO2RTC_PORT = "1984"

if (-not (Test-Path (Join-Path $BackendDir "app.py"))) {
    Write-Error "Backend not found at $BackendDir. Run this script from project root or fix path."
}
Push-Location $BackendDir
try {
    Write-Host "Starting backend on http://0.0.0.0:5002 (ONVIF discovery available)" -ForegroundColor Green
    Write-Host "Database: localhost:5435 (ensure Postgres container is running)" -ForegroundColor Gray
    python app.py
} finally {
    Pop-Location
}
