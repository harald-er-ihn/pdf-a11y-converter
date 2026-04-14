# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
DOM Transformer Layer (Sensor Fusion).
Kapselt alle Mutationen des SpatialDOM in typsichere Operationen.
Stellt sicher, dass der Domain-Contract gewahrt bleibt.
"""

import logging
import re
from typing import Dict, List

from src.domain.geometry import bbox_overlap
from src.domain.spatial import SpatialDOM, SpatialElement

logger = logging.getLogger("pdf-converter")


class DOMTransformer:
    """Service zur typsicheren Manipulation und Fusion des SpatialDOM."""

    IOU_THRESHOLD = 0.25

    @classmethod
    def _validate_and_return(cls, dom: SpatialDOM) -> SpatialDOM:
        """Sichert die Integrität nach jeder Mutation strikt ab."""
        return SpatialDOM.model_validate(dom.model_dump())

    @classmethod
    def merge_signatures(
        cls,
        dom: SpatialDOM,
        signatures: Dict[int, List[SpatialElement]],
    ) -> SpatialDOM:
        """Fügt Signatur-Elemente typsicher in den DOM ein."""
        for page in dom.pages:
            if page.page_num in signatures:
                page.elements.extend(signatures[page.page_num])
        return cls._validate_and_return(dom)

    @classmethod
    def merge_tables(
        cls,
        dom: SpatialDOM,
        table_pages: Dict[int, List[SpatialElement]],
    ) -> SpatialDOM:
        """Ersetzt Text durch Tabellen anhand robuster IoU-Kollision."""
        for page in dom.pages:
            if page.page_num in table_pages:
                t_elements = table_pages[page.page_num]
                filtered: List[SpatialElement] = []

                for base_el in page.elements:
                    overlaps = any(
                        bbox_overlap(base_el.bbox, t.bbox, cls.IOU_THRESHOLD)
                        for t in t_elements
                    )
                    if not overlaps:
                        filtered.append(base_el)

                page.elements = filtered + t_elements
        return cls._validate_and_return(dom)

    @classmethod
    def merge_footnotes(
        cls,
        dom: SpatialDOM,
        footnote_pages: Dict[int, List[SpatialElement]],
    ) -> SpatialDOM:
        """Weist Fußnoten anhand von IoU-Kollision typsicher zu."""
        for page in dom.pages:
            if page.page_num in footnote_pages:
                f_elements = footnote_pages[page.page_num]
                for base_el in page.elements:
                    overlaps = any(
                        bbox_overlap(base_el.bbox, f.bbox, cls.IOU_THRESHOLD)
                        for f in f_elements
                    )
                    if overlaps:
                        base_el.type = "Note"
        return cls._validate_and_return(dom)

    @classmethod
    def merge_forms(cls, dom: SpatialDOM, forms: List[SpatialElement]) -> SpatialDOM:
        """Fügt AcroForm-Felder typsicher in die erste Seite ein."""
        if forms and dom.pages:
            dom.pages[0].elements.extend(forms)
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
