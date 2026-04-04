# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Dediziertes Build-Modul für das Packaging der KI-Worker.
Wird von build.py aufgerufen.
Isoliert Venv-Erstellung, Offline-Pip-Installationen und Windows DLL-Hacks
strikt vom Kompilierungsprozess der Hauptanwendung.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class WorkerPackager:
    """Verantwortlich für das Deployment isolierter Worker-Umgebungen."""

    def __init__(self) -> None:
        self.resources = Path("resources")
        self.wheelhouse = self.resources / "wheels"
        self.is_windows = sys.platform == "win32"
        self.portable_base: Optional[Path] = None

    def prepare_offline_python(self) -> None:
        """Kopiert und initialisiert das Windows Embeddable Python."""
        if not self.is_windows:
            return

        base_embed = self.resources / "windows" / "python_embed"
        staged_dir = Path("build") / "python_base"

        if staged_dir.exists() and (staged_dir / "python.exe").exists():
            self.portable_base = staged_dir
            return

        if not base_embed.exists():
            print(
                f"⚠️ Portable Python fehlt ({base_embed}). Nutze System-Python (Online-Modus)."
            )
            return

        print(f"📦 Bereite Portable Python vor: {base_embed}")
        shutil.copytree(base_embed, staged_dir, dirs_exist_ok=True)
        self._init_pip_offline(staged_dir)
        self.portable_base = staged_dir

    def _init_pip_offline(self, py_dir: Path) -> None:
        """Initialisiert pip im portablen Python (Windows)."""
        pip_script = py_dir / "get-pip.py"
        py_exe = py_dir / "python.exe"

        if pip_script.exists():
            subprocess.run([str(py_exe), str(pip_script)], check=True)
            pip_script.unlink()
            subprocess.run(
                [str(py_exe), "-m", "pip", "install", "setuptools", "wheel"],
                check=True,
            )

    def _apply_windows_dll_patches(self, env_dir: Path) -> None:
        """Verteilt C-Runtime DLLs für Scikit-Learn und Abhängigkeiten."""
        sklearn_dir = self.resources / "windows" / "sklearn"
        if not sklearn_dir.exists():
            return

        libs_dst = env_dir / "Lib" / "site-packages" / "sklearn" / ".libs"
        libs_dst.mkdir(parents=True, exist_ok=True)

        for dll in sklearn_dir.glob("*.dll"):
            shutil.copy2(dll, libs_dst)
            shutil.copy2(dll, env_dir)

        print("📦 Windows Sklearn DLL-Patches angewendet.")

    def _install_requirements(self, py_exe: Path, req_file: Path) -> None:
        """Installiert Dependencies. Nutzt Wheelhouse falls vorhanden."""
        cmd = [str(py_exe), "-m", "pip", "install"]

        if self.wheelhouse.exists():
            print("🔒 [OFFLINE MODE] Installiere aus lokalem Wheelhouse...")
            cmd.extend(["--no-index", "--find-links", str(self.wheelhouse)])
        else:
            print(
                "⚠️ [ONLINE MODE] Wheelhouse fehlt! Lade Pakete aus dem Internet (PyPI)..."
            )

        cmd.extend(["-r", str(req_file)])
        subprocess.run(cmd, check=True)

    def package_worker(self, worker_dir: Path) -> None:
        """Richtet das autonome Environment für einen Worker ein."""
        req_file = worker_dir / "requirements.txt"
        if not req_file.exists():
            return

        print(f"  -> Richte {worker_dir.name} ein...")

        if self.is_windows and self.portable_base:
            env_dir = worker_dir / "python_env"
            shutil.copytree(self.portable_base, env_dir, dirs_exist_ok=True)
            self._apply_windows_dll_patches(env_dir)

            py_exe = env_dir / "python.exe"
            self._install_requirements(py_exe, req_file)
        else:
            venv_dir = worker_dir / "venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

            # 🚀 FIX: Windows GitHub-Actions Fallback nutzt "Scripts/python.exe"
            if self.is_windows:
                py_exe = venv_dir / "Scripts" / "python.exe"
            else:
                py_exe = venv_dir / "bin" / "python"

            subprocess.run(
                [str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                check=False,
            )
            self._install_requirements(py_exe, req_file)

    def run(self, targets: List[str]) -> None:
        self.prepare_offline_python()
        src_workers = Path("workers")

        if not src_workers.exists():
            print("⚠️ Keine Worker zum Packen gefunden.")
            return

        ignore_pattern = shutil.ignore_patterns(
            "venv", ".venv", "python_env", "__pycache__"
        )

        for target in targets:
            dist_workers = Path(f"dist/{target}/workers")
            shutil.copytree(
                src_workers, dist_workers, dirs_exist_ok=True, ignore=ignore_pattern
            )

            print(f"\n⚙️ Konfiguriere Worker in {target}...")
            for w_dir in dist_workers.iterdir():
                if w_dir.is_dir():
                    self.package_worker(w_dir)


def main() -> None:
    packager = WorkerPackager()
    packager.run(["PDF-A11y-GUI", "PDF-A11y-CLI"])
    print("\n🎉 Packaging erfolgreich abgeschlossen!")


if __name__ == "__main__":
    main()
