#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Generiert den Architektur-Graphen lokal und offline.
Scannt das Verzeichnis 'workers/' dynamisch, um alle Plugin-Module
(Isolierte Venvs) automatisch in die Clean Architecture zu integrieren.
"""

import json
from pathlib import Path
import graphviz


def get_dynamic_workers() -> list[dict]:
    """
    Scannt das 'workers/' Verzeichnis und extrahiert Metadaten für alle
    vorhandenen Plugin-Worker (ignoriert Hilfsverzeichnisse).
    """
    # Berücksichtigt den Aufruf aus dem Root- oder tools/-Verzeichnis
    base_dir = Path(__file__).resolve().parent.parent
    workers_dir = base_dir / "workers"
    workers = []

    if not workers_dir.exists():
        return workers

    for d in workers_dir.iterdir():
        # Ignoriere Utils und versteckte Ordner
        if (
            d.is_dir()
            and d.name not in ("common", "__pycache__")
            and not d.name.startswith(".")
        ):
            manifest_path = d / "manifest.json"

            # Standardname (bereinigt "worker_" und "_worker")
            clean_name = d.name.replace("worker_", "").replace("_worker", "")
            display_name = " ".join(p.capitalize() for p in clean_name.split("_"))

            script_name = "run.py"

            # Versuche, das Manifest für exaktere Daten auszulesen
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        script_name = data.get("script", script_name)
                except Exception:
                    pass

            workers.append(
                {
                    "id": d.name,
                    # Zweizeiliges Label: Oben der aufgeräumte Name, unten das aufgerufene Skript
                    "label": f"{display_name}\n[{script_name}]",
                }
            )

    # Alphabetisch sortieren für deterministisches Rendering des Graphen
    workers.sort(key=lambda w: w["id"])
    return workers


def generate_architecture_graph() -> None:
    """Erstellt die SVG-Visualisierung der Systemarchitektur."""
    dot = graphviz.Digraph("PDF_A11y_Architektur", format="svg")
    dot.attr(
        bgcolor="transparent",
        rankdir="LR",
        fontname="Arial",
        fontsize="12",
        splines="ortho",
        nodesep="0.6",
        ranksep="0.8",
    )
    dot.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname="Arial",
        fontsize="11",
        color="#333333",
    )

    # Lade die Worker dynamisch
    dynamic_workers = get_dynamic_workers()

    # User Input
    dot.node("User", "Benutzer\n(GUI / CLI)", fillcolor="#2b5e8f", fontcolor="white")

    # Domain Layer Cluster
    with dot.subgraph(name="cluster_domain") as domain:
        domain.attr(
            style="dashed",
            color="#2ca02c",
            label="Domain Layer (Core Rules)",
            fontcolor="#2ca02c",
            fontname="Arial bold",
        )
        domain.node(
            "CoordAdapter",
            "CoordinateAdapter\n[Fail-Fast Normalization]",
            fillcolor="#2ca02c",
            fontcolor="white",
        )
        domain.node(
            "SpatialMatcher",
            "SpatialMatcher\n[Bipartite Text-Aware]",
            fillcolor="#2ca02c",
            fontcolor="white",
        )
        domain.node(
            "ConstraintSolver",
            "ConstraintSolver\n[BBox Subtraction]",
            fillcolor="#2ca02c",
            fontcolor="white",
        )
        domain.node(
            "LayoutGraph",
            "LayoutGraph Model\n[Topological XY-Cut]",
            fillcolor="#2ca02c",
            fontcolor="white",
            shape="hexagon",
        )

    # Application Layer Cluster
    with dot.subgraph(name="cluster_app") as app:
        app.attr(
            style="dashed",
            color="#83B818",
            label="Application Layer (Use Cases)",
            fontcolor="#83B818",
            fontname="Arial bold",
        )
        app.node(
            "Orchestrator",
            "SemanticOrchestrator\n[Workflow & Audit]",
            fillcolor="#83B818",
            fontcolor="white",
            shape="hexagon",
        )
        app.node(
            "DOMTransformer",
            "DOMTransformer\n[Sensor Fusion]",
            fillcolor="#83B818",
            fontcolor="white",
        )

    # Plugins Layer Cluster
    with dot.subgraph(name="cluster_plugins") as plugins:
        plugins.attr(
            style="dashed",
            color="#e2a929",
            label="Plugins Layer (Isolated Venvs)",
            fontcolor="#e2a929",
            fontname="Arial bold",
        )
        plugins.node(
            "PluginManager",
            "Plugin Manager\n[Manifest Discovery]",
            fillcolor="#d4af37",
            fontcolor="white",
        )

        # Dynamisches Rendering aller gefundenen Worker-Knoten
        for w in dynamic_workers:
            plugins.node(w["id"], w["label"], fillcolor="#e2a929")

        # Interne Verbindungen: Discovery -> Worker
        for w in dynamic_workers:
            plugins.edge("PluginManager", w["id"], style="dotted")

    # Infrastructure Layer Cluster
    with dot.subgraph(name="cluster_infra") as infra:
        infra.attr(
            style="dashed",
            color="#6a0dad",
            label="Infrastructure Layer",
            fontcolor="#6a0dad",
            fontname="Arial bold",
        )
        infra.node("Repair", "Repair Facade\n[PyMuPDF Fonts]", fillcolor="#d4e1f9")
        infra.node(
            "Generator",
            "PDF Generator\n[WeasyPrint Overlay]",
            fillcolor="#a0522d",
            fontcolor="white",
        )
        infra.node(
            "Validator",
            "Validation\n[VeraPDF offline]",
            fillcolor="#6a0dad",
            fontcolor="white",
        )
        infra.node(
            "VSR",
            "VSR Engine\n[StructTreeRoot Parser]",
            fillcolor="#4A6B74",
            fontcolor="white",
            shape="hexagon",
        )

    # Outputs
    dot.node(
        "OutputPDF", "Barrierefreies\nPDF/UA-1", fillcolor="#2b5e8f", fontcolor="white"
    )
    dot.node(
        "AuditLog",
        "Audit Trail\n[JSON Log]",
        fillcolor="#555555",
        fontcolor="white",
        shape="note",
    )
    dot.node(
        "VSROut",
        "Visual Screenreader\n[HTML Vorschau]",
        fillcolor="#2b5e8f",
        fontcolor="white",
    )

    # ----- CONNECTIONS -----

    # Trigger
    dot.edge("User", "Orchestrator")

    # Execution Flow
    dot.edge("Orchestrator", "PluginManager", label=" Map/Reduce", fontsize="9")

    # Dynamischer Datenfluss zurück aus den Workern zum Coordinator
    for w in dynamic_workers:
        dot.edge(w["id"], "CoordAdapter")

    # Domain Flow
    dot.edge("CoordAdapter", "DOMTransformer", label=" Normalized BBox", fontsize="9")
    dot.edge("DOMTransformer", "SpatialMatcher", style="dotted")
    dot.edge("DOMTransformer", "ConstraintSolver", style="dotted")
    dot.edge("DOMTransformer", "LayoutGraph", label=" Fusion", fontsize="9")
    dot.edge("LayoutGraph", "Repair", label=" Sorted SpatialDOM", fontsize="9")

    # Post-Processing & Infrastructure
    dot.edge("Repair", "Generator", label=" Sanitized DOM", fontsize="9")
    dot.edge("Generator", "Validator", label=" Raw PDF", fontsize="9")

    # Final Outputs
    dot.edge("Validator", "OutputPDF", label=" Verified PDF", fontsize="9")
    dot.edge(
        "Orchestrator", "AuditLog", label=" Status Log", fontsize="9", style="dashed"
    )

    # VSR Flow
    dot.edge("User", "VSR", label=" Trigger", fontsize="9", style="dashed")
    dot.edge("OutputPDF", "VSR", label=" Read Tags", fontsize="9")
    dot.edge("VSR", "VSROut")

    # Render und Speichern
    out_path = (
        Path(__file__).resolve().parent.parent / "static" / "img" / "architecture_graph"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dot.render(str(out_path), cleanup=True)
    print(f"✅ Architektur-Graph (Clean Architecture) generiert: {out_path}.svg")
    print(f"   Erkannte Plugins: {len(dynamic_workers)} Worker.")


if __name__ == "__main__":
    generate_architecture_graph()
