# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Dediziertes Build-Modul für das Packaging der KI-Worker.
Implementiert die 'Shared AI Runtime' Architektur für 80% weniger Dateigröße.
Nutzt Constraints-Files, um Pip-Backtracking-Crashes zu verhindern.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Diese riesigen Pakete werden nur EINMAL zentral installiert
SHARED_PACKAGES = [
    "torch",
    "transformers",
    "Pillow",
    "sentencepiece",
    "protobuf",
    "numpy",
    "ultralytics",
]


class WorkerPackager:
    """Verantwortlich für das Deployment der Master-Runtime und der Worker."""

    def __init__(self) -> None:
        self.resources = Path("resources")
        self.wheelhouse = self.resources / "wheels"
        self.is_windows = sys.platform == "win32"
        self.portable_base: Optional[Path] = None

    def prepare_offline_python(self) -> None:
        """Bereitet das portable Python für Windows-Builds vor."""
        if not self.is_windows:
            return

        base_embed = self.resources / "windows" / "python_embed"
        staged_dir = Path("build") / "python_base"

        if staged_dir.exists() and (staged_dir / "python.exe").exists():
            self.portable_base = staged_dir
            return

        if not base_embed.exists():
            print(f"⚠️ Portable Python fehlt ({base_embed}). Nutze System-Python.")
            return

        print(f"📦 Bereite Portable Python vor: {base_embed}")
        shutil.copytree(base_embed, staged_dir, dirs_exist_ok=True)

        pip_script = staged_dir / "get-pip.py"
        py_exe = staged_dir / "python.exe"
        if pip_script.exists():
            subprocess.run([str(py_exe), str(pip_script)], check=True)
            pip_script.unlink()
            subprocess.run(
                [str(py_exe), "-m", "pip", "install", "setuptools", "wheel"], check=True
            )
        self.portable_base = staged_dir

    def _install_requirements(self, py_exe: Path, req_file: Path) -> None:
        """Generischer Installer für die zentrale AI-Runtime."""
        cmd = [str(py_exe), "-m", "pip", "install"]
        if self.wheelhouse.exists():
            print("🔒 [OFFLINE MODE] Installiere aus lokalem Wheelhouse...")
            cmd.extend(["--no-index", "--find-links", str(self.wheelhouse)])
        else:
            print("⚠️ [ONLINE MODE] Lade Pakete aus dem Internet (PyPI)...")

        cmd.extend(["-r", str(req_file)])

        # 🚀 FIX: Constraints anwenden, falls vorhanden!
        constraints = req_file.parent / "constraints.txt"
        if constraints.exists():
            cmd.extend(["-c", str(constraints)])

        subprocess.run(cmd, check=True)

    def build_shared_ai_runtime(self, dist_target: Path) -> Path:
        """Erstellt die zentrale AI Runtime für alle Worker."""
        runtime_dir = dist_target / "runtime" / "ai_env"
        if runtime_dir.exists():
            print("✅ AI Runtime existiert bereits.")
            return runtime_dir

        print(f"🧠 Baue zentrale AI Runtime in {runtime_dir}...")

        if self.is_windows and self.portable_base:
            shutil.copytree(self.portable_base, runtime_dir, dirs_exist_ok=True)
            py_exe = runtime_dir / "python.exe"
        else:
            subprocess.run([sys.executable, "-m", "venv", str(runtime_dir)], check=True)
            py_exe = (
                runtime_dir / "Scripts" / "python.exe"
                if self.is_windows
                else runtime_dir / "bin" / "python"
            )
            subprocess.run(
                [str(py_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True
            )

        req_file = Path("runtime/requirements-ai.txt")
        if req_file.exists():
            self._install_requirements(py_exe, req_file)

        print("✅ AI Runtime erfolgreich erstellt.")
        return runtime_dir

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

    def _install_worker_requirements(
        self, py_exe: Path, req_file: Path, shared_dir: Path, env_dir: Path
    ) -> None:
        """Filtert Shared-Packages heraus, installiert Reste und injiziert .pth Pfad."""
        # 1. Filtern der requirements.txt
        with open(req_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        filtered_reqs = []
        for line in lines:
            if not any(sp.lower() in line.lower() for sp in SHARED_PACKAGES):
                filtered_reqs.append(line)

        temp_req = req_file.with_name("temp_req.txt")
        with open(temp_req, "w", encoding="utf-8") as f:
            f.writelines(filtered_reqs)

        # 2. Worker-spezifische Pakete installieren
        cmd = [str(py_exe), "-m", "pip", "install"]
        if self.wheelhouse.exists():
            cmd.extend(["--no-index", "--find-links", str(self.wheelhouse)])

        cmd.extend(["-r", str(temp_req)])

        # 🚀 FIX: Constraints für Worker anwenden (z.B. formula_worker)!
        constraints = req_file.parent / "constraints.txt"
        if constraints.exists():
            cmd.extend(["-c", str(constraints)])

        subprocess.run(cmd, check=True)
        temp_req.unlink()

        # 3. Path Injection (.pth Datei)
        if self.is_windows and self.portable_base:
            pth_file = list(env_dir.glob("python*._pth"))
            if pth_file:
                with open(pth_file[0], "a", encoding="utf-8") as f:
                    f.write("\n../../shared_libs\n")
        else:
            site_packages = list(env_dir.glob("lib/python*/site-packages"))
            if site_packages:
                with open(
                    site_packages[0] / "shared_libs.pth", "w", encoding="utf-8"
                ) as f:
                    f.write(str(shared_dir.absolute()) + "\n")

    def package_worker(self, worker_dir: Path, shared_dir: Path) -> None:
        """Erstellt das deduplizierte Venv für einen Worker."""
        req_file = worker_dir / "requirements.txt"

        has_reqs = False
        if req_file.exists():
            with open(req_file, "r", encoding="utf-8") as f:
                has_reqs = any(line.strip() and not line.startswith("#") for line in f)

        if not has_reqs:
            print(f"  -> Überspringe Venv für {worker_dir.name} (100% Shared).")
            return

        print(f"  -> Richte leichtgewichtiges Venv für {worker_dir.name} ein...")

        if self.is_windows and self.portable_base:
            env_dir = worker_dir / "python_env"
            shutil.copytree(self.portable_base, env_dir, dirs_exist_ok=True)
            self._apply_windows_dll_patches(env_dir)
            py_exe = env_dir / "python.exe"
            self._install_worker_requirements(py_exe, req_file, shared_dir, env_dir)
        else:
            venv_dir = worker_dir / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
                check=True,
            )
            py_exe = (
                venv_dir / "Scripts" / "python.exe"
                if self.is_windows
                else venv_dir / "bin" / "python"
            )
            subprocess.run(
                [str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                check=False,
            )
            self._install_worker_requirements(py_exe, req_file, shared_dir, venv_dir)

    def compress_ai_runtime(self, dist_target: Path) -> None:
        """Komprimiert die AI Runtime und löscht das Original."""
        runtime_dir = dist_target / "runtime" / "ai_env"
        archive_base = dist_target / "runtime" / "ai_env"

        if not runtime_dir.exists():
            return

        print("📦 Komprimiere AI Runtime (ZIP)...")
        shutil.make_archive(str(archive_base), "zip", str(runtime_dir.parent), "ai_env")
        shutil.rmtree(runtime_dir)
        print("✅ Runtime komprimiert und Originalverzeichnis gelöscht.")

    def run(self, targets: List[str]) -> None:
        """Hauptmethode für das Packaging aller Targets."""
        self.prepare_offline_python()
        src_workers = Path("workers")

        if not src_workers.exists():
            print("⚠️ Keine Worker zum Packen gefunden.")
            return

        ignore_pattern = shutil.ignore_patterns(
            "venv", ".venv", "python_env", "__pycache__"
        )

        for target in targets:
            dist_target = Path(f"dist/{target}")

            # 1. Master AI Runtime bauen
            shared_dir = self.build_shared_ai_runtime(dist_target)

            # 2. Worker kopieren und leichtgewichtige Venvs bauen
            dist_workers = dist_target / "workers"
            shutil.copytree(
                src_workers, dist_workers, dirs_exist_ok=True, ignore=ignore_pattern
            )

            print(f"\n⚙️ Konfiguriere Worker in {target}...")
            for w_dir in dist_workers.iterdir():
                if w_dir.is_dir():
                    self.package_worker(w_dir, shared_dir)

            # 3. Runtime zippen
            self.compress_ai_runtime(dist_target)


def main() -> None:
    packager = WorkerPackager()
    packager.run(["PDF-A11y-GUI", "PDF-A11y-CLI"])
    print("\n🎉 Packaging & Deduplizierung erfolgreich abgeschlossen!")


if __name__ == "__main__":
    main()
