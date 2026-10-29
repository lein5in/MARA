$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root "venv\Scripts\python.exe"

& $python -m compileall -q core memory main.py
if ($LASTEXITCODE -ne 0) { Write-Host "compileall failed" -ForegroundColor Red; exit 1 }

& $python -m ruff check . --isolated --select E4,E7,E9,F --exclude venv
if ($LASTEXITCODE -ne 0) { Write-Host "ruff failed" -ForegroundColor Red; exit 1 }

& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "pytest failed" -ForegroundColor Red; exit 1 }

Write-Host "All checks passed." -ForegroundColor Green
