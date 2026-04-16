# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Runner für Experten-Worker.
Implementiert Thread-sicheres GPU-Locking gegen VRAM-Kollisionen.
"""

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from src.plugins.workers import WorkerManifest

logger = logging.getLogger("pdf-converter")

# Globaler Lock zur Verhinderung von CUDA Out-Of-Memory (OOM)
_GPU_LOCK = threading.Lock()

# Liste von Workern, die exklusiven GPU-Zugriff benötigen
_GPU_WORKERS = {
    "vision_worker",
    "signature_worker",
    "translation_worker",
    "formula_worker",
}


class WorkerRunner:
    """Führt Worker hermetisch isoliert und fehlerresistent aus."""

    @staticmethod
    def _build_env(manifest: WorkerManifest) -> Tuple[Path, Dict[str, str]]:
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env["HF_HUB_OFFLINE"] = "1"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        env["DISABLE_TELEMETRY"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        if getattr(sys, "frozen", False) and sys.platform == "win32":
            int_dir = Path(sys.executable).parent / "_internal"
            py_exe = int_dir / "python_runtime" / "python.exe"
            env["PYTHONPATH"] = str(manifest.worker_dir / "libs")
        else:
            w_venv = manifest.worker_dir / "venv"
            py_exe = (
                w_venv / "Scripts" / "python.exe"
                if sys.platform == "win32"
                else w_venv / "bin" / "python"
            )

        return py_exe, env

    @staticmethod
    def _run_process(
        cmd: List[str], env: Dict[str, str], timeout: int, name: str
    ) -> Tuple[bool, str]:
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=timeout,
            )
            return True, ""
        except subprocess.TimeoutExpired:
            err = f"Timeout ({timeout}s) überschritten."
            logger.error("❌ %s in '%s'.", err, name)
            return False, err
        except subprocess.CalledProcessError as e:
            return False, e.stderr or "Unbekannter Fehler"
        except Exception as e:  # pylint: disable=broad-exception-caught
            err = f"Systemfehler bei '{name}': {e}"
            logger.error("❌ %s", err)
            return False, err

    @staticmethod
    def execute(manifest: WorkerManifest, args: List[str]) -> Tuple[bool, str]:
        """Startet den Worker-Prozess mit automatischem GPU-Locking."""
        script_path = manifest.worker_dir / manifest.script
        py_exe, env = WorkerRunner._build_env(manifest)

        if not py_exe.exists():
            msg = f"Python fehlt für '{manifest.name}': {py_exe}"
            logger.error("❌ %s", msg)
            return False, msg

        cmd = [str(py_exe), str(script_path)] + args
        needs_gpu = manifest.name in _GPU_WORKERS

        if needs_gpu:
            logger.debug("🔒 Warte auf GPU-Lock für: %s", manifest.name)
            _GPU_LOCK.acquire()

        try:
            return WorkerRunner._run_process(
                cmd, env, manifest.timeout_sec, manifest.name
            )
        finally:
            if needs_gpu:
                _GPU_LOCK.release()
                logger.debug("🔓 GPU-Lock freigegeben: %s", manifest.name)
