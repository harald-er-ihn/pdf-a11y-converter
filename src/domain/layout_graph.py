# src/domain/layout_graph.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Topological Layout Graph Model (Y-Band XY-Cut 2.0).
Löst das PDF/UA Sequenz-Problem und behebt Sensor-Fusion Konflikte
(Container Absorption, Artifact Deletion, Caption Linking) durch
robuste IoM-Heuristiken (Intersection over Minimum Area).
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
        self,
        source: str,
        target: str,
        edge_type: EdgeType,
        weight: float = 1.0,
    ):
        self.source = source
        self.target = target
        self.type = edge_type
        self.weight = weight


class LayoutNode:
    def __init__(
        self,
        element: SpatialElement,
        is_worker: bool = False,
        is_column: bool = False,
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
        self,
        element: SpatialElement,
        is_worker: bool = False,
        is_column: bool = False,
    ) -> LayoutNode:
        node = LayoutNode(element, is_worker, is_column)
        self.nodes[node.id] = node
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        weight: float = 1.0,
    ) -> None:
        edge = LayoutEdge(source_id, target_id, edge_type, weight)
        self.nodes[source_id].out_edges.append(edge)
        self.nodes[target_id].in_edges.append(edge)

    @classmethod
    def build_layout_graph(
        cls, elements: List[SpatialElement]
    ) -> "LayoutGraph":
        graph = cls()
        col_nodes = []
        norm_nodes = []

        for el in elements:
            if el.type == "column":
                col_nodes.append(graph.add_node(el, is_column=True))
            else:
                norm_nodes.append(graph.add_node(el))

        # Spaltenzuordnung
        for n1 in norm_nodes:
            if col_nodes:
                best_col = None
                max_overlap = 0.0
                for c_node in col_nodes:
                    x_ov = max(
                        0.0,
                        min(n1.element.bbox[2], c_node.element.bbox[2])
                        - max(n1.element.bbox[0], c_node.element.bbox[0]),
                    )
                    if x_ov > max_overlap:
                        max_overlap = x_ov
                        best_col = c_node
                if best_col:
                    graph.add_edge(n1.id, best_col.id, EdgeType.COLUMN_OF)

        return graph

    def fuse_worker_elements(
        self, worker_elements: List[SpatialElement]
    ) -> None:
        """
        Architektur-Fix: Nutzt strikte IoM Logik (Container Absorption).
        Löscht Layout-Elemente, die in Worker-Containern (Tabellen/Figuren)
        oder Artifacts (Header/Footer) liegen.
        """
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

            is_container = w_el.type in ["table", "figure", "form"]
            is_artifact = w_el.type in ["artifact", "header", "footer"]
            w_el_added = False

            if not overlapping_nodes:
                if not is_artifact:
                    self.add_node(w_el, is_worker=True)
                continue

            for l_node in overlapping_nodes:
                area_l = max(bbox_area(l_node.element.bbox), 1.0)
                area_w = max(bbox_area(w_el.bbox), 1.0)
                inter = bbox_intersection(l_node.element.bbox, w_el.bbox)

                # Container Absorption (Tabelle/Figure schluckt Zellen/Texte)
                if is_container:
                    if (inter / area_l) > 0.4:
                        if l_node.id in self.nodes:
                            del self.nodes[l_node.id]
                        if not w_el_added:
                            self.add_node(w_el, is_worker=True)
                            w_el_added = True
                    continue

                # Artifact Deletion (Header/Footer löschen)
                if is_artifact:
                    if (inter / area_l) > 0.4:
                        if l_node.id in self.nodes:
                            del self.nodes[l_node.id]
                    continue

                # Spatial Constraint Solving (z.B. Marker P vs Spezifisches Tag)
                if area_l > area_w * 1.5 and inter > area_w * 0.3:
                    sub_text = SpatialMatcher._extract_text(w_el)
                    split_els = (
                        SpatialConstraintSolver.insert_element_at_position(
                            l_node.element, w_el, sub_text
                        )
                    )
                    if l_node.id in self.nodes:
                        del self.nodes[l_node.id]
                    for el in split_els:
                        is_w = (el.type == w_el.type) and (
                            el.bbox == w_el.bbox
                        )
                        self.add_node(el, is_worker=is_w)
                        if is_w:
                            w_el_added = True
                else:
                    iou = inter / max(area_l + area_w - inter, 1.0)
                    if iou > 0.6:
                        if l_node.id in self.nodes:
                            del self.nodes[l_node.id]
                            if not w_el_added:
                                self.add_node(w_el, is_worker=True)
                                w_el_added = True

            # Fallback Addition
            if not w_el_added and not is_artifact:
                self.add_node(w_el, is_worker=True)

    def _sort_nodes_xy_bands(
        self, nodes: List[LayoutNode]
    ) -> List[LayoutNode]:
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
        valid_elements = [
            n.element for n in self.nodes.values() if not n.is_column
        ]
        col_elements = [n.element for n in self.nodes.values() if n.is_column]

        final_graph = LayoutGraph()
        col_nodes = [
            final_graph.add_node(c, is_column=True) for c in col_elements
        ]
        norm_nodes = [final_graph.add_node(e) for e in valid_elements]

        columns_map = {}
        unassigned = []

        for n1 in norm_nodes:
            best_col = None
            max_overlap = 0.0
            for c_node in col_nodes:
                x_ov = max(
                    0.0,
                    min(n1.element.bbox[2], c_node.element.bbox[2])
                    - max(n1.element.bbox[0], c_node.element.bbox[0]),
                )
                if x_ov > max_overlap:
                    max_overlap = x_ov
                    best_col = c_node

            if best_col:
                columns_map.setdefault(best_col.id, []).append(n1)
            else:
                unassigned.append(n1)

        # Robuste Caption-Zuordnung (Toleriert Einrückungen bis -50pt)
        caption_targets = {}
        for n1 in norm_nodes:
            if n1.element.type == "caption":
                best_target = None
                best_dist = 9999.0
                for n2 in norm_nodes:
                    if n2.element.type in ["figure", "table"]:
                        x_ov = max(
                            -50.0,
                            min(n1.element.bbox[2], n2.element.bbox[2])
                            - max(n1.element.bbox[0], n2.element.bbox[0]),
                        )
                        y_dist = min(
                            abs(n1.element.bbox[1] - n2.element.bbox[3]),
                            abs(n2.element.bbox[1] - n1.element.bbox[3]),
                        )
                        if x_ov > -50.0 and y_dist < 100.0:
                            if y_dist < best_dist:
                                best_dist = y_dist
                                best_target = n2

                if best_target:
                    caption_targets.setdefault(best_target.id, []).append(n1)

        col_nodes.sort(key=lambda c: c.element.bbox[0])
        sorted_elements = []

        def _append_node_and_captions(node: LayoutNode) -> None:
            if node.element.type != "caption":
                caps = caption_targets.get(node.id, [])
                if caps:
                    if node.element.items is None:
                        node.element.items = []
                    for cap_node in caps:
                        node.element.items.append(
                            {"text": cap_node.element.text}
                        )
                sorted_elements.append(node.element)
            else:
                is_linked = any(
                    node in caps for caps in caption_targets.values()
                )
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
