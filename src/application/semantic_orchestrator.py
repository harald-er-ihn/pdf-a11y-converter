# ${/src/application/semantic_orchestrator.py}
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

"""
Semantic Orchestrator: Zentrale Steuerung des PDF/UA-
Konvertierungs-pipelines.

Pattern: Orchestrator + Facade Pattern
Verantwortung: Koordination aller Worker + Reparatur-Schritte

Pipeline:
  1. Preflight-Scan
  2. Worker-Ausführung (parallel + sequenziell)
  3. TABLE REPAIR FACADE ← NEUE SCHICHT
  4. Sensor Fusion
  5. Semantic Overlay Generator
  6. veraPDF Validierung
  7. Audit Trail

Architektur: Clean Architecture + Dependency Injection
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from src.application.table_repair_facade import (
    create_table_repair_facade,
)


class SemanticOrchestrator:
    """
    Orchestriert Worker-Ausführung + Reparaturschritte.

    Zentrale Koordination für den gesamten
    Rekonstruktions-Prozess.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            logger: Optional Python logger.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.table_repair_facade = create_table_repair_facade(
            logger=self.logger
        )

    def process_table_worker_output(
        self,
        raw_tables: List[Dict[str, Any]],
        document_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Verarbeite Output vom table_worker mit
        Reparatur-Facade.

        Schritt nach table_worker.run():
          1. Extrahiere Tabellendaten
          2. Wende Reparatur-Facade an
          3. Rekonstruiere Tabellen-Objekt
          4. Sammle Audit-Metriken

        Args:
            raw_tables: Rohausgabe von table_worker
            document_metadata: Dokument-Metadaten

        Returns:
            Reparierte Tabellenliste mit Metriken
        """
        repaired_tables = []

        for table_idx, raw_table in enumerate(raw_tables):
            try:
                # Extrahiere Tabellendaten
                table_data = raw_table.get("data", [])
                table_bbox = raw_table.get("bbox", {})

                # REPAIR FACADE AUFGERUFEN
                (
                    repaired_data,
                    repair_metric,
                ) = self.table_repair_facade.repair_table_structure(
                    table_data=table_data,
                    table_metadata={
                        "id": f"table_{table_idx}",
                        "bbox": table_bbox,
                    },
                )

                # Rekonstruiere Tabellen-Objekt
                repaired_table = {
                    **raw_table,
                    "data": repaired_data,
                    "repair_metric": asdict(repair_metric),
                }

                repaired_tables.append(repaired_table)

                # Log mit korrektem F-String
                headers = repair_metric.empty_headers_inferred
                conflicts = repair_metric.type_conflicts_resolved
                self.logger.info(
                    f"Tabelle {table_idx} repariert: "
                    f"{repair_metric.status} "
                    f"(Headers: {headers}, "
                    f"Typ-Konflikte: {conflicts})"
                )

            except Exception as e:
                self.logger.error(
                    f"Fehler beim Reparieren von Tabelle {table_idx}: {str(e)}"
                )
                # Fallback: Original beibehalten
                repaired_tables.append(raw_table)

        return repaired_tables

    def apply_table_repairs(
        self,
        spatial_dom: Any,
        document_metadata: Dict[str, Any],
    ) -> Any:
        """
        Zentrale Integration: Tabellen-Reparatur
        in den Orchestrator.

        Wird aufgerufen nach table_worker,
        VOR Sensor Fusion.

        Args:
            spatial_dom: SpatialDOM-Objekt
            document_metadata: Dokument-Context

        Returns:
            Aktualisiertes SpatialDOM
        """
        if not hasattr(spatial_dom, "tables") or not spatial_dom.tables:
            self.logger.debug(
                "Keine Tabellen im SpatialDOM, überspringe Reparatur"
            )
            return spatial_dom

        self.logger.info("🔧 Wende Table Repair Facade an...")

        spatial_dom.tables = self.process_table_worker_output(
            spatial_dom.tables,
            document_metadata,
        )

        self.logger.info("✅ Table Repair Facade komplett")

        return spatial_dom

    def get_repair_summary(
        self,
        spatial_dom: Any,
    ) -> Dict[str, Any]:
        """
        Generiere Zusammenfassung aller
        durchgeführten Tabellenreparaturen.

        Für Audit Trail.

        Args:
            spatial_dom: SpatialDOM mit
                         repair_metric

        Returns:
            Aggregierte Reparatur-Statistiken
        """
        if not hasattr(spatial_dom, "tables") or not spatial_dom.tables:
            return {
                "tables_repaired": 0,
                "total_headers_inferred": 0,
                "total_type_conflicts": 0,
                "total_gaps_corrected": 0,
                "failed_repairs": 0,
            }

        summary = {
            "tables_repaired": 0,
            "total_headers_inferred": 0,
            "total_type_conflicts": 0,
            "total_gaps_corrected": 0,
            "failed_repairs": 0,
            "repairs_by_table": [],
        }

        for table in spatial_dom.tables:
            if "repair_metric" in table:
                metric = table["repair_metric"]
                summary["tables_repaired"] += 1

                headers_inf = metric.get(
                    "empty_headers_inferred",
                    0,
                )
                summary["total_headers_inferred"] += headers_inf

                type_conf = metric.get(
                    "type_conflicts_resolved",
                    0,
                )
                summary["total_type_conflicts"] += type_conf

                gaps_corr = metric.get(
                    "whitespace_gaps_corrected",
                    0,
                )
                summary["total_gaps_corrected"] += gaps_corr

                if metric.get("status") == "FAILED":
                    summary["failed_repairs"] += 1

                table_id = metric.get(
                    "table_id",
                    "unknown",
                )
                status = metric.get(
                    "status",
                    "UNKNOWN",
                )
                rows = metric.get("rows_after", 0)
                cols = metric.get("cols_after", 0)

                summary["repairs_by_table"].append(
                    {
                        "table_id": table_id,
                        "status": status,
                        "rows": rows,
                        "cols": cols,
                    }
                )

        return summary
