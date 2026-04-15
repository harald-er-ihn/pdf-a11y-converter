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

from src.domain.spatial import SpatialDOM, SpatialElement
from src.domain.spatial_matching import SpatialMatcher
from src.domain.layout_sorting import sort_by_reading_order
from src.domain.spatial_constraints import SpatialConstraintSolver
from src.domain.geometry import bbox_area

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
        Führt DOM Injection durch. Löst Subtraktionen über den Constraint Solver,
        falls ein Layout-Block massiv größer ist als das injizierte Element
        (behebt das Marker-Fallback-Verlust-Problem).
        """
        if not worker_elements:
            return layout_elements

        current_layout = list(layout_elements)

        # Sequenzielle Verarbeitung: Löst das Problem, dass mehrere Elemente
        # (z.B. 2 Tabellen) in denselben großen Basis-Block fallen können.
        for w_el in worker_elements:
            matches = SpatialMatcher.match_elements(current_layout, [w_el])

            if matches:
                # matches liefert {layout_idx: worker_idx (0)}
                l_idx = next(iter(matches.keys()))
                l_el = current_layout[l_idx]

                area_l = bbox_area(l_el.bbox)
                area_w = bbox_area(w_el.bbox)

                # Spatial Constraint Solving: Wenn das Basis-Element massiv größer
                # ist (>50% mehr Fläche), extrahieren wir die Tabelle geometrisch.
                if area_l > area_w * 1.5:
                    sub_text = SpatialMatcher._extract_text(w_el)
                    split_els = SpatialConstraintSolver.insert_element_at_position(
                        l_el, w_el, sub_text
                    )
                    # Ersetze den massiven Block durch die gesplitteten Fragmente
                    current_layout = (
                        current_layout[:l_idx] + split_els + current_layout[l_idx + 1 :]
                    )
                else:
                    # Reguläre Injection (direkter Replace bei ähnlicher Größe)
                    current_layout[l_idx] = w_el
            else:
                current_layout.append(w_el)

        return sort_by_reading_order(current_layout)

    @classmethod
    def merge_signatures(
        cls,
        dom: SpatialDOM,
        signatures: Dict[int, List[SpatialElement]],
    ) -> SpatialDOM:
        """Fügt Signatur-Elemente typsicher via Injection in den DOM ein."""
        for page in dom.pages:
            if page.page_num in signatures:
                page.elements = cls._inject_and_sort(
                    page.elements, signatures[page.page_num]
                )
        return cls._validate_and_return(dom)

    @classmethod
    def merge_tables(
        cls,
        dom: SpatialDOM,
        table_pages: Dict[int, List[SpatialElement]],
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
        cls,
        dom: SpatialDOM,
        footnote_pages: Dict[int, List[SpatialElement]],
    ) -> SpatialDOM:
        """Weist Fußnoten anhand von Text-Aware Bipartite Matching typsicher zu."""
        for page in dom.pages:
            if page.page_num in footnote_pages:
                f_elements = footnote_pages[page.page_num]
                matches = SpatialMatcher.match_elements(page.elements, f_elements)

                for idx, base_el in enumerate(page.elements):
                    if idx in matches:
                        base_el.type = "Note"

                page.elements = sort_by_reading_order(page.elements)
        return cls._validate_and_return(dom)

    @classmethod
    def merge_forms(cls, dom: SpatialDOM, forms: List[SpatialElement]) -> SpatialDOM:
        """Fügt AcroForm-Felder typsicher in die erste Seite ein."""
        if forms and dom.pages:
            dom.pages[0].elements.extend(forms)
            dom.pages[0].elements = sort_by_reading_order(dom.pages[0].elements)
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
