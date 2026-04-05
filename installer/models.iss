; PDF A11y Converter - Model Layer Installer
; Enterprise Split Distribution: Enthält NUR die 3GB+ KI-Modelle.

#define MyAppName "PDF A11y Models"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TU Dortmund"

[Setup]
AppId={{9B72F18A-D645-42E1-8153-C8A9B2E3D4F5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

; Schreibt die 3GB Modelle global für alle User in ProgramData
DefaultDirName=C:\ProgramData\PDF-A11y\models

OutputDir=..\dist\installer
OutputBaseFilename=PDF-A11y-Models-v{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

DisableProgramGroupPage=yes
DirExistsWarning=no
Uninstallable=no
WizardStyle=modern

[Files]
; Kopiert alles aus dem lokalen Entwickler-Modell-Ordner in das Setup
Source: "..\resources\models\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
