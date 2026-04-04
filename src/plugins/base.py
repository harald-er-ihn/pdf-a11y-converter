# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Plugin Architecture Base.
Definiert den Vertrag, den jeder KI-Worker erfüllen muss.
Kein Infrastructure-Leak mehr: Das Plugin liefert nur noch Metadaten.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any


class WorkerPlugin(ABC):
    """Abstrakte Basisklasse für alle PDF-Analyse Worker."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Name des Workers (z.B. 'layout_worker')."""
        pass

    @property
    @abstractmethod
    def script_name(self) -> str:
        """Name des auszuführenden Skripts (z.B. 'run_layout.py')."""
        pass

    @property
    def dependencies(self) -> List[str]:
        """Namen der Worker, die zwingend vorher laufen müssen."""
        return []

    def get_output_path(self, job_dir: Path) -> Path:
        """Standardisiert den Ausgabepfad."""
        return job_dir / f"{self.name}_result.json"

    @abstractmethod
    def get_arguments(
        self, input_pdf: Path, job_dir: Path, context: Dict[str, Any]
    ) -> List[str]:
        """
        Liefert NUR die spezifischen CLI-Argumente für den Subprozess.
        Das Routing/Executing übernimmt die Engine.
        """
        pass
