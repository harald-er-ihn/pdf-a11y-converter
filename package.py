# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Phase 3 der Build-Pipeline: Packaging.
Erzeugt die MSI/EXE-Installer via Inno Setup für Matrix42 Deployment.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
INSTALLER_DIR = ROOT_DIR / "installer"

# Standard-Pfad von Inno Setup Compiler
ISCC_PATH = Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"


def build_installer(iss_file: Path) -> None:
    """Führt den Inno Setup Compiler für ein Skript aus."""
    if not iss_file.exists():
        print(f"⚠️ Überspringe {iss_file.name} (Nicht gefunden).")
        return
        
    print(f"\n📦 Kompiliere Installer: {iss_file.name} ...")
    # Durch die LZMA2-Kompression der KI-Modelle kann das ein paar Minuten dauern!
    try:
        subprocess.run([str(ISCC_PATH), str(iss_file)], check=True)
        print(f"✅ {iss_file.name} erfolgreich kompiliert!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Fehler beim Kompilieren von {iss_file.name}: {e}")
        sys.exit(1)


def main() -> None:
    print("🚀 Starte Phase 3: Installer Packaging (Inno Setup)...")
    
    if not ISCC_PATH.exists():
        print(f"❌ Inno Setup Compiler nicht gefunden unter:\n{ISCC_PATH}")
        print("Bitte installiere Inno Setup 6: https://jrsoftware.org/isdl.php")
        sys.exit(1)

    build_installer(INSTALLER_DIR / "pdf-a11y-gui.iss")
    build_installer(INSTALLER_DIR / "pdf-a11y-cli.iss")

    print("\n🎉 Phase 3 erfolgreich! Die Setup-Dateien liegen in 'installer/Output/'.")
    print("\n👉 Matrix42 Silent-Install Befehl für IT-Admins:")
    print("   Install_PDF-A11y-GUI.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART")


if __name__ == "__main__":
    main()
