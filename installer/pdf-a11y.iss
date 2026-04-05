; PDF A11y Converter
; Installer Script (Inno Setup)

#define MyAppName "PDF A11y Converter"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "TU Dortmund"
#define MyAppExeName "PDF-A11y-GUI.exe"

[Setup]
AppId={{A2C3D7C6-4E2D-4F32-91E5-6A1F0D92F123}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={pf}\PDF-A11y-Converter
DefaultGroupName=PDF A11y Converter

OutputDir=..\dist\installer
OutputBaseFilename=PDF-A11y-Setup-v{#MyAppVersion}

Compression=lzma
SolidCompression=yes

ArchitecturesInstallIn64BitMode=x64

DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop Icon erstellen"; Flags: unchecked

[Files]
Source: "..\dist\PDF-A11y-GUI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\dist\PDF-A11y-CLI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\dist\PDF-A11y-GUI\runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF A11y Converter"; Filename: "{app}\PDF-A11y-GUI.exe"
Name: "{autodesktop}\PDF A11y Converter"; Filename: "{app}\PDF-A11y-GUI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PDF-A11y-GUI.exe"; Description: "Programm starten"; Flags: nowait postinstall skipifsilent
