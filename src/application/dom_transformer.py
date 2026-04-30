# src/application/dom_transformer.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
DOM Transformer Layer (Sensor Fusion).
Kapselt alle Mutationen des SpatialDOM in typsichere Operationen.
Behebt PDF Fragmentierungs-Fehler (Zeilen-/Seitenumbrüche) durch
aggressives Paragraph-Merging.
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
        """Fusioniert zersplitterte Textblöcke (P) zu sauberen Absätzen."""
        if not elements:
            return []

        merged = []
        curr = elements[0].model_copy(deep=True)

        for nxt in elements[1:]:
            if curr.type == "p" and nxt.type == "p":
                x_align = abs(curr.bbox[0] - nxt.bbox[0]) < 80.0
                h_curr = max(curr.bbox[3] - curr.bbox[1], 8.0)
                v_gap = nxt.bbox[1] - curr.bbox[3]

                # ARCHITEKTUR-FIX: Reduktion der y-Toleranz auf 1.8.
                if x_align and -20.0 <= v_gap <= (h_curr * 1.8):
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
        """Repariert Zersplitterungen nach Typografie-Korrektur."""
        for page in dom.pages:
            cleaned = [
                e
                for e in page.elements
                if e.type not in ["column", "artifact", "nonstruct"]
            ]
            for e in cleaned:
                if e.type == "figure":
                    e.text = ""

            page.elements = cls._merge_paragraphs(cleaned)
        return cls._validate_and_return(dom)

    @classmethod
    def _inject_and_sort(
        cls,
        layout_elements: List[SpatialElement],
        worker_elements: List[SpatialElement],
    ) -> List[SpatialElement]:
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
        """Cluster-basiertes BBox-Merging für defragmentierte Formeln."""
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
            new_elements = []
            skip_until = 0

            for i, el in enumerate(page.elements):
                if i < skip_until:
                    continue

                text = el.text or ""
                text_clean = text.strip()

                is_math = el.type in ["formula", "equation"]

                if not is_math and el.type == "p":
                    # 🚀 ARCHITEKTUR-FIX: Erweiterte Heuristik für zersplitterte Tectonic-Formeln.
                    # Erkennt winzige Variablen (z.B. '𝐿') als Startpunkt einer Formel,
                    # wenn sie isoliert oder in dichten Clustern auftreten.
                    looks_like_math = (
                        any(c in text_clean for c in "=+-/()[]{}<>^~_∑∫")
                        or len(text_clean) <= 2
                    )

                    if looks_like_math:
                        prev_gap = (
                            el.bbox[1] - page.elements[i - 1].bbox[3]
                            if i > 0
                            else 100.0
                        )
                        next_gap = (
                            page.elements[i + 1].bbox[1] - el.bbox[3]
                            if i + 1 < len(page.elements)
                            else 100.0
                        )

                        # Formeln stehen oft vertikal isoliert oder bilden extreme BBox-Cluster
                        if (
                            prev_gap > 15.0
                            or next_gap < 5.0
                            or any(c in text_clean for c in "=+-∑∫")
                        ):
                            is_math = True

                if is_math and formula_idx < len(latex_formulas):
                    merged_bbox = list(el.bbox)
                    j = i + 1

                    while j < len(page.elements):
                        nxt = page.elements[j]
                        nxt_text = (nxt.text or "").strip()
                        nxt_is_math = nxt.type in ["formula", "equation"]

                        if not nxt_is_math and nxt.type == "p":
                            nxt_looks_math = (
                                any(c in nxt_text for c in "=+-/()[]{}<>^~_∑∫")
                                or len(nxt_text) <= 2
                            )
                            if nxt_looks_math:
                                nxt_is_math = True

                        v_gap = nxt.bbox[1] - merged_bbox[3]

                        # Formel-Fragmente haben sehr kleine vertikale Gaps (< 60pt)
                        if v_gap < 60.0 and nxt_is_math:
                            merged_bbox = [
                                min(merged_bbox[0], nxt.bbox[0]),
                                min(merged_bbox[1], nxt.bbox[1]),
                                max(merged_bbox[2], nxt.bbox[2]),
                                max(merged_bbox[3], nxt.bbox[3]),
                            ]
                            j += 1
                        else:
                            break

                    new_elements.append(
                        SpatialElement(
                            type="formula",
                            text=f"$$ {latex_formulas[formula_idx]} $$",
                            bbox=merged_bbox,
                        )
                    )
                    skip_until = j
                    formula_idx += 1
                else:
                    new_elements.append(el)

            page.elements = new_elements

        return cls._validate_and_return(dom)
