$LogFile = "C:\project on my Local PC\MainAi\logs\autostart.log"
$MaxWait = 120
function Log($msg) { $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; Add-Content -Path $LogFile -Value "[$ts] $msg" }
Log "=== KORGAN AI Auto-Start ==="
Log "Waiting for Docker Desktop..."
$waited = 0
while ($waited -lt $MaxWait) {
    try { docker info 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { Log "Docker is ready (waited ${waited}s)"; break } } catch {}
    Start-Sleep -Seconds 5; $waited += 5
}
if ($waited -ge $MaxWait) { Log "ERROR: Docker not ready after ${MaxWait}s"; exit 1 }
Log "Starting KORGAN AI services..."
Set-Location "C:\project on my Local PC\MainAi"
try { docker compose up -d 2>&1 | ForEach-Object { Log $_ }; Log "All services started successfully" } catch { Log "ERROR: $_"; exit 1 }
