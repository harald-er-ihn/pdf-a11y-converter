<#
.SYNOPSIS
Enterprise Build-Script für den PDF A11y Converter.
Nutzt absolute Interpreter-Pfade und sicheres Error-Handling.
#>

$ErrorActionPreference = "Continue" # Verhindert Abstürze durch harmlose stderr-Logs
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
    
    # Nutzt IMMER strikt den Venv-Interpreter. Kein Activate.ps1 nötig!
    $VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    
    if (!(Test-Path $VenvPython)) {
        Write-Log "⚠️ Venv nicht gefunden. Nutze System-Python als Fallback..." "Yellow"
        $VenvPython = "python"
    }

    Write-Log "> $VenvPython $ScriptPath $Args" "DarkGray"
    
    # Führt den Prozess aus und leitet Streams live in die Konsole
    $process = Start-Process -FilePath $VenvPython -ArgumentList "$ScriptPath $Args" -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -ne 0) {
        Write-Log "❌ FEHLER: Skript endete mit Code $($process.ExitCode)" "Red"
        Write-Log "Bitte prüfen Sie das Konsolenfenster auf Details." "Red"
        exit $process.ExitCode
    }
}

Push-Location $ProjectRoot
Write-Log "🚀 Starte PDF A11y Converter Build-Pipeline..." "Cyan"
Write-Log "==============================================" "Cyan"

try {
    Write-Log "`n[1/5] Erstelle isoliertes Build-Venv..." "Green"
    if (!(Test-Path "venv")) {
        python -m venv venv
    }

    Write-Log "`n[2/5] Installiere Core-Dependencies..." "Green"
    $VenvPip = Join-Path $ProjectRoot "venv\Scripts\pip.exe"
    Start-Process -FilePath $VenvPip -ArgumentList "install -r requirements-dev.txt" -NoNewWindow -Wait

	Write-Log "`n[2b/5] upgrade pip..." "Green"
    Run-Python "C:\Users\HaraldHutter\project_code\venv\Scripts\python.exe -m pip install --upgrade pip"
    
    Write-Log "`n[3/5] Phase 1: Core Binaries kompilieren (build.py)..." "Green"
    Run-Python "build.py"

    Write-Log "`n[4/5] Phase 2: Runtime Assembly (assemble.py)..." "Green"
    Run-Python "assemble.py"

    Write-Log "`n[5/5] Phase 3: Installer Paketierung (package.py)..." "Green"
    Run-Python "package.py"

    Write-Log "`n🎉 Build-Prozess komplett und erfolgreich abgeschlossen!" "Cyan"
    Write-Log "Logdatei: $LogFile" "DarkGray"
}
finally {
    Pop-Location
}
