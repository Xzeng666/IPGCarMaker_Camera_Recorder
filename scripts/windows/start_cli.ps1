$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/3] Creating Python virtual environment..."
    py -3 -m venv .venv
} else {
    Write-Host "[1/3] Reusing existing virtual environment..."
}

$python = ".venv\Scripts\python.exe"
& $python -c "import numpy, cv2" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[2/3] Installing core dependencies..."
    if ((Test-Path "wheels") -and (Get-ChildItem "wheels" -File -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        Write-Host "Using local offline wheelhouse."
        & $python -m pip install --no-index --find-links wheels -r requirements-core.txt
    } else {
        & $python -m pip install -r requirements-core.txt
    }
} else {
    Write-Host "[2/3] Core dependencies already available; skipping pip install."
}

Write-Host "[3/3] Starting CarMaker recorder CLI..."
& $python run.py --config config.json
exit $LASTEXITCODE
