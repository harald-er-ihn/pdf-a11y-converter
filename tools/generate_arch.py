#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Generiert den Architektur-Graphen lokal und offline.
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
    )
    dot.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname="Arial",
        fontsize="11",
        color="#333333",
    )

    dot.node("User", "Benutzer\n(GUI/CLI)", fillcolor="#2b5e8f", fontcolor="white")
    dot.node(
        "Engine",
        "engine.py\n[Orchestrator & Sensor Fusion]",
        fillcolor="#83B818",
        fontcolor="white",
        shape="hexagon",
    )

    # Worker Pool
    dot.node("W_Layout", "Layout-Experte\n[docling/marker]", fillcolor="#e2a929")
    dot.node("W_Table", "Tabellen-Experte\n[pdfplumber]", fillcolor="#e2a929")
    dot.node("W_Vision", "Bild-Experte\n[blip]", fillcolor="#e2a929")
    dot.node("W_Form", "Formular-Experte\n[pikepdf]", fillcolor="#e2a929")
    dot.node("W_Sig", "Signatur-Experte\n[yolov8s local]", fillcolor="#e2a929")
    dot.node("W_Trans", "Übersetzer\n[nllb-200]", fillcolor="#e2a929")

    # Backend
    dot.node("Repair", "repair.py\n[Sanitization & PyMuPDF]", fillcolor="#d4e1f9")
    dot.node(
        "Generator",
        "generator.py\n[WeasyPrint Overlay]",
        fillcolor="#a0522d",
        fontcolor="white",
    )
    dot.node(
        "Validator",
        "validation.py\n[VeraPDF offline]",
        fillcolor="#6a0dad",
        fontcolor="white",
    )
    dot.node(
        "Output", "Barrierefreies\nPDF/UA-1", fillcolor="#2b5e8f", fontcolor="white"
    )

    # NEU: Visual Screenreader
    dot.node(
        "VSR",
        "vsr_generator.py\n[Visual Screenreader]",
        fillcolor="#4A6B74",
        fontcolor="white",
        shape="hexagon",
    )
    dot.node(
        "VSR_Out", "HTML-Vorschau\n(PAC26 Style)", fillcolor="#2b5e8f", fontcolor="white"
    )

    # Flow
    dot.edge("User", "Engine")

    # Map
    dot.edge("Engine", "W_Layout")
    dot.edge("Engine", "W_Table")
    dot.edge("Engine", "W_Vision")
    dot.edge("Engine", "W_Form")
    dot.edge("Engine", "W_Sig")
    dot.edge("W_Vision", "W_Trans", label=" Alt-Texte", fontsize="9")
    dot.edge("W_Sig", "W_Trans", label=" Labels", fontsize="9")
    dot.edge("W_Trans", "Engine")

    # Generation Flow
    dot.edge("W_Layout", "Engine")
    dot.edge("W_Table", "Engine")
    dot.edge("W_Form", "Engine")

    dot.edge("Engine", "Repair")
    dot.edge("Repair", "Generator")
    dot.edge("Generator", "Validator")
    dot.edge("Validator", "Output")

    # VSR Flow
    dot.edge("User", "VSR", label=" Trigger", fontsize="9", style="dashed")
    dot.edge("Output", "VSR", label=" StructTreeRoot", fontsize="9")
    dot.edge("VSR", "VSR_Out")

    out_path = Path("static/img/architecture_graph")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dot.render(str(out_path), cleanup=True)
    print(f"✅ Architektur-Graph generiert: {out_path}.svg")


if __name__ == "__main__":
    generate_architecture_graph()
