# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Build-Orchestrator für den PDF A11y Converter (Strategy Pattern).
Kompiliert die Hauptanwendungen (GUI & CLI) plattformspezifisch.
Das Setup der Worker-Umgebungen wurde in build_workers.py ausgelagert.
Ruft am Ende das mitgelieferte, portable Inno Setup auf (.exe Generierung).
"""

import os
import subprocess
import sys
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List

import customtkinter
import PyInstaller.__main__

os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyInstaller")

CTK_PATH = os.path.dirname(customtkinter.__file__)
SEP = os.pathsep


@dataclass
class BuildTarget:
    """Kapselt die Konfiguration für ein PyInstaller-Ziel."""

    script: str
    name: str
    console: bool


class PlatformBuilder(ABC):
    """Strategy Interface für plattformspezifische Build-Argumente."""

    @abstractmethod
    def get_platform_args(self) -> List[str]:
        """Gibt plattformspezifische PyInstaller-Argumente zurück."""


class WindowsBuilder(PlatformBuilder):
    """Konkrete Strategie für Windows-Builds (inkl. GTK3)."""

    def get_platform_args(self) -> List[str]:
        args = []
        gtk_path = Path("resources") / "windows" / "gtk3"
        if gtk_path.exists():
            args.append(f"--add-data={gtk_path}{SEP}gtk3/")
        return args


class UnixBuilder(PlatformBuilder):
    """Konkrete Strategie für Unix-Builds (Linux/macOS)."""

    def get_platform_args(self) -> List[str]:
        return []


class PyInstallerDirector:
    """Orchestriert den Build-Prozess anhand der gewählten Strategie."""

    def __init__(self, strategy: PlatformBuilder) -> None:
        self.strategy = strategy
        self.base_args = [
            "--onedir",
            f"--add-data={CTK_PATH}{SEP}customtkinter/",
            f"--add-data=config{SEP}config/",
            f"--add-data=static{SEP}static/",
            f"--add-data=resources{SEP}resources/",
            f"--add-data=README.md{SEP}.",
            f"--add-data=ARCHITECTURE.md{SEP}.",
            "--hidden-import=PIL._tkinter_finder",
            "--hidden-import=pymupdf",
            "--hidden-import=fitz",
            "--exclude-module=tensorboard",
            "--noconfirm",
        ]

    def build(self, target: BuildTarget) -> None:
        """Führt den PyInstaller-Build für ein spezifisches Target aus."""
        print(f"\n⚙️ Kompiliere {target.name}...")

        args = [target.script, f"--name={target.name}"] + self.base_args
        args.extend(self.strategy.get_platform_args())

        if not target.console:
            args.append("--noconsole")

        PyInstaller.__main__.run(args)


def build_installer() -> None:
    """Builds the Inno Setup installer using the bundled portable compiler."""
    iscc = Path("resources") / "windows" / "Inno Setup 6" / "ISCC.exe"
    script = Path("installer") / "pdf-a11y.iss"

    if not iscc.exists():
        iscc = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        if not iscc.exists():
            print("⚠️ Inno Setup Compiler nicht gefunden.")
            print("Installer wird übersprungen.")
            return

    if not script.exists():
        print(f"⚠️ Installer Script fehlt unter: {script}")
        return

    print("\n📦 Baue Installer mit Inno Setup...")
    subprocess.run([str(iscc), str(script)], check=True)
    print("✅ Installer erfolgreich erstellt (Siehe dist/installer/)!")


def main() -> None:
    """Haupteinstiegspunkt des Orchestrators."""
    print("🚀 Starte PyInstaller Build-Prozess (Strategy Pattern)...")

    strategy = WindowsBuilder() if sys.platform == "win32" else UnixBuilder()
    director = PyInstallerDirector(strategy)

    targets = [
        BuildTarget("app_gui.py", "PDF-A11y-GUI", console=False),
        BuildTarget("cli.py", "PDF-A11y-CLI", console=True),
    ]

    for target in targets:
        director.build(target)

    print("\n📦 Kompilierung beendet. Starte Worker-Packaging...")

    packaging_script = Path("build_workers.py")
    if packaging_script.exists():
        subprocess.run([sys.executable, str(packaging_script)], check=True)
    else:
        print(
            f"⚠️ Packaging-Skript fehlt ({packaging_script}). Worker wurden nicht gepackt!"
        )

    if sys.platform == "win32":
        print("\n🚀 Erstelle Split Distribution Installer...")
        build_installer()


if __name__ == "__main__":
    main()
