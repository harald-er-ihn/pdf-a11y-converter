$ErrorActionPreference = "Stop"

function Run-Step($name, $command) {
    Write-Host ""
    Write-Host "=== $name ===" -ForegroundColor Cyan
    try {
        & $command
        Write-Host "$name erfolgreich" -ForegroundColor Green
    }
    catch {
        Write-Host "$name fehlgeschlagen!" -ForegroundColor Red
        exit 1
    }
}

Run-Step "Dependencies installieren" { pip install -r .\requirements-dev.txt }
Run-Step "Build" { python .\build.py }
Run-Step "Assemble" { python .\assemble.py }
Run-Step "Package" { python .\package.py }

Write-Host ""
Write-Host "Build-Prozess abgeschlossen." -ForegroundColor Green