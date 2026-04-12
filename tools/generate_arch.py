#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Generiert den Architektur-Graphen lokal und offline.
Visualisiert die neue Clean Architecture (Application, Infra, Plugins).
"""

from pathlib import Path

import graphviz


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

    # User Input
    dot.node("User", "Benutzer\n(GUI / CLI)", fillcolor="#2b5e8f", fontcolor="white")

    # Application Layer Cluster
    with dot.subgraph(name="cluster_app") as app:
        app.attr(style="dashed", color="#83B818", label="Application Layer", fontcolor="#83B818", fontname="Arial bold")
        app.node(
            "Orchestrator",
            "SemanticOrchestrator\n[Sensor Fusion & Audit]",
            fillcolor="#83B818",
            fontcolor="white",
            shape="hexagon",
        )

    # Plugins Layer Cluster
    with dot.subgraph(name="cluster_plugins") as plugins:
        plugins.attr(style="dashed", color="#e2a929", label="Plugins Layer (Isolated Venvs)", fontcolor="#e2a929", fontname="Arial bold")
        plugins.node("PluginManager", "Plugin Manager\n[Manifest Discovery]", fillcolor="#d4af37", fontcolor="white")
        
        plugins.node("W_Layout", "Layout-Experte\n[docling]", fillcolor="#e2a929")
        plugins.node("W_Table", "Tabellen-Experte\n[pdfplumber]", fillcolor="#e2a929")
        plugins.node("W_Sig", "Signatur-Experte\n[yolov8s local]", fillcolor="#e2a929")
        plugins.node("W_Vision", "Bild-Experte\n[blip]", fillcolor="#e2a929")
        plugins.node("W_Trans", "Übersetzer\n[nllb-200]", fillcolor="#e2a929")
        
        # Internal Plugin flow
        plugins.edge("PluginManager", "W_Layout", style="dotted")
        plugins.edge("PluginManager", "W_Table", style="dotted")
        plugins.edge("PluginManager", "W_Sig", style="dotted")
        plugins.edge("PluginManager", "W_Vision", style="dotted")
        plugins.edge("PluginManager", "W_Trans", style="dotted")

    # Infrastructure Layer Cluster
    with dot.subgraph(name="cluster_infra") as infra:
        infra.attr(style="dashed", color="#6a0dad", label="Infrastructure Layer", fontcolor="#6a0dad", fontname="Arial bold")
        infra.node("Repair", "Repair Facade\n[PyMuPDF Fonts]", fillcolor="#d4e1f9")
        infra.node("Generator", "PDF Generator\n[WeasyPrint Overlay]", fillcolor="#a0522d", fontcolor="white")
        infra.node("Validator", "Validation\n[VeraPDF offline]", fillcolor="#6a0dad", fontcolor="white")
        infra.node("VSR", "VSR Engine\n[StructTreeRoot Parser]", fillcolor="#4A6B74", fontcolor="white", shape="hexagon")

    # Outputs
    dot.node("OutputPDF", "Barrierefreies\nPDF/UA-1", fillcolor="#2b5e8f", fontcolor="white")
    dot.node("AuditLog", "Audit Trail\n[JSON Log]", fillcolor="#555555", fontcolor="white", shape="note")
    dot.node("VSROut", "Visual Screenreader\n[HTML Vorschau]", fillcolor="#2b5e8f", fontcolor="white")

    # ----- CONNECTIONS -----
    
    # Trigger
    dot.edge("User", "Orchestrator")
    
    # Discovery & Execution
    dot.edge("Orchestrator", "PluginManager", label=" Load Manifests", fontsize="9")
    
    # Data flow back to Orchestrator (Blackboard)
    dot.edge("W_Layout", "Orchestrator")
    dot.edge("W_Table", "Orchestrator")
    dot.edge("W_Sig", "Orchestrator")
    dot.edge("W_Vision", "Orchestrator")
    dot.edge("W_Trans", "Orchestrator")

    # Post-Processing
    dot.edge("Orchestrator", "Repair", label=" Spatial DOM", fontsize="9")
    dot.edge("Repair", "Generator", label=" Sanitized DOM", fontsize="9")
    dot.edge("Generator", "Validator", label=" Raw PDF", fontsize="9")
    
    # Final Outputs
    dot.edge("Validator", "OutputPDF", label=" Verified PDF", fontsize="9")
    dot.edge("Orchestrator", "AuditLog", label=" JSON Status", fontsize="9", style="dashed")
    
    # VSR Flow
    dot.edge("User", "VSR", label=" Trigger", fontsize="9", style="dashed")
    dot.edge("OutputPDF", "VSR", label=" Read Tags", fontsize="9")
    dot.edge("VSR", "VSROut")

    # Render
    out_path = Path("static/img/architecture_graph")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dot.render(str(out_path), cleanup=True)
    print(f"✅ Architektur-Graph (Clean Architecture) generiert: {out_path}.svg")


if __name__ == "__main__":
    generate_architecture_graph()
