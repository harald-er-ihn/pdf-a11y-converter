[Setup]
AppName=PDF A11y Converter CLI
AppVersion=0.1.0
AppPublisher=Dr. Harald Hutter
DefaultDirName={autopf}\PDF-A11y-Converter-CLI
OutputBaseFilename=Install_PDF-A11y-CLI
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
; WICHTIG: Sagt Windows, dass sich Umgebungsvariablen ändern
ChangesEnvironment=yes
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes

[Files]
; Kopiert ALLES aus dem dist Ordner, aber IGNORIERT __pycache__ und Cache-Dateien!
Source: "..\dist\pdf-a11y-cli\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*\__pycache__\*,*.pyc,*.pyo"

[Registry]
; Schreibt das Installationsverzeichnis in den globalen System-PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Code]
// Pascal-Skript: Verhindert, dass der PATH bei mehrfacher Installation zugemüllt wird
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  // Suchen, ob der Pfad schon drinsteht
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
