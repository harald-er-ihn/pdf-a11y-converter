# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Hardware-Aware Runtime Optimizer.
Wird im Kontext der isolierten AI-Runtime aufgerufen, um die Hardware
zu analysieren (CUDA, bfloat16, CPU-Cores) ohne den GUI-Prozess zu belasten.
"""

import json
import os


def detect_hardware() -> dict:
    """Erkennt die verfügbare Hardware und Torch-Fähigkeiten."""
    info = {
        "cuda": False,
        "gpu_name": None,
        "bf16": False,
        "cpu_count": os.cpu_count() or 4,
    }

    try:
        import torch

        if torch.cuda.is_available():
            info["cuda"] = True
            info["gpu_name"] = torch.cuda.get_device_name(0)

            # Compute Capability >= 8.0 (Ampere) unterstützt natives bfloat16
            cap = torch.cuda.get_device_capability(0)
            if cap[0] >= 8:
                info["bf16"] = True
    except ImportError:
        pass

    return info


def main() -> None:
    """Gibt das Ergebnis als parsbaren JSON-String an stdout aus."""
    hw_info = detect_hardware()
    print(json.dumps(hw_info))


if __name__ == "__main__":
    main()
