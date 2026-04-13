# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Domain Models für das Spatial DOM.
Dient als Anti-Corruption Layer zwischen KI-Ausgaben und der PDF-Generierung.
Garantiert, dass der Datenvertrag strikt eingehalten wird.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SpatialElement(BaseModel):
    """Repräsentiert ein einzelnes visuelles/semantisches Element auf dem PDF."""

    type: str
    bbox: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    text: Optional[str] = None
    alt_text: Optional[str] = None
    html: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None  # Für rekursive Listen-Items


class SpatialPage(BaseModel):
    """Repräsentiert eine physische PDF-Seite."""

    page_num: int
    width: float = 595.0
    height: float = 842.0
    elements: List[SpatialElement] = Field(default_factory=list)


class SpatialDOM(BaseModel):
    """Der Haupt-Vertrag für das Semantic Overlay Blackboard."""

    pages: List[SpatialPage] = Field(default_factory=list)
    images: Dict[str, str] = Field(default_factory=dict)
    needs_visual_reconstruction: bool = False
