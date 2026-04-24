# src/application/dom_transformer.py
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
    def _merge_paragraphs(cls, elements: List[SpatialElement]) -> List[SpatialElement]:
        """Fusioniert zersplitterte Textblöcke (P) zu zusammenhängenden Absätzen."""
        if not elements:
            return []

        merged = []
        curr = elements[0].model_copy(deep=True)

        for nxt in elements[1:]:
            if curr.type == "p" and nxt.type == "p":
                x_align = abs(curr.bbox[0] - nxt.bbox[0]) < 20.0
                h_curr = max(curr.bbox[3] - curr.bbox[1], 8.0)
                v_gap = nxt.bbox[1] - curr.bbox[3]

                if x_align and -5.0 <= v_gap <= (h_curr * 2.0):
                    curr.text = f"{curr.text or ''} {nxt.text or ''}".strip()
                    curr.bbox = [
                        min(curr.bbox[0], nxt.bbox[0]),
                        min(curr.bbox[1], nxt.bbox[1]),
                        max(curr.bbox[2], nxt.bbox[2]),
                        max(curr.bbox[3], nxt.bbox[3]),
                    ]
                    continue

            merged.append(curr)
            curr = nxt.model_copy(deep=True)

        merged.append(curr)
        return merged

    @classmethod
    def optimize_reading_flow(cls, dom: SpatialDOM) -> SpatialDOM:
        """Post-Processing: Repariert Zersplitterungen nach Typografie-Korrektur."""
        for page in dom.pages:
            cleaned = [
                e
                for e in page.elements
                if e.type not in ["column", "artifact", "nonstruct"]
            ]
            for e in cleaned:
                if e.type == "figure":
                    e.text = ""  # Verhindert "0" Bug
            page.elements = cls._merge_paragraphs(cleaned)
        return cls._validate_and_return(dom)

    @classmethod
    def _inject_and_sort(
        cls,
        layout_elements: List[SpatialElement],
        worker_elements: List[SpatialElement],
    ) -> List[SpatialElement]:
        """Führt die Graph-basierte Sensor Fusion durch."""
        graph = LayoutGraph.build_layout_graph(layout_elements)
        graph.fuse_worker_elements(worker_elements)
        return graph.compute_reading_order()

    @classmethod
    def merge_columns(
        cls, dom: SpatialDOM, columns: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        for page in dom.pages:
            if page.page_num in columns:
                page.elements.extend(columns[page.page_num])
        return cls._validate_and_return(dom)

    @classmethod
    def merge_captions(
        cls, dom: SpatialDOM, captions: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
        for page in dom.pages:
            if page.page_num in captions:
                page.elements.extend(captions[page.page_num])
        return cls._validate_and_return(dom)

    @classmethod
    def merge_artifacts(
        cls, dom: SpatialDOM, artifacts: Dict[int, List[SpatialElement]]
    ) -> SpatialDOM:
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
        for page in dom.pages:
            if page.page_num in footnote_pages:
                page.elements = cls._inject_and_sort(
                    page.elements, footnote_pages[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_forms(cls, dom: SpatialDOM, forms: List[SpatialElement]) -> SpatialDOM:
        if forms and dom.pages:
            dom.pages[0].elements.extend(forms)
            graph = LayoutGraph.build_layout_graph(dom.pages[0].elements)
            dom.pages[0].elements = graph.compute_reading_order()
        return cls._validate_and_return(dom)

    @classmethod
    def merge_formulas(cls, dom: SpatialDOM, formula_md: str) -> SpatialDOM:
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

                # Verbesserte Erkennung von Docling Math-Blöcken (Sensor Fusion Fallback)
                is_math = el.type in ["formula", "equation"] or (
                    el.type == "p"
                    and (
                        "\\" in text
                        or "∑" in text
                        or "∫" in text
                        or text.strip().startswith("$$")
                        or (len(text.strip()) < 25 and "̂" in text)
                    )
                )

                if is_math:
                    if formula_idx < len(latex_formulas):
                        el.text = f"$$ {latex_formulas[formula_idx]} $$"
                        el.type = "formula"
                        formula_idx += 1

        return cls._validate_and_return(dom)
