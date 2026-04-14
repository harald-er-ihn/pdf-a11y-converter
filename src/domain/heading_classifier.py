# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Multi-Signal Klassifikator für Überschriften.
Löst den Single Point of Failure defekter Font-Metriken auf.
"""

from typing import Tuple


class HeadingClassifier:
    """Gewichteter Klassifikator für PDF/UA Überschriften."""

    THRESHOLD = 2.5

    @staticmethod
    def _is_garbage(text: str) -> bool:
        """Prüft auf Formeln oder Metadaten-Artefakte."""
        if text.startswith("$$") or text.startswith("\\"):
            return True
        if "@" in text and "." in text:
            return True
        return False

    @classmethod
    def calculate_score(
        cls,
        text: str,
        el_type: str,
        true_size: float,
        is_bold: bool,
        med: float,
    ) -> float:
        """Berechnet den Confidence-Score für eine Überschrift."""
        if cls._is_garbage(text):
            return 0.0

        score = 0.0

        # 1. Font Size Score (Gewichtung der relativen Größe)
        ratio = true_size / med if med > 0 else 1.0
        if ratio > 1.15:
            score += (ratio - 1.0) * 2.5

        # 2. Font Weight Score (Fettgedruckt)
        if is_bold:
            score += 1.0

        # 3. Text Length Score (Kürzere Texte sind eher Headings)
        word_count = len(text.split())
        if word_count < 15:
            score += 0.5
        if word_count < 5:
            score += 0.5

        # 4. Docling Label Score (Vorhandenes KI-Label)
        if el_type.startswith("h"):
            score += 1.5

        return score

    @classmethod
    def is_heading(
        cls,
        text: str,
        el_type: str,
        true_size: float,
        is_bold: bool,
        med: float,
    ) -> Tuple[bool, bool]:
        """
        Entscheidet mehrdimensional, ob ein Element eine Überschrift ist.
        Gibt (is_heading, has_docling_label) zurück.
        """
        score = cls.calculate_score(text, el_type, true_size, is_bold, med)
        docling_h = el_type.startswith("h") and not cls._is_garbage(text)

        return (score >= cls.THRESHOLD) or docling_h, docling_h
