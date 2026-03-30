# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Build-Skript für den PDF A11y Converter.
Kompiliert die Hauptanwendung (GUI & CLI) und richtet Worker ein.
"""

import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import customtkinter
import PyInstaller.__main__

os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyInstaller")

CTK_PATH = os.path.dirname(customtkinter.__file__)
SEP = os.pathsep

config_path = os.path.abspath("config")
static_path = os.path.abspath("static")
resources_path = os.path.abspath("resources")

print("🚀 Starte PyInstaller Dual-Build-Prozess...")

build_targets = [
    {
        "script": "app_gui.py",
        "name": "PDF-A11y-GUI",
        "console": True,
    },
    {"script": "cli.py", "name": "PDF-A11y-CLI", "console": True},
]

for target in build_targets:
    print(f"\n⚙️ Kompiliere {target['name']}...")

    args = [
        target["script"],
        f"--name={target['name']}",
        "--onedir",
        f"--add-data={CTK_PATH}{SEP}customtkinter/",
        f"--add-data={config_path}{SEP}config/",
        f"--add-data={static_path}{SEP}static/",
        f"--add-data={resources_path}{SEP}resources/",
        f"--add-data=README.md{SEP}.",  # 🚀 FIX: README hinzugefügt
        f"--add-data=ARCHITECTURE.md{SEP}.",  # 🚀 FIX: ARCHITECTURE hinzugefügt
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=frontend",
        "--hidden-import=pymupdf",
        "--hidden-import=fitz",
        "--exclude-module=tensorboard",
        "--noconfirm",
    ]

    if not target["console"]:
        args.append("--noconsole")

    PyInstaller.__main__.run(args)

print("\n📂 Kopiere Worker-Skripte für beide Builds...")
for target in build_targets:
    dist_workers_dir = Path(f"dist/{target['name']}/workers")
    src_workers_dir = Path("workers")

    if src_workers_dir.exists():
        shutil.copytree(
            src_workers_dir,
            dist_workers_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("venv", ".venv", "__pycache__"),
        )

        print(f"\n⚙️ Richte Venvs in {target['name']} ein...")
        for worker_dir in dist_workers_dir.iterdir():
            req_file = worker_dir / "requirements.txt"

            if worker_dir.is_dir() and req_file.exists():
                print(f"  -> [{worker_dir.name}]")
                venv_dir = worker_dir / "venv"

                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_dir)], check=True
                )

                if sys.platform == "win32":
                    py_exe = venv_dir / "Scripts" / "python.exe"
                    pip_exe = venv_dir / "Scripts" / "pip.exe"
                else:
                    py_exe = venv_dir / "bin" / "python"
                    pip_exe = venv_dir / "bin" / "pip"

                subprocess.run(
                    [str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                    check=False,
                )

                subprocess.run(
                    [str(pip_exe), "install", "-r", str(req_file)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )

print("\n🎉 Dual-Build erfolgreich abgeschlossen!")
