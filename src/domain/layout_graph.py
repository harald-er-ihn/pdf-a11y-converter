# src/domain/layout_graph.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Topological Layout Graph Model (Y-Band XY-Cut 2.0).
Löst das PDF/UA Sequenz-Problem, indem nebeneinander liegende Elemente
(Tabellen, Signatures, Texte) intelligent in Y-Bändern gruppiert werden,
anstatt dumm nach der rohen Y-Achse zu sortieren.
"""

import uuid
from enum import Enum
from typing import Dict, List

from src.domain.geometry import bbox_area, bbox_intersection
from src.domain.spatial import SpatialElement
from src.domain.spatial_constraints import SpatialConstraintSolver
from src.domain.spatial_matching import SpatialMatcher


class EdgeType(Enum):
    BELOW = "below"
    ABOVE = "above"
    COLUMN_OF = "column_of"
    CAPTION_OF = "caption_of"


class LayoutEdge:
    def __init__(
        self, source: str, target: str, edge_type: EdgeType, weight: float = 1.0
    ):
        self.source = source
        self.target = target
        self.type = edge_type
        self.weight = weight


class LayoutNode:
    def __init__(
        self, element: SpatialElement, is_worker: bool = False, is_column: bool = False
    ):
        self.id = str(uuid.uuid4())
        self.element = element
        self.is_worker = is_worker
        self.is_column = is_column
        self.in_edges: List[LayoutEdge] = []
        self.out_edges: List[LayoutEdge] = []


class LayoutGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, LayoutNode] = {}

    def add_node(
        self, element: SpatialElement, is_worker: bool = False, is_column: bool = False
    ) -> LayoutNode:
        node = LayoutNode(element, is_worker, is_column)
        self.nodes[node.id] = node
        return node

    def add_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType, weight: float = 1.0
    ) -> None:
        edge = LayoutEdge(source_id, target_id, edge_type, weight)
        self.nodes[source_id].out_edges.append(edge)
        self.nodes[target_id].in_edges.append(edge)

    @classmethod
    def build_layout_graph(cls, elements: List[SpatialElement]) -> "LayoutGraph":
        graph = cls()
        col_nodes = []
        norm_nodes = []

        for el in elements:
            if el.type == "column":
                col_nodes.append(graph.add_node(el, is_column=True))
            else:
                norm_nodes.append(graph.add_node(el))

        for i, n1 in enumerate(norm_nodes):
            if col_nodes:
                best_col = None
                max_overlap = 0.0
                for c_node in col_nodes:
                    x_overlap = max(
                        0.0,
                        min(n1.element.bbox[2], c_node.element.bbox[2])
                        - max(n1.element.bbox[0], c_node.element.bbox[0]),
                    )
                    if x_overlap > max_overlap:
                        max_overlap = x_overlap
                        best_col = c_node
                if best_col:
                    graph.add_edge(n1.id, best_col.id, EdgeType.COLUMN_OF)

            for j, n2 in enumerate(norm_nodes):
                if i == j:
                    continue
                x_overlap = max(
                    0.0,
                    min(n1.element.bbox[2], n2.element.bbox[2])
                    - max(n1.element.bbox[0], n2.element.bbox[0]),
                )

                if n1.element.type == "caption" and n2.element.type in [
                    "figure",
                    "table",
                ]:
                    y_dist = min(
                        abs(n1.element.bbox[1] - n2.element.bbox[3]),
                        abs(n2.element.bbox[1] - n1.element.bbox[3]),
                    )
                    if x_overlap > 0 and y_dist < 60:
                        graph.add_edge(n1.id, n2.id, EdgeType.CAPTION_OF)

        return graph

    def fuse_worker_elements(self, worker_elements: List[SpatialElement]) -> None:
        """Architektur-Fix: Ignoriert winzige BBox-Kollisionen (verhindert Löschung von Fließtext)."""
        if not worker_elements:
            return

        for w_el in worker_elements:
            overlapping_nodes = []
            for n in list(self.nodes.values()):
                if n.is_column or n.is_worker:
                    continue
                inter = bbox_intersection(n.element.bbox, w_el.bbox)
                if inter > 0:
                    overlapping_nodes.append(n)

            is_empty = not w_el.text and not w_el.html and not w_el.items
            if is_empty and overlapping_nodes:
                best_m = max(
                    overlapping_nodes,
                    key=lambda x: bbox_intersection(x.element.bbox, w_el.bbox),
                )
                w_el.text = best_m.element.text
                if best_m.element.items:
                    w_el.items = best_m.element.items

            w_el_added = False

            if not overlapping_nodes:
                self.add_node(w_el, is_worker=True)
                continue

            for l_node in overlapping_nodes:
                area_l = bbox_area(l_node.element.bbox)
                area_w = bbox_area(w_el.bbox)
                inter = bbox_intersection(l_node.element.bbox, w_el.bbox)

                # FIX: Verhindert, dass Footnotes den kompletten Haupttext löschen!
                # Wenn die Überschneidung kleiner als 10% der Fläche ist -> ignorieren.
                if inter < area_w * 0.1 and inter < area_l * 0.1:
                    continue

                if area_l > area_w * 1.5 and inter > area_w * 0.3:
                    sub_text = SpatialMatcher._extract_text(w_el)
                    split_els = SpatialConstraintSolver.insert_element_at_position(
                        l_node.element, w_el, sub_text
                    )

                    if l_node.id in self.nodes:
                        del self.nodes[l_node.id]

                    for el in split_els:
                        is_w = el.type == w_el.type and el.bbox == w_el.bbox
                        self.add_node(el, is_worker=is_w)
                        if is_w:
                            w_el_added = True
                elif inter > area_l * 0.5 or inter > area_w * 0.5:
                    if l_node.id in self.nodes:
                        del self.nodes[l_node.id]

                        if not w_el_added:
                            self.add_node(w_el, is_worker=True)
                            w_el_added = True

            if not w_el_added:
                self.add_node(w_el, is_worker=True)

    def _sort_nodes_xy_bands(self, nodes: List[LayoutNode]) -> List[LayoutNode]:
        if not nodes:
            return []

        nodes.sort(key=lambda n: n.element.bbox[1])

        bands = []
        current_band = [nodes[0]]

        for n in nodes[1:]:
            prev = current_band[-1]
            overlap = max(
                0.0,
                min(n.element.bbox[3], prev.element.bbox[3])
                - max(n.element.bbox[1], prev.element.bbox[1]),
            )
            h1 = prev.element.bbox[3] - prev.element.bbox[1]
            h2 = n.element.bbox[3] - n.element.bbox[1]

            if overlap > 0.3 * min(h1, h2):
                current_band.append(n)
            else:
                bands.append(current_band)
                current_band = [n]

        bands.append(current_band)

        result = []
        for band in bands:
            band.sort(key=lambda n: n.element.bbox[0])
            result.extend(band)

        return result

    def compute_reading_order(self) -> List[SpatialElement]:
        valid_elements = [n.element for n in self.nodes.values() if not n.is_column]
        col_elements = [n.element for n in self.nodes.values() if n.is_column]

        final_graph = LayoutGraph()
        col_nodes = [final_graph.add_node(c, is_column=True) for c in col_elements]
        norm_nodes = [final_graph.add_node(e) for e in valid_elements]

        columns_map = {}
        unassigned = []

        for n1 in norm_nodes:
            best_col = None
            max_overlap = 0.0
            for c_node in col_nodes:
                x_overlap = max(
                    0.0,
                    min(n1.element.bbox[2], c_node.element.bbox[2])
                    - max(n1.element.bbox[0], c_node.element.bbox[0]),
                )
                if x_overlap > max_overlap:
                    max_overlap = x_overlap
                    best_col = c_node

            if best_col:
                columns_map.setdefault(best_col.id, []).append(n1)
            else:
                unassigned.append(n1)

        caption_targets = {}
        for n1 in norm_nodes:
            if n1.element.type == "caption":
                for n2 in norm_nodes:
                    if n2.element.type in ["figure", "table"]:
                        x_ov = max(
                            0.0,
                            min(n1.element.bbox[2], n2.element.bbox[2])
                            - max(n1.element.bbox[0], n2.element.bbox[0]),
                        )
                        y_dist = min(
                            abs(n1.element.bbox[1] - n2.element.bbox[3]),
                            abs(n2.element.bbox[1] - n1.element.bbox[3]),
                        )
                        if x_ov > 0 and y_dist < 60:
                            caption_targets.setdefault(n2.id, []).append(n1)

        col_nodes.sort(key=lambda c: c.element.bbox[0])
        sorted_elements = []

        def _append_node_and_captions(node: LayoutNode) -> None:
            if node.element.type != "caption":
                caps = caption_targets.get(node.id, [])
                if caps:
                    if node.element.items is None:
                        node.element.items = []
                    for cap_node in caps:
                        node.element.items.append({"text": cap_node.element.text})
                sorted_elements.append(node.element)
            else:
                is_linked = any(node in caps for caps in caption_targets.values())
                if not is_linked:
                    sorted_elements.append(node.element)

        for col in col_nodes:
            items = columns_map.get(col.id, [])
            items = self._sort_nodes_xy_bands(items)
            for item in items:
                _append_node_and_captions(item)

        unassigned = self._sort_nodes_xy_bands(unassigned)
        for item in unassigned:
            _append_node_and_captions(item)

        return sorted_elements
