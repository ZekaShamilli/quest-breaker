# Boots Quest-Breaker on Windows: builds the UI, then serves UI + API on http://localhost:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path backend\.venv)) { python -m venv backend\.venv }
$py = Resolve-Path backend\.venv\Scripts\python.exe
& $py -m pip install -q -r backend\requirements.txt
Push-Location frontend; npm install --silent; npm run build; Pop-Location
Set-Location backend; & $py -m uvicorn main:app --host 0.0.0.0 --port 8000
