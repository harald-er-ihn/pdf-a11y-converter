# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Phase 3 der Build-Pipeline: Packaging.
Erzeugt die MSI/EXE-Installer via Inno Setup für Matrix42 Deployment.
Kompatibel mit Windows 11.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
INSTALLER_DIR = ROOT_DIR / "installer"


def get_iscc_path() -> Path | None:
    """
    WINDOWS-FIX: Dynamische, robuste Suche nach dem Inno Setup Compiler.
    Verhindert Abstürze, wenn Umgebungsvariablen wie PROGRAMFILES(X86) fehlen.
    """
    if sys.platform != "win32":
        return None

    # 1. Ist es in der globalen PATH-Variable registriert?
    iscc_which = shutil.which("iscc")
    if iscc_which:
        return Path(iscc_which)

    # 2. Übliche Windows Programm-Pfade absuchen
    check_paths = [
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        os.environ.get("PROGRAMW6432", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
    ]

    for base in check_paths:
        if base:
            path = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if path.exists():
                return path

    return None


def build_installer(iss_file: Path, iscc_path: Path) -> None:
    """Führt den Inno Setup Compiler sicher für ein Skript aus."""
    if not iss_file.exists():
        print(f"⚠️ Überspringe {iss_file.name} (Nicht gefunden).")
        return

    print(f"\n📦 Kompiliere Installer: {iss_file.name} ...")
    # Durch die LZMA2-Kompression der KI-Modelle kann das dauern
    try:
        # WINDOWS-FIX: text=True und UTF-8 Replacement, da Inno Setup
        # auf Windows Konsolen häufig CP1252 Umlaute in stdout wirft,
        # was Python zum Absturz bringt.
        subprocess.run(
            [str(iscc_path.resolve()), str(iss_file.resolve())],
            check=True,
            capture_output=False,  # Wir lassen den Output auf die Konsole durch
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(f"✅ {iss_file.name} erfolgreich kompiliert!")
    except subprocess.CalledProcessError as e:
        print(
            f"❌ Fehler beim Kompilieren von {iss_file.name}: Exit-Code {e.returncode}"
        )
        sys.exit(1)


def main() -> None:
    print("🚀 Starte Phase 3: Installer Packaging (Inno Setup)...")

    # WINDOWS-FIX: Linux Graceful Exit
    if sys.platform != "win32":
        print(
            "⚠️ Phase 3 (Inno Setup) wird übersprungen, da das System nicht Windows ist."
        )
        sys.exit(0)

    iscc_path = get_iscc_path()

    if not iscc_path or not iscc_path.exists():
        print("❌ Inno Setup Compiler (ISCC.exe) nicht gefunden!")
        print("Bitte installiere Inno Setup 6: https://jrsoftware.org/isdl.php")
        sys.exit(1)

    build_installer(INSTALLER_DIR / "pdf-a11y-gui.iss", iscc_path)
    build_installer(INSTALLER_DIR / "pdf-a11y-cli.iss", iscc_path)

    print("\n🎉 Phase 3 erfolgreich! Die Setup-Dateien liegen in 'installer/Output/'.")
    print("\n👉 Matrix42 Silent-Install Befehl für IT-Admins:")
    print("   Install_PDF-A11y-GUI.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART")


if __name__ == "__main__":
    main()
