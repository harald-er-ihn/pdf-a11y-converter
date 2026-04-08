[Setup]
AppName=PDF A11y Converter GUI
AppVersion=0.1.0
AppPublisher=Dr. Harald Hutter
; Installiert nach C:\Program Files\PDF-A11y-Converter-GUI
DefaultDirName={autopf}\PDF-A11y-Converter-GUI
DefaultGroupName=PDF A11y Converter
OutputBaseFilename=Install_PDF-A11y-GUI
; Höchste Kompressionsstufe für die riesigen KI-Modelle
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; Matrix42 Opt-Ins (verhindert nervige Dialoge bei Silent Install)
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes

[Files]
; Kopiert ALLES aus dem dist Ordner, aber IGNORIERT __pycache__ und Cache-Dateien!
Source: "..\dist\pdf-a11y-gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*\__pycache__\*,*.pyc,*.pyo"

[Icons]
Name: "{group}\PDF A11y Converter"; Filename: "{app}\pdf-a11y-gui.exe"
Name: "{autodesktop}\PDF A11y Converter"; Filename: "{app}\pdf-a11y-gui.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Symbol erstellen"; GroupDescription: "Zusätzliche Symbole:"
