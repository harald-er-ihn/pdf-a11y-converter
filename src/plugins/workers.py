# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Plugin-Bridge für externe Worker.
Implementiert dynamisches Discovery (Manifests) und Dependency Injection.
"""

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("pdf-converter")


@dataclass
class WorkerManifest:
    """Repräsentiert die Fähigkeiten eines isolierten Workers."""

    name: str
    script: str
    timeout_sec: int
    phase: str
    worker_dir: Path
    accepts_force_ocr: bool = False
    requires_lang: bool = False


class PluginManager:
    """Lädt und verwaltet isolierte Experten-Worker dynamisch."""

    def __init__(self) -> None:
        self.workers_dir = self._get_workers_dir()
        self.workers = self._discover_workers()

    def _get_workers_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "workers"
        return Path(__file__).resolve().parent.parent.parent / "workers"

    def _discover_workers(self) -> List[WorkerManifest]:
        discovered = []
        if not self.workers_dir.exists():
            return discovered

        for directory in self.workers_dir.iterdir():
            if directory.is_dir():
                manifest_path = directory / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            discovered.append(
                                WorkerManifest(
                                    name=data.get("name", directory.name),
                                    script=data.get("script", "run.py"),
                                    timeout_sec=data.get("timeout_sec", 300),
                                    phase=data.get("phase", "map"),
                                    worker_dir=directory,
                                    accepts_force_ocr=data.get(
                                        "accepts_force_ocr", False
                                    ),
                                    requires_lang=data.get("requires_lang", False),
                                )
                            )
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logger.error("Fehler beim Laden von %s: %s", directory.name, e)
        return discovered

    def get_map_workers(self) -> List[WorkerManifest]:
        """Gibt alle Worker für die initialen PDF-Scans zurück."""
        return [w for w in self.workers if w.phase == "map"]

    def get_worker(self, name: str) -> Optional[WorkerManifest]:
        """Sucht einen spezifischen Worker anhand des Namens."""
        for w in self.workers:
            if w.name == name:
                return w
        return None
