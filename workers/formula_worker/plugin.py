# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

from pathlib import Path
from typing import List, Dict, Any
from src.plugins.base import WorkerPlugin


class FormulaWorkerPlugin(WorkerPlugin):
    @property
    def name(self) -> str:
        return "formula_worker"

    @property
    def script_name(self) -> str:
        return "run_formula.py"

    def get_arguments(
        self, input_pdf: Path, job_dir: Path, context: Dict[str, Any]
    ) -> List[str]:
        return [
            "--input",
            str(input_pdf),
            "--output",
            str(self.get_output_path(job_dir)),
        ]
