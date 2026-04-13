# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Runner für Experten-Worker.
Kapselt Subprocesses, Venv-Pfade, UTF-8 Encodings und Telemetrie-Blocker.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from src.plugins.workers import WorkerManifest

logger = logging.getLogger("pdf-converter")


class WorkerRunner:
    """Führt Worker hermetisch isoliert und fehlerresistent aus."""

    @staticmethod
    def execute(manifest: WorkerManifest, args: List[str]) -> Tuple[bool, str]:
        """
        Startet den Worker-Prozess.
        Gibt ein Tupel (Erfolg, Stderr-Log) zurück.
        """
        script_path = manifest.worker_dir / manifest.script

        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        if getattr(sys, "frozen", False) and sys.platform == "win32":
            internal_dir = Path(sys.executable).parent / "_internal"
            py_exe = internal_dir / "python_runtime" / "python.exe"
            libs_dir = manifest.worker_dir / "libs"
            env["PYTHONPATH"] = str(libs_dir)
        else:
            worker_venv = manifest.worker_dir / "venv"
            py_exe = (
                worker_venv / "Scripts" / "python.exe"
                if sys.platform == "win32"
                else worker_venv / "bin" / "python"
            )

        if not py_exe.exists():
            err_msg = f"Python fehlt für '{manifest.name}': {py_exe}"
            logger.error("❌ %s", err_msg)
            return False, err_msg

        cmd = [str(py_exe), str(script_path)]
        cmd.extend(args)

        env["HF_HUB_OFFLINE"] = "1"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        env["DISABLE_TELEMETRY"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=manifest.timeout_sec,
            )
            return True, ""
        except subprocess.TimeoutExpired:
            err_msg = f"Timeout ({manifest.timeout_sec}s) überschritten."
            logger.error("❌ %s in '%s'.", err_msg, manifest.name)
            return False, err_msg
        except subprocess.CalledProcessError as e:
            # Wir loggen hier nicht mehr rot! Der Orchestrator entscheidet gleich,
            # ob es ein Managed Error (JSON Contract) oder ein echter Crash ist.
            return False, e.stderr or f"Unbekannter Fehler (Code {e.returncode})"
        except Exception as e:  # pylint: disable=broad-exception-caught
            err_msg = f"Systemfehler bei '{manifest.name}': {e}"
            logger.error("❌ %s", err_msg)
            return False, err_msg
