# src/table_repair_facade.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Fassade zur Reparatur und Typprüfung von HTML-Tabellen.
Behebt Barrierefreiheits-Verstöße (PDF/UA) in Tabellenstrukturen:
- Zelltypenerkennung (Header/Data/Footer)
- Column-Spanning-Behandlung (Leere benachbarte Zellen)
- Semantische <thead>, <tbody>, <tfoot> Zuordnung
"""

import re
import xml.etree.ElementTree as ET
from enum import Enum


class CellType(Enum):
    """Klassifikation für Tabellenzellen-Typen."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"


class CellTypeInferencer:
    """Inferiert den Datentyp einer Tabellenzelle deterministisch."""

    @staticmethod
    def infer_cell_type(text: str) -> CellType:
        """Klassifiziert Text als Zahl, Datum oder Freitext."""
        text = (text or "").strip()

        # Datumsformate: DD.MM.YYYY oder YYYY-MM-DD
        if re.match(r"^\d{2,4}[-./]\d{2}[-./]\d{2,4}$", text):
            return CellType.DATE

        # Zahlen: optionales Minus, Ziffern, Tausendertrenner, Dezimalstellen
        if re.match(r"^-?\d{1,3}([\.,]\d{3})*([\.,]\d+)?$", text) or re.match(
            r"^-?\d+([\.,]\d+)?$", text
        ):
            return CellType.NUMBER

        return CellType.TEXT


class TableRepairFacade:
    """Repariert HTML-Tabellen gemäß PDF/UA i18n Vorgaben."""

    @staticmethod
    def repair_html_table(html_str: str) -> str:
        """
        Füllt leere Tabellenzellen mit barrierefreiem Inhalt.
        Die leere obere linke Zelle wird mit "Spalte 1" aufgefüllt.
        Führt Zelltypenerkennung und Column-Spanning-Behandlung durch.
        """
        if not html_str:
            return ""

        # HTML bereinigen für strengen XML-Parser
        html_clean = html_str.replace("<br>", "<br/>").replace("&", "&amp;")
        html_clean = html_clean.replace("&#8203;", "")

        try:
            root = ET.fromstring(html_clean)
        except ET.ParseError:
            try:
                root = ET.fromstring(f"<div>{html_clean}</div>")[0]
            except Exception:
                # Fallback: Falls XML extrem kaputt, Originalstring zurückgeben
                return html_str

        rows = list(root.findall(".//tr"))
        if not rows:
            return html_str

        table_new = ET.Element(
            "table", {"style": "width:100%; border-collapse: collapse;"}
        )
        thead = ET.SubElement(table_new, "thead")
        tbody = ET.SubElement(table_new, "tbody")
        tfoot = None

        for r_idx, row in enumerate(rows):
            cells = list(row)
            if not cells:
                continue

            is_header_row = r_idx == 0
            is_footer_row = False

            # Zelltypenerkennung: Footer erkennen (z.B. Summenzeile)
            if r_idx == len(rows) - 1 and len(rows) > 2:
                first_text = "".join(cells[0].itertext()).strip().lower()
                if first_text in [
                    "total",
                    "summe",
                    "gesamt",
                    "ergebnis",
                    "sum",
                    "gesamtsumme",
                ]:
                    is_footer_row = True
                    if tfoot is None:
                        tfoot = ET.SubElement(table_new, "tfoot")

            new_row = ET.Element("tr")
            skip = 0

            for c_idx, cell in enumerate(cells):
                if skip > 0:
                    skip -= 1
                    continue

                text = "".join(cell.itertext()).strip()

                # Column-Spanning: Prüfe benachbarte Zellen auf Leere
                colspan = 1
                while c_idx + colspan < len(cells):
                    next_cell = cells[c_idx + colspan]
                    next_text = "".join(next_cell.itertext()).strip()
                    if not next_text:
                        colspan += 1
                    else:
                        break

                tag = "th" if is_header_row else "td"

                # Zelltypenerkennung: Row-Header erkennen
                if (
                    not is_header_row
                    and not is_footer_row
                    and c_idx == 0
                    and text
                ):
                    if len(cells) > 1:
                        n_sample = "".join(cells[1].itertext()).strip()
                        n_type = CellTypeInferencer.infer_cell_type(n_sample)
                        if n_type in [CellType.NUMBER, CellType.DATE]:
                            tag = "th"

                # Footer-Row-Header
                if is_footer_row and c_idx == 0:
                    tag = "th"

                new_cell = ET.Element(tag)
                if colspan > 1:
                    new_cell.set("colspan", str(colspan))
                    skip = colspan - 1

                # i18n PDF/UA Fix: Semantisches Auffüllen leerer Zellen
                if not text:
                    if is_header_row and c_idx == 0:
                        new_cell.text = "Spalte 1"
                    else:
                        new_cell.text = "&#8203;"  # Zero-width space
                else:
                    new_cell.text = text

                new_row.append(new_cell)

            if is_header_row:
                thead.append(new_row)
            elif is_footer_row:
                tfoot.append(new_row)
            else:
                tbody.append(new_row)

        # Konvertiere zurück zu HTML-String
        repaired_html = ET.tostring(
            table_new, encoding="unicode", method="xml"
        )
        repaired_html = repaired_html.replace("&amp;amp;", "&amp;")
        repaired_html = repaired_html.replace("&amp;#8203;", "&#8203;")

        # Fix für empty self-closing tags (wichtig für Weasyprint)
        repaired_html = re.sub(
            r"<(td|th)([^>]*)/>", r"<\1\2>&#8203;</\1>", repaired_html
        )

        return repaired_html
