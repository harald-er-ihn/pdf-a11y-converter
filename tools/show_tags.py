#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Zeigt den PDF/UA Tag‑Baum (StructTreeRoot) eines PDFs an.
Wenn kein StructTreeRoot existiert, wird eine entsprechende Meldung ausgegeben.
"""

import argparse
import sys
from pathlib import Path

import pikepdf


def get_tag_text(element, pdf):
    """
    Versucht, den Textinhalt eines Strukturelements zu extrahieren.
    Rückgabe: String oder None.
    """
    # Typische Pfade: /K (Kinder), /P (Parent), /S (Type), /Pg (Seite), /MCID
    # Text steht meist in einem /K Element, das auf eine Content-Referenz verweist.
    # Wir versuchen, über /K -> /MCR -> /MCID den Text aus dem Seiteninhalt zu holen.
    # Vereinfacht: Wenn ein /K ein Dictionary mit /Obj und /MCID ist, können wir den Text
    # aus den Page-Contents extrahieren – das ist komplex. Für die Darstellung reicht
    # oft der Typ und ob ein Kindelement existiert.
    # Daher zeigen wir hier nur, ob Text vorhanden ist, nicht den exakten Text.

    # Einfach: Wenn das Element ein /K hat, das ein String oder eine Liste ist, kann man
    # den Text dort finden. Aber der Text kann über mehrere Knoten verteilt sein.
    # Für den Überblick reicht es, den Typ und ggf. Hinweis "hat Text" zu zeigen.
    # Wir versuchen, den ersten direkten Text zu finden.
    k = element.get("/K")
    if k is None:
        return None
    # K kann ein Array oder ein einzelnes Objekt sein
    if isinstance(k, list):
        for item in k:
            if isinstance(item, str):
                return item.strip()
            if isinstance(item, pikepdf.Object):
                if item.get("/Type") == "/MCR":
                    # Verweis auf MCID – Text holen ist aufwendig, überspringen wir
                    continue
                # Rekursiv? Das würde Komplexität erhöhen.
        return None
    if isinstance(k, str):
        return k.strip()
    return None


def walk_tag_tree(element, pdf, indent=0):
    """
    Rekursive Traversierung des StructTreeRoot.
    Gibt einen String mit eingerückter Baumstruktur zurück.
    """
    lines = []
    indent_str = "  " * indent

    # 1. Fall: element ist ein Array -> jedes Element separat behandeln
    if isinstance(element, (list, tuple, pikepdf.Array)):
        for child in element:
            lines.extend(walk_tag_tree(child, pdf, indent))
        return lines

    # 2. Fall: element ist kein Dictionary (z.B. einfacher Wert) -> überspringen
    if not hasattr(element, "get"):
        return lines

    # 3. Jetzt ist element ein Dictionary
    tag_type = element.get("/S", "Unknown")
    if isinstance(tag_type, pikepdf.Name):
        tag_type = str(tag_type).lstrip("/")

    title = element.get("/Title", "")
    if title:
        title = f" [Title: {title}]"
    alt = element.get("/Alt", "")
    if alt:
        alt = f" [Alt: {alt}]"

    text = get_tag_text(element, pdf)
    text_str = f" — text: {text}" if text else ""

    lines.append(f"{indent_str}▶ {tag_type}{title}{alt}{text_str}")

    # Kinder durchgehen
    kids = element.get("/K")
    if kids is not None:
        if isinstance(kids, (list, tuple, pikepdf.Array)):
            for kid in kids:
                lines.extend(walk_tag_tree(kid, pdf, indent + 1))
        else:
            # Einzelnes Kind
            lines.extend(walk_tag_tree(kids, pdf, indent + 1))

    return lines


def show_tags(pdf_path: Path) -> None:
    """Hauptfunktion: PDF öffnen und StructTreeRoot ausgeben."""
    if not pdf_path.exists():
        print(f"❌ Datei nicht gefunden: {pdf_path}")
        sys.exit(1)

    with pikepdf.open(pdf_path) as pdf:
        root = pdf.Root
        if "/StructTreeRoot" not in root:
            print("⚠️ Kein StructTreeRoot gefunden – Dokument ist NICHT getaggt.")
            return

        st_root = root.StructTreeRoot
        # Der eigentliche Baum startet unter /K
        k = st_root.get("/K")
        if k is None:
            print("⚠️ StructTreeRoot vorhanden, aber keine Kinder (/K).")
            return

        # Sicherstellen, dass k eine Liste ist
        if not isinstance(k, (list, tuple, pikepdf.Array)):
            k = [k]

        print("📑 PDF/UA Tag‑Baum (StructTreeRoot):")
        for idx, top_node in enumerate(k):
            if isinstance(top_node, pikepdf.Object):
                lines = walk_tag_tree(top_node, pdf, indent=0)
                print("\n".join(lines))
            else:
                print(f"Top-Level Element {idx}: {top_node} (kein Tag)")

        print("\n✅ Ende der Struktur.")


def main():
    parser = argparse.ArgumentParser(
        description="Zeigt den PDF/UA Tag‑Baum (StructTreeRoot) eines PDFs an."
    )
    parser.add_argument("input", help="Pfad zur PDF-Datei")
    args = parser.parse_args()

    show_tags(Path(args.input))


if __name__ == "__main__":
    main()
