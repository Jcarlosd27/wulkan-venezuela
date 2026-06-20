[CmdletBinding()]
param(
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$ApiRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $ApiRoot

try {
    python -m pip install --upgrade pip
    python -m pip install -r requirements-desktop.txt

    $pyinstallerArgs = @(
        "--noconfirm",
        "--clean",
        "--name", "FVENTAS Desktop",
        "--windowed",
        "--collect-submodules", "webview",
        "--add-data", "templates;templates",
        "--add-data", "static;static",
        "--add-data", "core\country_locations_data.json;core",
        "--add-data", "migrations;migrations",
        "--add-data", "alembic.ini;.",
        "desktop_app.py"
    )

    if ($OneFile) {
        $pyinstallerArgs = @("--onefile") + $pyinstallerArgs
    }

    python -m PyInstaller @pyinstallerArgs

    if ($OneFile) {
        Write-Host "EXE listo en: $ApiRoot\dist\FVENTAS Desktop.exe"
    }
    else {
        Write-Host "EXE listo en: $ApiRoot\dist\FVENTAS Desktop\FVENTAS Desktop.exe"
    }
}
finally {
    Pop-Location
}
