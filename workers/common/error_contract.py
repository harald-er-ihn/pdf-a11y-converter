# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Central Error Contract für isolierte Worker.
Standardisiert die Fehlerkommunikation zwischen Worker und Orchestrator.
"""

import json
import traceback
from pathlib import Path
from typing import Optional


def write_error_contract(
    output_path: Path,
    error_type: str,
    message: str,
    details: Optional[str] = None,
) -> None:
    """
    Schreibt ein standardisiertes Fehlerobjekt als JSON.

    Args:
        output_path: Pfad zur Ausgabedatei (wo der Orchestrator das Ergebnis erwartet)
        error_type: Kurzname des Fehlers (z.B. 'OutOfMemory', 'ServiceOffline')
        message: Lesbare Fehlermeldung für den Endnutzer
        details: Optionaler technischer Stacktrace für Debugging
    """
    error_data = {
        "status": "error",
        "error": {
            "type": error_type,
            "message": message,
            "details": details or traceback.format_exc(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(error_data, f, ensure_ascii=False, indent=2)
