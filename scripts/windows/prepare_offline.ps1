$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3 first on the download machine."
}

New-Item -ItemType Directory -Force -Path "wheels" | Out-Null
Write-Host "Downloading GUI + build dependencies into $projectRoot\wheels ..."
py -3 -m pip download -r requirements-build.txt -d wheels
Write-Host "Offline wheelhouse prepared. Copy the whole project folder to the target computer."
