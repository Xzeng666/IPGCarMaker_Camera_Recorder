$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectRoot

if (-not (Test-Path ".venv-build\Scripts\python.exe")) {
    Write-Host "[1/4] Creating build environment..."
    py -3 -m venv .venv-build
} else {
    Write-Host "[1/4] Reusing build environment..."
}

$python = ".venv-build\Scripts\python.exe"
Write-Host "[2/4] Installing build dependencies..."
if ((Test-Path "wheels") -and (Get-ChildItem "wheels" -File -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    & $python -m pip install --no-index --find-links wheels -r requirements-build.txt
} else {
    & $python -m pip install -r requirements-build.txt
}

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist\CarMakerCameraRecorderGUI") { Remove-Item -Recurse -Force "dist\CarMakerCameraRecorderGUI" }

Write-Host "[3/4] Building portable GUI..."
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "CarMakerCameraRecorderGUI" `
    --add-data "config.json;." `
    run_gui.py

Copy-Item "config.json" "dist\CarMakerCameraRecorderGUI\config.json" -Force

Write-Host "[4/4] Running packaged GUI smoke test..."
$exe = Join-Path $projectRoot "dist\CarMakerCameraRecorderGUI\CarMakerCameraRecorderGUI.exe"
$proc = Start-Process -FilePath $exe -ArgumentList @("--smoke-test", "--config", "config.json") -PassThru -Wait
if ($proc.ExitCode -ne 0) {
    throw "Portable GUI smoke test failed with exit code $($proc.ExitCode)."
}
Write-Host "Portable GUI build verified: $projectRoot\dist\CarMakerCameraRecorderGUI"
