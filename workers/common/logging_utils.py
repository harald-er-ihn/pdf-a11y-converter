# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Standardized logging setup for workers.
"""

import logging


def setup_worker_logging(name: str) -> logging.Logger:
    """
    Configure standardized worker logging.

    Args:
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Verhindert, dass Handler mehrfach hinzugefügt werden
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Stoppt die Propagation zum Root-Logger (verhindert doppelte Prints)
        logger.propagate = False

    return logger
