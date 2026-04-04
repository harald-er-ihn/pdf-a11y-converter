# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

from pathlib import Path
from typing import List, Dict, Any
from src.plugins.base import WorkerPlugin


class LayoutWorkerPlugin(WorkerPlugin):
    @property
    def name(self) -> str:
        return "layout_worker"

    @property
    def script_name(self) -> str:
        return "run_layout.py"

    def get_arguments(
        self, input_pdf: Path, job_dir: Path, context: Dict[str, Any]
    ) -> List[str]:
        args = [
            "--input",
            str(input_pdf),
            "--output",
            str(self.get_output_path(job_dir)),
        ]
        if context.get("force_ocr"):
            args.append("--force-ocr")
        return args
