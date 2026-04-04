# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Dynamischer Plugin-Loader.
Nutzt sichere, pfadbasierte Imports und Caching.
"""

import importlib.util
import inspect
import logging
from functools import lru_cache
from pathlib import Path
from typing import List

from src.plugins.base import WorkerPlugin

logger = logging.getLogger("pdf-converter")


class PluginLoader:
    """Lädt Worker-Plugins dynamisch, paketunabhängig und performant."""

    @staticmethod
    @lru_cache(maxsize=1)
    def load_all(workers_dir_str: str) -> List[WorkerPlugin]:
        """
        Sucht nach 'plugin.py' und lädt diese sicher via file_location.
        Nutzt 'str' Parameter für sicheres Caching.
        """
        workers_dir = Path(workers_dir_str)
        plugins: List[WorkerPlugin] = []

        if not workers_dir.exists():
            logger.warning("⚠️ Worker-Verzeichnis %s nicht gefunden.", workers_dir)
            return plugins

        for child in workers_dir.iterdir():
            plugin_file = child / "plugin.py"
            if child.is_dir() and plugin_file.exists():
                module_name = f"worker_plugin_{child.name}"
                try:
                    # Sicherer Import OHNE Python-Package Struktur vorauszusetzen
                    spec = importlib.util.spec_from_file_location(
                        module_name, str(plugin_file)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        for _, obj in inspect.getmembers(module, inspect.isclass):
                            if (
                                issubclass(obj, WorkerPlugin)
                                and obj is not WorkerPlugin
                            ):
                                plugins.append(obj())
                                logger.debug("🔌 Plugin geladen: %s", obj().name)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("❌ Fehler beim Laden von %s: %s", plugin_file, e)

        return plugins
