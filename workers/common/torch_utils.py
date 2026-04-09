# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Torch runtime configuration utilities.

These helpers prevent excessive thread spawning and
improve stability in virtualized environments.
"""

import logging
import os

logger = logging.getLogger("torch-utils")


def configure_torch_runtime() -> None:
    """
    Configure PyTorch runtime settings.

    Prevents CPU thread explosion in VMs and improves
    deterministic runtime behaviour. MUST be called before heavy imports.
    """
    # 1. C++ Backend Thread-Limiter (Extrem wichtig für VMs!)
    # Dies muss vor 'import torch' passieren!
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"

    try:
        import torch  # pylint: disable=import-outside-toplevel

        # 2. Globale Gradienten-Berechnung deaktivieren (Spart ~30% RAM!)
        torch.set_grad_enabled(False)

        # 3. PyTorch native Threads limitieren
        try:
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 4. GPU Optimierung (falls vorhanden)
        if torch.cuda.is_available():
            torch.backends.cudnn.benchmark = True

    except ImportError:
        logger.debug("Torch not available. Skipping torch configuration.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Torch configuration error: %s", e)
