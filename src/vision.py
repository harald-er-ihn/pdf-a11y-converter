# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Proxy für den Vision-Worker.
Delegiert die Bildanalyse an einen isolierten Subprozess.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict

from src.config import _get_app_base_dir, get_worker_python

logger = logging.getLogger("pdf-converter")


def get_image_descriptions(
    images_dict: Dict[str, str], job_dir: Path
) -> Dict[str, str]:
    """Ruft den isolierten Vision-Worker auf, um Alt-Texte zu generieren."""
    if not images_dict:
        return {}

    input_json = job_dir / "vision_input.json"
    output_json = job_dir / "vision_output.json"

    if output_json.exists():
        logger.info(
            "✅ Überspringe Vision-Analyse (Ergebnisse aus vorherigem Lauf geladen)."
        )
        with open(output_json, "r", encoding="utf-8") as f:
            return json.load(f)

    with open(input_json, "w", encoding="utf-8") as f:
        json.dump(images_dict, f, ensure_ascii=False, indent=2)

    worker_name = "vision_worker"
    base_dir = _get_app_base_dir()
    script_path = base_dir / "workers" / worker_name / "run_vision.py"
    python_exe = get_worker_python(worker_name)

    if not script_path.exists():
        logger.error(f"❌ Vision-Worker Skript nicht gefunden: {script_path}")
        raise RuntimeError("Vision-Worker fehlt.")

    cmd = [
        str(python_exe),
        str(script_path),
        "--input",
        str(input_json),
        "--output",
        str(output_json),
    ]

    # 🚀 FIX FÜR CRASH CODE 103 (PyInstaller Venv Dependency Hell Prevention)
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    logger.info("▶ Starte Spezialist: 'vision_worker'...")

    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, env=env
        )
        logger.debug(f"[vision_worker STDOUT]\n{result.stdout}")

        if output_json.exists():
            with open(output_json, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            raise RuntimeError("Vision-Worker hat keine Ausgabedatei generiert.")

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Vision-Worker ist abgestürzt (Code {e.returncode}).")
        logger.error(f"Error Log:\n{e.stderr}")
        raise RuntimeError("Fehler bei der Bildanalyse. Prozess abgebrochen.") from e
