# src/domain/spatial_constraints.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Spatial Constraint Solving.
Löst geometrische und semantische Konflikte (z.B. Marker-Fallback vs. Tabellen),
ohne dass wertvolle Daten des Basis-Textblocks gelöscht werden.
"""

from difflib import SequenceMatcher
from typing import List, Tuple

from src.domain.spatial import SpatialElement


class SpatialConstraintSolver:
    """Kapselt die deterministische räumliche Subtraktion für Bounding-Box Kollisionen."""

    @classmethod
    def subtract_text_region(cls, base_text: str, sub_text: str) -> Tuple[str, str]:
        """
        Subtrahiert sub_text deterministisch aus base_text.
        Gibt (text_before, text_after) zurück und toleriert OCR-Artefakte.
        """
        if not base_text or not sub_text:
            return base_text, ""

        # FIX: Whitespace-Normalisierung für stabileres Bipartite Matching
        base_norm = " ".join(base_text.split())
        sub_norm = " ".join(sub_text.split())

        matcher = SequenceMatcher(None, base_norm, sub_norm)
        blocks = [b for b in matcher.get_matching_blocks() if b.size > 5]

        if not blocks:
            # Letzter Fallback, falls SequenceMatcher versagt
            idx = base_norm.find(sub_norm[:20])
            if idx != -1:
                return base_norm[:idx].strip(), base_norm[idx + len(sub_norm) :].strip()
            return base_norm, ""

        start_idx = blocks[0].a
        end_idx = blocks[-1].a + blocks[-1].size

        # Schutz vor extrem gestreckten Matches (z.B. wenn nur 2 Worte ganz vorne
        # und ganz hinten matchen). Nimmt dann nur den größten zusammenhängenden Block.
        if (end_idx - start_idx) > len(sub_norm) * 2.5:
            best_block = max(blocks, key=lambda b: b.size)
            start_idx = best_block.a
            end_idx = best_block.a + best_block.size

        return base_norm[:start_idx].strip(), base_norm[end_idx:].strip()

    @classmethod
    def insert_element_at_position(
        cls, base_el: SpatialElement, insert_el: SpatialElement, sub_text: str
    ) -> List[SpatialElement]:
        """
        Führt eine räumliche Subtraktion am Basis-Element durch und bettet das
        neue Element passend ein, sodass die Reading Order (Y-Achse) gewahrt bleibt.
        """
        before_text, after_text = cls.subtract_text_region(base_el.text or "", sub_text)

        result: List[SpatialElement] = []

        # Geometrische Anpassung der Bounding Boxes, damit der XY-Cut Sorter
        # (sort_by_reading_order) die Elemente später in die exakt richtige Sequenz legt.
        y_mid_top = min(max(base_el.bbox[1], insert_el.bbox[1]), base_el.bbox[3])
        y_mid_bottom = min(max(base_el.bbox[1], insert_el.bbox[3]), base_el.bbox[3])

        if before_text:
            bbox_before = [base_el.bbox[0], base_el.bbox[1], base_el.bbox[2], y_mid_top]
            result.append(
                SpatialElement(type=base_el.type, text=before_text, bbox=bbox_before)
            )

        # Injiziere das neue Element (z.B. Tabelle, Fußnote) exakt in die Lücke
        result.append(insert_el)

        if after_text:
            bbox_after = [
                base_el.bbox[0],
                y_mid_bottom,
                base_el.bbox[2],
                base_el.bbox[3],
            ]
            result.append(
                SpatialElement(type=base_el.type, text=after_text, bbox=bbox_after)
            )

        return result
