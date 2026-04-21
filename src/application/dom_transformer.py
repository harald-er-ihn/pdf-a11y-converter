# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
DOM Transformer Layer (Sensor Fusion).
Kapselt alle Mutationen des SpatialDOM in typsichere Operationen.
Delegiert die Konfliktauflösung an das Layout Graph Model.
"""

import logging
import re
from typing import Dict, List

from src.domain.spatial import SpatialDOM, SpatialElement
from src.domain.layout_graph import LayoutGraph

logger = logging.getLogger("pdf-converter")


class DOMTransformer:
    """Service zur typsicheren Manipulation und Fusion des SpatialDOM."""

    @classmethod
    def _validate_and_return(cls, dom: SpatialDOM) -> SpatialDOM:
        """Sichert die Integrität nach jeder Mutation strikt ab."""
        return SpatialDOM.model_validate(dom.model_dump())

    @classmethod
    def _inject_and_sort(
        cls,
        layout_elements: List[SpatialElement],
        worker_elements: List[SpatialElement],
    ) -> List[SpatialElement]:
        """
        Führt die Graph-basierte Sensor Fusion durch.
        SpatialDOM -> LayoutGraph -> Fusion -> Sorted DOM
        """
        graph = LayoutGraph.build_layout_graph(layout_elements)
        graph.fuse_worker_elements(worker_elements)
        return graph.compute_reading_order()

    @classmethod
    def merge_columns(
        cls, dom: SpatialDOM, columns: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Reichert das DOM mit Spalten-Metadaten für die Topologie an."""
        for page in dom.pages:
            if page.page_num in columns:
                page.elements.extend(columns[page.page_num])
        return cls._validate_and_return(dom)

    @classmethod
    def merge_captions(
        cls, dom: SpatialDOM, captions: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Reichert das DOM mit Captions für die Verknüpfung an."""
        for page in dom.pages:
            if page.page_num in captions:
                page.elements.extend(captions[page.page_num])
        return cls._validate_and_return(dom)

    @classmethod
    def merge_artifacts(
        cls, dom: SpatialDOM, artifacts: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Fügt Header/Footer als Artifacts typsicher in den Graphen ein."""
        for page in dom.pages:
            if page.page_num in artifacts:
                page.elements = cls._inject_and_sort(
                    page.elements, artifacts[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_signatures(
        cls, dom: SpatialDOM, signatures: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Fügt Signatur-Elemente typsicher via Graph Fusion in den DOM ein."""
        for page in dom.pages:
            if page.page_num in signatures:
                page.elements = cls._inject_and_sort(
                    page.elements, signatures[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_tables(
        cls, dom: SpatialDOM, table_pages: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Ersetzt Text durch Tabellen anhand von Constraint Solving & Bipartite Matching."""
        for page in dom.pages:
            if page.page_num in table_pages:
                page.elements = cls._inject_and_sort(
                    page.elements, table_pages[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_footnotes(
        cls, dom: SpatialDOM, footnote_pages: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        """Weist Fußnoten anhand der Graphen-Topologie typsicher zu."""
        for page in dom.pages:
            if page.page_num in footnote_pages:
                page.elements = cls._inject_and_sort(
                    page.elements, footnote_pages[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_forms(cls, dom: SpatialDOM, forms: List[SpatialElement]) -> SpatialDOM:
        """Fügt AcroForm-Felder typsicher in die erste Seite ein und sortiert."""
        if forms and dom.pages:
            dom.pages[0].elements.extend(forms)
            graph = LayoutGraph.build_layout_graph(dom.pages[0].elements)
            dom.pages[0].elements = graph.compute_reading_order()
        return cls._validate_and_return(dom)

    @classmethod
    def merge_formulas(cls, dom: SpatialDOM, formula_md: str) -> SpatialDOM:
        """Verwebt extrahierte LaTeX-Formeln typsicher in die Textstruktur."""
        if not formula_md:
            return dom

        regex = r"(\$\$|\\\[|\\\()(.*?)(\$\$|\\\]|\\\))"
        latex_formulas = [
            m.group(2).strip() for m in re.finditer(regex, formula_md, flags=re.DOTALL)
        ]

        if not latex_formulas:
            return dom

        formula_idx = 0
        for page in dom.pages:
            for el in page.elements:
                text = el.text or ""
                is_garbage = len(text) < 25 and (
                    "̂" in text or "ݏ" in text or "\\" in text
                )

                if el.type == "formula" or is_garbage:
                    if formula_idx < len(latex_formulas):
                        el.text = f"$$ {latex_formulas[formula_idx]} $$"
                        el.type = "p"
                        formula_idx += 1

        return cls._validate_and_return(dom)
