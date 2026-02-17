# =============================================================================
# KORGAN AI — Windows Setup Script
# Run as Administrator: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# =============================================================================

param(
    [switch]$SkipDocker,
    [switch]$SkipOllama,
    [switch]$SkipDesktop
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  KORGAN AI — Setup Script v1.0" -ForegroundColor Cyan
Write-Host "  Personal AI Operating System" -ForegroundColor Cyan
Write-Host "  Created by Mr. Korgan" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Check prerequisites ---
Write-Host "[1/8] Checking prerequisites..." -ForegroundColor Yellow

# Docker
if (-not $SkipDocker) {
    try {
        docker --version | Out-Null
        Write-Host "  [OK] Docker installed" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] Docker not found. Please install Docker Desktop." -ForegroundColor Red
        exit 1
    }

    # Docker Compose
    try {
        docker compose version | Out-Null
        Write-Host "  [OK] Docker Compose available" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] Docker Compose not found." -ForegroundColor Red
        exit 1
    }
}

# NVIDIA GPU
try {
    nvidia-smi --query-gpu=name --format=csv,noheader | Out-Null
    $gpu = nvidia-smi --query-gpu=name --format=csv,noheader
    Write-Host "  [OK] NVIDIA GPU: $gpu" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] nvidia-smi not found. GPU features may not work." -ForegroundColor Yellow
}

# Python
try {
    python --version | Out-Null
    $pyver = python --version
    Write-Host "  [OK] $pyver" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Python not found in PATH" -ForegroundColor Yellow
}

# Node.js (for Desktop app)
if (-not $SkipDesktop) {
    try {
        node --version | Out-Null
        $nodever = node --version
        Write-Host "  [OK] Node.js $nodever" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] Node.js not found. Desktop app requires Node.js 18+" -ForegroundColor Yellow
    }
}

# --- Create .env from .env.example ---
Write-Host ""
Write-Host "[2/8] Setting up environment..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  [OK] Created .env from .env.example" -ForegroundColor Green
    Write-Host "  [!!!] IMPORTANT: Edit .env and fill in your secrets!" -ForegroundColor Red
} else {
    Write-Host "  [OK] .env already exists" -ForegroundColor Green
}

# --- Create necessary directories ---
Write-Host ""
Write-Host "[3/8] Creating directories..." -ForegroundColor Yellow

$dirs = @("logs", "data", "backups")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  [OK] Created $dir/" -ForegroundColor Green
    }
}

# --- Pull Docker images ---
if (-not $SkipDocker) {
    Write-Host ""
    Write-Host "[4/8] Pulling Docker images..." -ForegroundColor Yellow

    $images = @(
        "postgres:16-alpine",
        "redis:7-alpine",
        "chromadb/chroma:latest",
        "ollama/ollama:latest",
        "n8nio/n8n:latest"
    )

    foreach ($img in $images) {
        Write-Host "  Pulling $img..." -ForegroundColor Gray
        docker pull $img
    }
    Write-Host "  [OK] All images pulled" -ForegroundColor Green
}

# --- Build KORGAN containers ---
if (-not $SkipDocker) {
    Write-Host ""
    Write-Host "[5/8] Building KORGAN containers..." -ForegroundColor Yellow
    docker compose build
    Write-Host "  [OK] Containers built" -ForegroundColor Green
}

# --- Start infrastructure ---
if (-not $SkipDocker) {
    Write-Host ""
    Write-Host "[6/8] Starting infrastructure..." -ForegroundColor Yellow
    docker compose up -d postgresql redis chromadb ollama
    Write-Host "  Waiting for services to be ready..."
    Start-Sleep -Seconds 10
    Write-Host "  [OK] Infrastructure started" -ForegroundColor Green
}

# --- Pull Ollama models ---
if (-not $SkipOllama) {
    Write-Host ""
    Write-Host "[7/8] Pulling LLM models (this may take a while)..." -ForegroundColor Yellow

    $models = @(
        "mistral:7b-instruct-v0.3-q4_K_M",
        "nomic-embed-text"
    )

    foreach ($model in $models) {
        Write-Host "  Pulling $model..." -ForegroundColor Gray
        docker exec korgan-ollama ollama pull $model
    }
    Write-Host "  [OK] Models pulled" -ForegroundColor Green
}

# --- Desktop app setup ---
if (-not $SkipDesktop) {
    Write-Host ""
    Write-Host "[8/8] Setting up Desktop app..." -ForegroundColor Yellow

    if (Test-Path "desktop/package.json") {
        Push-Location desktop
        npm install
        Pop-Location
        Write-Host "  [OK] Desktop dependencies installed" -ForegroundColor Green
    }
}

# --- Summary ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  KORGAN AI Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env and fill in your secrets (Telegram bot token, etc.)"
Write-Host "  2. Start all services:  docker compose up -d"
Write-Host "  3. Start Desktop app:   cd desktop && npm start"
Write-Host "  4. Check health:        curl http://localhost:8000/health"
Write-Host ""
Write-Host "Telegram commands:" -ForegroundColor Yellow
Write-Host "  /start   — Initialize"
Write-Host "  /status  — System status"
Write-Host "  /mode    — Change autonomy level"
Write-Host "  /brief   — Intelligence briefing"
Write-Host "  /stop    — Emergency stop"
Write-Host ""
Write-Host "API: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "n8n: http://localhost:5678" -ForegroundColor Cyan
Write-Host ""
