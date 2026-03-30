# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
import warnings


def pytest_configure(config):
    """
    Globale Konfiguration für alle Tests.
    Unterdrückt die nervigen urllib3 Kompatibilitäts-Warnungen von 'requests',
    bevor irgendein Test ausgeführt wird.
    """
    warnings.filterwarnings("ignore", category=UserWarning, module="requests")
    warnings.filterwarnings("ignore", message=".*urllib3.*")
