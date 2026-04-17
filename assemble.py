# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Phase 2 der Build-Pipeline: Runtime Assembly (SRP).
Kopiert Worker-Skripte, richtet isolierte Venvs ein und kopiert
Ressourcen (veraPDF, KI-Modelle) in die Zielverzeichnisse.
"""

import shutil
import subprocess
import sys
from pathlib import Path
import urllib.request
import zipfile

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
TARGETS = ["pdf-a11y-gui", "pdf-a11y-cli"]


def ensure_embedded_runtime(internal_dir: Path) -> None:
    """
    Sorgt dafür, dass eine portierbare Python 3.12 Laufzeitumgebung
    für Windows im End-Release mitgeliefert wird.
    """
    if sys.platform != "win32":
        return

    runtime_target = internal_dir / "python_runtime"
    if runtime_target.exists():
        return

    print("  -> Lade Python 3.12 Embedded Runtime herunter...")

    cache_dir = Path.home() / ".pdf-a11y-models" / "build_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "python-3.12.9-embed-amd64.zip"

    # 1. Download der offiziellen CPython Embedded Version
    if not zip_path.exists():
        url = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
        urllib.request.urlretrieve(url, zip_path)

    # 2. Entpacken in das Release-Verzeichnis (_internal/python_runtime)
    runtime_target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(runtime_target)

    # 3. WICHTIGER HACK: Embedded Python ignoriert standardmäßig site-packages!
    # Wir müssen in der python312._pth Datei das Import-System ('import site')
    # entkommentieren, sonst können die Venvs ihre Pakete nicht laden.
    pth_file = runtime_target / "python312._pth"
    if pth_file.exists():
        lines = pth_file.read_text(encoding="utf-8")
        lines = lines.replace("#import site", "import site")
        pth_file.write_text(lines, encoding="utf-8")

    print("  ✅ Embedded Runtime erfolgreich bereitgestellt.")


def assemble_target(target_name: str) -> None:
    """Baut die isolierte Laufzeitumgebung für das angegebene Target zusammen."""
    print(f"\n📦 Assembly Phase für '{target_name}'...")
    target_dir = DIST_DIR / target_name
    internal_dir = target_dir / "_internal"

    # Runtime injeziieren
    ensure_embedded_runtime(internal_dir)

    # 1. Ressourcen kopieren
    src_resources = ROOT_DIR / "resources"
    dst_resources = internal_dir / "resources"

    if src_resources.exists():
        print("  -> Kopiere Ressourcen (veraPDF, Modelle, GTK)...")
        shutil.copytree(src_resources, dst_resources, dirs_exist_ok=True)
    else:
        print("  ⚠️ WARNUNG: Quell-Ordner 'resources' nicht gefunden!")

    # 2. Worker kopieren und Venvs einrichten
    src_workers = ROOT_DIR / "workers"
    dst_workers = target_dir / "workers"

    if src_workers.exists():
        print("  -> Kopiere Worker-Strukturen...")
        shutil.copytree(
            src_workers,
            dst_workers,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("venv", ".venv", "__pycache__"),
        )

        print("  -> Erstelle isolierte Venvs für Worker...")
        for worker_dir in dst_workers.iterdir():
            if worker_dir.is_dir() and (worker_dir / "requirements.txt").exists():
                print(f"     * Setup [{worker_dir.name}]...")
                venv_dir = worker_dir / "venv"

                # 100% Offline: Standard Venv-Generierung
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_dir.resolve())], check=True
                )

                # WINDOWS-FIX: Korrekte Erkennung des Python-Interpreters im Venv
                if sys.platform == "win32":
                    py_exe = venv_dir / "Scripts" / "python.exe"
                else:
                    py_exe = venv_dir / "bin" / "python"

                # Sicherheits-Upgrade: Verhindert Rust/Maturin Kompilierungsfehler
                subprocess.run(
                    [
                        str(py_exe.resolve()),
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "pip",
                        "setuptools",
                        "wheel",
                        "-q",
                    ],
                    check=False,
                )

                try:
                    # WINDOWS-FIX: DEVNULL entfernt, stderr/stdout abfangen,
                    # um Pip-Abstürze (z.B. Long Paths) debuggen zu können.
                    # Sicheres Encoding verhindert Crash auf deutschen Windows-Systemen.
                    subprocess.run(
                        [
                            str(py_exe.resolve()),
                            "-m",
                            "pip",
                            "install",
                            "-r",
                            str((worker_dir / "requirements.txt").resolve()),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                except subprocess.CalledProcessError as e:
                    print(f"\n❌ FEHLER beim Installieren von {worker_dir.name}!")
                    print(f"   Grund:\n{e.stderr or e.stdout}")
                    print(
                        "Achten Sie darauf, dass Sie für KI-Pakete Python 3.12 nutzen."
                    )
                    sys.exit(1)
    else:
        print("  ⚠️ WARNUNG: Quell-Ordner 'workers' nicht gefunden!")


def main() -> None:
    """Haupteinstiegspunkt für Phase 2."""
    print("🚀 Starte Phase 2: Runtime Assembly...")

    if not DIST_DIR.exists():
        print(
            "❌ FEHLER: 'dist' Ordner fehlt! Bitte zuerst 'python build.py' ausführen."
        )
        sys.exit(1)

    for target in TARGETS:
        if (DIST_DIR / target).exists():
            assemble_target(target)
        else:
            print(f"  ⚠️ Überspringe '{target}' (wurde nicht kompiliert).")

    print("\n🎉 Phase 2 (Assembly) erfolgreich abgeschlossen!")


if __name__ == "__main__":
    main()
