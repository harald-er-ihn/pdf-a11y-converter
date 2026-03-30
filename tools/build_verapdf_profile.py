#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Baut ein aggregiertes veraPDF Master-Profil aus vielen einzelnen XML-Regeln.
Ideal, um die 93 einzelnen WCAG 2.2 Regeln in ein einziges Profil zu mergen.
"""

import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    # 1. Pfade definieren
    source_dir = Path(
        "resources/verapdf/profiles/veraPDF-validation-profiles-rel-1.28/PDF_UA/WCAG/2.2"
    )
    output_file = Path("resources/verapdf/profiles/WCAG_2_2.xml")

    if not source_dir.exists():
        print(f"❌ Quell-Ordner nicht gefunden: {source_dir}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 2. XML Namespaces registrieren, damit die Ausgabe sauber bleibt (ohne ns0:)
    ns = {"v": "http://www.verapdf.org/ValidationProfile"}
    ET.register_namespace("", "http://www.verapdf.org/ValidationProfile")

    # 3. Master-Struktur aufbauen
    root = ET.Element(
        "{http://www.verapdf.org/ValidationProfile}profile", flavour="WCAG_2_2"
    )

    details = ET.SubElement(root, "{http://www.verapdf.org/ValidationProfile}details")
    ET.SubElement(
        details, "{http://www.verapdf.org/ValidationProfile}name"
    ).text = "WCAG 2.2 Master Profile"
    ET.SubElement(
        details, "{http://www.verapdf.org/ValidationProfile}description"
    ).text = "Aggregated WCAG 2.2 rules"

    ET.SubElement(root, "{http://www.verapdf.org/ValidationProfile}hash")

    rules_elem = ET.SubElement(root, "{http://www.verapdf.org/ValidationProfile}rules")
    vars_elem = ET.SubElement(
        root, "{http://www.verapdf.org/ValidationProfile}variables"
    )

    rule_count = 0
    seen_vars = set()

    # 4. Alle Dateien parsen und extrahieren
    for xml_file in source_dir.rglob("*.xml"):
        try:
            tree = ET.parse(xml_file)

            # Alle <rule> Elemente anfügen
            for rule in tree.findall(".//v:rule", ns):
                rules_elem.append(rule)
                rule_count += 1

            # Alle <variable> Elemente anfügen (Deduplizierung ist zwingend!)
            for var in tree.findall(".//v:variable", ns):
                vname = var.get("name")
                if vname not in seen_vars:
                    vars_elem.append(var)
                    seen_vars.add(vname)

        except Exception as e:
            print(f"⚠️ Fehler beim Parsen von {xml_file.name}: {e}")

    # 5. Speichern
    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(
        f"✅ Master-Profil mit {rule_count} Regeln und {len(seen_vars)} Variablen erstellt!"
    )
    print(f"📂 Gespeichert unter: {output_file}")


if __name__ == "__main__":
    main()
