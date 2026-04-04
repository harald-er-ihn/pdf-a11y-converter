# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
DAG (Directed Acyclic Graph) Execution Framework.
Ersetzt serielle Schleifen durch topologisch sortierte, parallele Ausführung.
Vergleichbar mit Apache Airflow, aber leichtgewichtig und 100% On-Premise.
"""

import graphlib
import logging
from concurrent.futures import ThreadPoolExecutor, Future, wait, FIRST_COMPLETED
from typing import Dict, Any, Callable, List

logger = logging.getLogger("pdf-converter")


class DAGTask:
    """Kapselt eine ausführbare Einheit innerhalb des DAGs."""

    def __init__(
        self, name: str, action: Callable[[], Any], dependencies: List[str] = None
    ) -> None:
        self.name = name
        self.action = action
        self.dependencies = dependencies or []


class DAGExecutor:
    """Führt Tasks basierend auf ihren Abhängigkeiten parallel aus."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def execute(self, tasks: List[DAGTask]) -> Dict[str, Any]:
        """
        Berechnet den Abhängigkeitsgraphen und führt Tasks parallel aus.
        Fail-Fast: Bricht ab, wenn eine zyklische Abhängigkeit besteht.
        """
        task_dict = {t.name: t for t in tasks}
        graph = {t.name: set(t.dependencies) for t in tasks}

        try:
            # Native C-Bibliothek für Topologische Sortierung (Python 3.9+)
            sorter = graphlib.TopologicalSorter(graph)
            sorter.prepare()
        except graphlib.CycleError as e:
            logger.error("❌ Zyklische Abhängigkeit im DAG entdeckt: %s", e)
            raise RuntimeError("DAG Evaluierung fehlgeschlagen.") from e

        results: Dict[str, Any] = {}
        futures: Dict[Future, str] = {}

        logger.info(
            "🚀 Starte DAG Pipeline mit %s maximalen Workern...", self.max_workers
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while sorter.is_active():
                # Alle Tasks, deren Abhängigkeiten erfüllt sind, in den Pool werfen
                for node_name in sorter.get_ready():
                    task = task_dict[node_name]
                    logger.debug("➡️ Submitting Task: %s", node_name)
                    futures[pool.submit(task.action)] = node_name

                if not futures:
                    break

                # Auf den Abschluss des ERSTEN fertigen Tasks warten
                done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)

                for future in done:
                    node_name = futures.pop(future)
                    try:
                        results[node_name] = future.result()
                        logger.info("✅ Task '%s' abgeschlossen.", node_name)
                        # Dem Sorter mitteilen, dass Node fertig ist (gibt nächste frei)
                        sorter.done(node_name)
                    except Exception as e:
                        logger.error(
                            "❌ Task '%s' ist fehlgeschlagen: %s", node_name, e
                        )
                        # Fail-Fast: Bei Fehler sofort abbrechen
                        for f in futures:
                            f.cancel()
                        raise RuntimeError(
                            f"Pipeline an Task {node_name} abgebrochen."
                        ) from e

        return results
