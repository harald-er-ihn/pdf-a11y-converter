# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Topological Layout Graph Model.
Modelliert das Dokument als deterministischen Graphen, um Sensor Fusion
und PDF/UA Lesereihenfolgen robust gegen Koordinatenfehler zu machen.
"""

import uuid
from enum import Enum
from typing import Dict, List

from src.domain.geometry import bbox_area
from src.domain.spatial import SpatialElement
from src.domain.spatial_constraints import SpatialConstraintSolver
from src.domain.spatial_matching import SpatialMatcher


class EdgeType(Enum):
    BELOW = "below"
    ABOVE = "above"
    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    INSIDE = "inside"
    CAPTION_OF = "caption_of"
    COLUMN_OF = "column_of"
    OVERLAPS = "overlaps"


class LayoutEdge:
    """Repräsentiert eine topologische Beziehung zwischen zwei Elementen."""

    def __init__(self, source: str, target: str, type: EdgeType, weight: float = 1.0):
        self.source = source
        self.target = target
        self.type = type
        self.weight = weight


class LayoutNode:
    """Knoten im Layout-Graphen. Kapselt das SpatialElement."""

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
    """Graph-Based Sensor Fusion & Reading Order Pipeline."""

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
        """SCHRITT 1: SpatialDOM -> LayoutGraph Konstruktion."""
        graph = cls()
        col_nodes: List[LayoutNode] = []
        norm_nodes: List[LayoutNode] = []

        for el in elements:
            if el.type == "column":
                col_nodes.append(graph.add_node(el, is_column=True))
            else:
                norm_nodes.append(graph.add_node(el))

        # Topologie erstellen
        for i, n1 in enumerate(norm_nodes):
            # SCHRITT 5: Column Awareness
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

            # Spatial Relationships (ABOVE / BELOW / CAPTIONS)
            for j, n2 in enumerate(norm_nodes):
                if i == j:
                    continue

                x_overlap = max(
                    0.0,
                    min(n1.element.bbox[2], n2.element.bbox[2])
                    - max(n1.element.bbox[0], n2.element.bbox[0]),
                )

                if x_overlap > 0:
                    # Y-Achsen Sequenz
                    if n1.element.bbox[1] >= n2.element.bbox[3] - 10:
                        dist = n1.element.bbox[1] - n2.element.bbox[3]
                        if dist < 150:
                            graph.add_edge(
                                n2.id, n1.id, EdgeType.BELOW, weight=1 / (dist + 1)
                            )
                            graph.add_edge(
                                n1.id, n2.id, EdgeType.ABOVE, weight=1 / (dist + 1)
                            )

                # SCHRITT 4: Caption Detection
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
        """SCHRITT 3: Graph-based Sensor Fusion mit Constraint Solving."""
        if not worker_elements:
            return

        w_nodes = [self.add_node(el, is_worker=True) for el in worker_elements]
        l_nodes = [
            n for n in self.nodes.values() if not n.is_worker and not n.is_column
        ]

        # Bipartite Matching
        matches = SpatialMatcher.match_elements(
            [n.element for n in l_nodes], [n.element for n in w_nodes]
        )

        for l_idx, w_idx in matches.items():
            self.add_edge(l_nodes[l_idx].id, w_nodes[w_idx].id, EdgeType.OVERLAPS)

        # Überlappungen auflösen
        for w_node in w_nodes:
            overlap_edges = [e for e in w_node.in_edges if e.type == EdgeType.OVERLAPS]
            if overlap_edges:
                l_node = self.nodes[overlap_edges[0].source]

                area_l = bbox_area(l_node.element.bbox)
                area_w = bbox_area(w_node.element.bbox)

                if area_l > area_w * 1.5:
                    sub_text = SpatialMatcher._extract_text(w_node.element)
                    split_els = SpatialConstraintSolver.insert_element_at_position(
                        l_node.element, w_node.element, sub_text
                    )
                    del self.nodes[l_node.id]
                    for el in split_els:
                        self.add_node(el)
                else:
                    l_node.element = w_node.element

                del self.nodes[w_node.id]
            else:
                w_node.is_worker = False

    def compute_reading_order(self) -> List[SpatialElement]:
        """SCHRITT 2: Topological Reading Order (Deterministisch)."""
        valid_elements = [
            n.element
            for n in self.nodes.values()
            if not n.is_column and not n.is_worker
        ]
        col_elements = [n.element for n in self.nodes.values() if n.is_column]

        # Sauberer Graph-Rebuild nach Fusion für deterministische Topologie
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

        # Captions zwingend verankern
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

        def _append_node_and_captions(node: LayoutNode):
            if node.element.type != "caption":
                sorted_elements.append(node.element)
                for cap_node in caption_targets.get(node.id, []):
                    sorted_elements.append(cap_node.element)
            else:
                is_linked = any(node in caps for caps in caption_targets.values())
                if not is_linked:
                    sorted_elements.append(node.element)

        for col in col_nodes:
            items = columns_map.get(col.id, [])
            items.sort(key=lambda n: n.element.bbox[1])
            for item in items:
                _append_node_and_captions(item)

        unassigned.sort(key=lambda n: n.element.bbox[1])
        for item in unassigned:
            _append_node_and_captions(item)

        return sorted_elements
