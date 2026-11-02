# Orbital Agronomist (v5) — Animated Website Launcher (PowerShell)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  ORBITAL AGRONOMIST (v5) — FastAPI + WebGL + SVG" -ForegroundColor Yellow
Write-Host "  URL:      http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  Fallback: py -m streamlit run app.py (port 8501)" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Yellow

py -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000
