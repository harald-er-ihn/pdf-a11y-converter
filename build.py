# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Build-Skript für den PDF A11y Converter.
Kompiliert die Hauptanwendung (GUI & CLI) und richtet Worker ein.
Erzeugt 100% portable Python-Umgebungen für Windows (Offline-Variante).
"""
# pylint: disable=broad-exception-caught

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


def prepare_local_portable_python() -> Path:
    """
    Bereitet das lokale Python Embeddable Package für die Worker vor.
    (100% Offline - kopiert aus resources/windows/python_embed)
    """
    base_embed = Path(resources_path) / "windows" / "python_embed"
    staged_dir = Path("build/python_base")

    if staged_dir.exists() and (staged_dir / "python.exe").exists():
        return staged_dir

    if not base_embed.exists():
        print(f"❌ KRITISCHER FEHLER: Lokales Portable Python fehlt: {base_embed}")
        sys.exit(1)

    print(f"\n📦 Bereite lokales Portable Python aus {base_embed.name} vor...")
    shutil.copytree(base_embed, staged_dir, dirs_exist_ok=True)

    print("📦 Initialisiere pip im portablen Python (Offline)...")
    pip_script = staged_dir / "get-pip.py"
    py_exe = staged_dir / "python.exe"

    if pip_script.exists():
        subprocess.run([str(py_exe), str(pip_script)], check=True)
        pip_script.unlink()

        print("📦 Installiere Build-Tools (setuptools & wheel)...")
        cmd =[str(py_exe), "-m", "pip", "install", "setuptools", "wheel"]
        subprocess.run(cmd, check=True)

    return staged_dir


print("🚀 Starte PyInstaller Dual-Build-Prozess...")

build_targets =[
    {
        "script": "app_gui.py",
        "name": "PDF-A11y-GUI",
        "console": True,
    },
    {"script": "cli.py", "name": "PDF-A11y-CLI", "console": True},
]

gtk_local_path = os.path.join(resources_path, "windows", "gtk3")

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
        f"--add-data=README.md{SEP}.",
        f"--add-data=ARCHITECTURE.md{SEP}.",
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=frontend",
        "--hidden-import=pymupdf",
        "--hidden-import=fitz",
        "--exclude-module=tensorboard",
        "--noconfirm",
    ]

    if sys.platform == "win32" and os.path.exists(gtk_local_path):
        print("📦 Integriere lokale GTK3-Runtime für Windows...")
        args.append(f"--add-data={gtk_local_path}{SEP}gtk3/")

    if not target["console"]:
        args.append("--noconsole")

    PyInstaller.__main__.run(args)


print("\n📂 Kopiere Worker-Skripte und baue isolierte Umgebungen...")

PORTABLE_BASE = prepare_local_portable_python() if sys.platform == "win32" else None

for target in build_targets:
    dist_workers_dir = Path(f"dist/{target['name']}/workers")
    src_workers_dir = Path("workers")

    if src_workers_dir.exists():
        shutil.copytree(
            src_workers_dir,
            dist_workers_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("venv", ".venv", "python_env", "__pycache__"),
        )

        print(f"\n⚙️ Richte KI-Worker in {target['name']} ein...")
        for worker_dir in dist_workers_dir.iterdir():
            req_file = worker_dir / "requirements.txt"

            if worker_dir.is_dir() and req_file.exists():
                print(f"  -> Installiere[{worker_dir.name}]...")

                if sys.platform == "win32" and PORTABLE_BASE:
                    env_dir = worker_dir / "python_env"
                    shutil.copytree(PORTABLE_BASE, env_dir)

                    # 🚀 FIX: Sklearn C-Runtime DLLs perfekt verteilen!
                    sklearn_dir = Path(resources_path) / "windows" / "sklearn"
                    if sklearn_dir.exists():
                        libs_dst = env_dir / "Lib" / "site-packages" / "sklearn"
                        libs_dst = libs_dst / ".libs"
                        libs_dst.mkdir(parents=True, exist_ok=True)
                        
                        for dll_file in sklearn_dir.glob("*.dll"):
                            # 1. In .libs (für hardcoded paths in sklearn)
                            shutil.copy2(dll_file, libs_dst)
                            # 2. In python_env (für Windows DLL dependency loading)
                            shutil.copy2(dll_file, env_dir)

                    py_exe = env_dir / "python.exe"

                    subprocess.run([str(py_exe), "-m", "pip", "install", "-r", str(req_file)],
                        check=True,
                    )
                else:
                    venv_dir = worker_dir / "venv"
                    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True
                    )
                    py_exe = venv_dir / "bin" / "python"

                    subprocess.run([str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                        check=False,
                    )
                    subprocess.run([str(py_exe), "-m", "pip", "install", "-r", str(req_file)],
                        check=True,
                    )

print("\n🎉 Dual-Build erfolgreich abgeschlossen!")
