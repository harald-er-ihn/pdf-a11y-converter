# ${/tests/test_table_repair_facade.py}
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

"""
Unit-Tests für Table Repair Facade.

Test-Abdeckung:
  - Empty Header Inference
  - Type Conflict Resolution
  - Whitespace Gap Detection
  - End-to-End Repair
  - Real-World Cases aus Test_03_Tables.pdf
"""

import pytest
from src.application.table_repair_facade import (
    CellType,
    CellTypeInferencer,
    HeaderCellInferencer,
    TableRepairFacade,
)


class TestCellTypeInferencer:
    """Test Typ-Inferenz-Logik."""

    def test_infer_numeric_cell(self):
        """Erkenne numerische Zellen."""
        assert CellTypeInferencer.infer_cell_type("123") == CellType.NUMBER
        assert CellTypeInferencer.infer_cell_type("99.98") == CellType.NUMBER
        assert CellTypeInferencer.infer_cell_type("15.000") == CellType.NUMBER

    def test_infer_text_cell(self):
        """Erkenne Text-Zellen."""
        assert CellTypeInferencer.infer_cell_type("Node-01") == CellType.TEXT
        assert CellTypeInferencer.infer_cell_type("Aktiv") == CellType.TEXT

    def test_infer_date_cell(self):
        """Erkenne Datums-Zellen."""
        assert (
            CellTypeInferencer.infer_cell_type("12.03.2026") == CellType.DATE
        )
        assert (
            CellTypeInferencer.infer_cell_type("2026-03-12") == CellType.DATE
        )

    def test_infer_empty_cell(self):
        """Erkenne leere Zellen."""
        assert CellTypeInferencer.infer_cell_type("") == CellType.EMPTY
        assert CellTypeInferencer.infer_cell_type(None) == CellType.EMPTY

    def test_infer_dominant_column_type(self):
        """Berechne dominanten Spaltentyp."""
        column = [
            "Node-01",
            "Node-02",
            "Node-03",
            "Node-04",
        ]
        dominant = CellTypeInferencer.infer_dominant_column_type(column)
        assert dominant == CellType.TEXT

        column_mixed = [
            "System-ID",
            "123",
            "Node-01",
            "456",
        ]
        dominant_mixed = CellTypeInferencer.infer_dominant_column_type(
            column_mixed
        )
        # 75% Mischung
        assert dominant_mixed in [
            CellType.TEXT,
            CellType.NUMBER,
        ]


class TestHeaderCellInferencer:
    """Test Header-Inferenz."""

    def test_infer_empty_header_node_column(self):
        """Inferiere leere Header-Zelle
        für Node-Spalte."""
        table_data = [
            [None, "Status", "Uptime"],
            ["Node-01", "Aktiv", "99.98"],
            ["Node-02", "Fehler", "85.40"],
        ]

        inferred = HeaderCellInferencer.infer_empty_header_cell(
            table_data,
            row_idx=0,
            col_idx=0,
        )

        assert inferred is not None
        assert isinstance(inferred, str)

    def test_detect_semantic_role_node(self):
        """Erkenne Node-Spalte."""
        sample = ["Node-01", "Node-02", "Node-03"]
        role = HeaderCellInferencer.detect_semantic_role(sample)
        assert role == "System_ID"

    def test_detect_semantic_role_status(self):
        """Erkenne Status-Spalte."""
        sample = ["Aktiv", "Fehler", "Online"]
        role = HeaderCellInferencer.detect_semantic_role(sample)
        assert role == "Status"


class TestTableRepairFacade:
    """Integration-Tests für komplette
    Reparatur."""

    def test_repair_empty_headers(self):
        """Repariere leere Header-Zelle."""
        table_data = [
            [None, "Status", "Uptime"],
            ["Node-01", "Aktiv", "99.98"],
        ]

        facade = TableRepairFacade()
        repaired, metric = facade.repair_table_structure(table_data)

        assert repaired[0][0] is not None
        assert repaired[0][0] != ""
        assert metric.empty_headers_inferred == 1

    def test_repair_mixed_type_column(self):
        """Repariere Mixed-Type-Spalte."""
        table_data = [
            ["System-ID", "Status", "Uptime"],
            ["Node-01", "Aktiv", "99.98"],
            ["Node-02", "Fehler", "85.40"],
        ]

        facade = TableRepairFacade()
        repaired, metric = facade.repair_table_structure(table_data)

        assert metric.status == "SUCCESS"
        assert len(repaired) == len(table_data)

    def test_repair_fails_on_empty_table(self):
        """Fail-Fast bei leerer Tabelle."""
        facade = TableRepairFacade()

        with pytest.raises(ValueError):
            facade.repair_table_structure([])

    def test_repair_maintains_table_dimensions(
        self,
    ):
        """Bewahre Tabelledimensionen."""
        table_data = [
            [None, "B", "C"],
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ]

        facade = TableRepairFacade()
        repaired, metric = facade.repair_table_structure(table_data)

        assert metric.rows_before == metric.rows_after
        assert metric.cols_before == metric.cols_after


class TestRealWorldCase:
    """Test mit Daten aus Test_03_Tables.pdf."""

    def test_repair_statistical_report_table(
        self,
    ):
        """
        Repariere echte Tabelle aus
        Quality Report.

        Quelle: Test_03_Tables.md
        Problem: Header-Zelle leer,
        Mixed Types
        """
        table_data = [
            [
                None,
                "Q1 2026",
                "Q2 2026",
                "Q3 2026",
                "Q4 2026",
            ],
            [
                "Nord",
                15000,
                18500,
                14200,
                21000,
            ],
            [
                "Süd",
                12300,
                13100,
                11900,
                16400,
            ],
            [
                "Ost",
                8400,
                9200,
                8800,
                10100,
            ],
            [
                "West",
                19800,
                22400,
                21100,
                25600,
            ],
        ]

        facade = TableRepairFacade()
        repaired, metric = facade.repair_table_structure(table_data)

        # Header sollte repariert sein
        assert repaired[0][0] is not None
        assert metric.empty_headers_inferred >= 1
        assert metric.status == "SUCCESS"

    def test_repair_system_metrics_table(self):
        """Repariere System-Metriken-Tabelle."""
        table_data = [
            [
                None,
                "Status",
                "Uptime (%)",
                "Letzter Neustart",
                "Warnungen",
            ],
            [
                "Node-01",
                "Aktiv",
                99.98,
                "12.03.2026",
                "Keine",
            ],
            [
                "Node-02",
                "Fehler",
                85.40,
                "14.04.2026",
                "RAM Limit",
            ],
            [
                "DB-Main",
                "Aktiv",
                100.0,
                "01.01.2026",
                "Keine",
            ],
        ]

        facade = TableRepairFacade()
        repaired, metric = facade.repair_table_structure(table_data)

        # Validierung
        assert metric.rows_after == 4
        assert metric.cols_after == 5
        assert repaired[0][0] != ""
        assert metric.status == "SUCCESS"
