# =============================================================================
# KORGAN AI — Auto-Start Configuration
# Creates a Windows Task Scheduler task to start KORGAN AI on boot.
# Run as Administrator: powershell -ExecutionPolicy Bypass -File scripts\autostart.ps1
# =============================================================================

param(
    [switch]$Remove,
    [switch]$Status
)

$TaskName = "KorganAI-AutoStart"
$ProjectPath = "C:\project on my Local PC\MainAi"

# --- Status check ---
if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Host "[OK] Task '$TaskName' exists" -ForegroundColor Green
        Write-Host "  State: $($task.State)" -ForegroundColor Cyan
        Write-Host "  Path: $($task.TaskPath)" -ForegroundColor Gray
    } else {
        Write-Host "[--] Task '$TaskName' not found" -ForegroundColor Yellow
    }
    exit 0
}

# --- Remove ---
if ($Remove) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] Task '$TaskName' removed" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Task not found or already removed" -ForegroundColor Yellow
    }
    exit 0
}

# --- Create startup script ---
$StartupScript = @"
# KORGAN AI Auto-Start Script
# Waits for Docker to be ready, then starts all services

`$LogFile = "$ProjectPath\logs\autostart.log"
`$MaxWait = 120  # seconds to wait for Docker

function Log(`$msg) {
    `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path `$LogFile -Value "[`$ts] `$msg"
}

Log "=== KORGAN AI Auto-Start ==="
Log "Waiting for Docker Desktop..."

# Wait for Docker to be ready
`$waited = 0
while (`$waited -lt `$MaxWait) {
    try {
        docker info 2>&1 | Out-Null
        if (`$LASTEXITCODE -eq 0) {
            Log "Docker is ready (waited `${waited}s)"
            break
        }
    } catch {}
    Start-Sleep -Seconds 5
    `$waited += 5
}

if (`$waited -ge `$MaxWait) {
    Log "ERROR: Docker not ready after `${MaxWait}s"
    exit 1
}

# Start KORGAN AI services
Log "Starting KORGAN AI services..."
Set-Location "$ProjectPath"

try {
    docker compose up -d 2>&1 | ForEach-Object { Log `$_ }
    Log "All services started successfully"
} catch {
    Log "ERROR: Failed to start services: `$_"
    exit 1
}

# Wait for core to be healthy
Log "Waiting for Core API..."
`$healthWait = 0
while (`$healthWait -lt 60) {
    try {
        `$resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if (`$resp.StatusCode -eq 200) {
            Log "Core API is healthy"
            break
        }
    } catch {}
    Start-Sleep -Seconds 5
    `$healthWait += 5
}

Log "KORGAN AI startup complete"
"@

$ScriptPath = "$ProjectPath\scripts\korgan_startup.ps1"
Set-Content -Path $ScriptPath -Value $StartupScript -Encoding UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  KORGAN AI — Auto-Start Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Create Scheduled Task ---
Write-Host "Creating scheduled task '$TaskName'..." -ForegroundColor Yellow

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`"" `
    -WorkingDirectory $ProjectPath

$Trigger = New-ScheduledTaskTrigger -AtLogon

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -RunLevel Highest `
    -LogonType Interactive

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Starts KORGAN AI services when user logs in" `
        -Force

    Write-Host ""
    Write-Host "[OK] Auto-start configured!" -ForegroundColor Green
    Write-Host ""
    Write-Host "KORGAN AI will start automatically when you log in." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Management:" -ForegroundColor Yellow
    Write-Host "  Check status:  .\scripts\autostart.ps1 -Status"
    Write-Host "  Remove:        .\scripts\autostart.ps1 -Remove"
    Write-Host "  View logs:     Get-Content logs\autostart.log -Tail 20"
    Write-Host ""
} catch {
    Write-Host "[FAIL] Failed to create task: $_" -ForegroundColor Red
    Write-Host "Make sure you're running as Administrator." -ForegroundColor Yellow
    exit 1
}
