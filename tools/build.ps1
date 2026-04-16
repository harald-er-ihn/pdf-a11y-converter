<#
.SYNOPSIS
Enterprise Build-Script für den PDF A11y Converter.
Nutzt absolute Interpreter-Pfade und sicheres Error-Handling.
#>
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$LogDir = Join-Path $ProjectRoot "logs"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogFile = Join-Path $LogDir "build_$Timestamp.log"

function Write-Log {
    param([string]$message, [string]$color="White")
    $time = Get-Date -Format "HH:mm:ss"
    $line = "[$time] $message"
    Write-Host $line -ForegroundColor $color
    Add-Content -Path $LogFile -Value $line
}

function Run-Python {
    param([string]$ScriptPath, [string]$Args="")
    
    $VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    
    if (!(Test-Path $VenvPython)) {
        Write-Log "⚠️ Venv nicht gefunden. Nutze System-Python..." "Yellow"
        $VenvPython = "python"
    }

    Write-Log "> $VenvPython $ScriptPath $Args" "DarkGray"
    
    $process = Start-Process -FilePath $VenvPython -ArgumentList "$ScriptPath $Args" -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -ne 0) {
        Write-Log "❌ FEHLER: Skript endete mit Code $($process.ExitCode)" "Red"
        exit $process.ExitCode
    }
}

Push-Location $ProjectRoot
Write-Log "🚀 Starte PDF A11y Converter Build-Pipeline..." "Cyan"
Write-Log "==============================================" "Cyan"

try {
    Write-Log "`n[1/7] Erstelle isoliertes Build-Venv..." "Green"
    if (!(Test-Path "venv")) {
        python -m venv venv
    }

    Write-Log "`n[2/7] Installiere Core-Dependencies & Upgrade Pip..." "Green"
    $VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    
    # Pip und Setuptools aktualisieren, um Rust-Crashes zu vermeiden
    Start-Process -FilePath $VenvPython -ArgumentList "-m pip install --upgrade pip setuptools wheel" -NoNewWindow -Wait
    Start-Process -FilePath $VenvPython -ArgumentList "-m pip install -r requirements-dev.txt" -NoNewWindow -Wait

    Write-Log "`n[3/7] setup workers..." "Green"
    Run-Python "tools\setup_workers.py"

    Write-Log "`n[4/7] download models..." "Green"
    Run-Python "tools\download_models.py"

    Write-Log "`n[5/7] Phase 1: Core Binaries kompilieren (build.py)..." "Green"
    Run-Python "build.py"

    Write-Log "`n[6/7] Phase 2: Runtime Assembly (assemble.py)..." "Green"
    Run-Python "assemble.py"

    Write-Log "`n[7/7] Phase 3: Installer Paketierung (package.py)..." "Green"
    Run-Python "package.py"

    Write-Log "`n🎉 Build-Prozess komplett und erfolgreich abgeschlossen!" "Cyan"
    Write-Log "Logdatei: $LogFile" "DarkGray"
}
finally {
    Pop-Location
}
