# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
from src.repair import enforce_pdfua_heading_hierarchy, enforce_pdfua_list_structure


def test_heading_hierarchy_repair():
    """Prüft, ob eine fehlende H1 und Sprünge repariert werden."""
    bad_md = "### Überschrift 3 ohne H1\nText"
    fixed_md = enforce_pdfua_heading_hierarchy(bad_md)

    # H3 muss zu H1 gezwungen werden (weil es die erste ist)
    assert fixed_md.startswith("# Überschrift 3")


def test_list_structure_repair():
    """Prüft, ob leere Fragmente (die FAIL 7.2-20 triggern) gelöscht werden."""
    bad_md = "1.\nText\n• \nWeiterer Text"
    fixed_md = enforce_pdfua_list_structure(bad_md)

    assert "1." not in fixed_md  # Das nackte Fragment muss gelöscht sein
    assert "•" not in fixed_md  # Das nackte Bullet muss gelöscht sein
    assert "Text" in fixed_md  # Echter Text muss bleiben
