# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Memory cleanup helpers for machine learning workers.

This module provides a defensive cleanup function that triggers 
garbage collection and optionally clears GPU memory (PyTorch).
"""

import gc
import logging

logger = logging.getLogger("worker-cleanup")


def cleanup_memory(aggressive: bool = False) -> None:
    """
    Erzwingt Garbage Collection und leert den PyTorch VRAM.
    
    WICHTIG: Der Aufrufer (Worker) muss die großen Objekte VOR Aufruf 
    dieser Funktion mit `del objekt` aus seinem lokalen Scope löschen!

    Args:
        aggressive: If True, executes additional GPU synchronization.
    """
    # 1. Zwingt Python, alle unreferenzierten Objekte sofort zu vernichten
    gc.collect()

    # 2. PyTorch VRAM Cache leeren (Fail-Fast: Try-Except)
    try:
        import torch  # pylint: disable=import-outside-toplevel

        if torch.cuda.is_available():
            if aggressive:
                torch.cuda.synchronize()
            torch.cuda.empty_cache()
            
    except ImportError:
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("GPU Cache konnte nicht geleert werden: %s", e)
