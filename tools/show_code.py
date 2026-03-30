#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Sammelt den gesamten relevanten Projekt-Code für Audits / AI-Prompts und
schreibt ihn direkt in eine Textdatei.
"""

from pathlib import Path

# Diese Ordner ignorieren wir
IGNORE_DIRS = {
    "venv",
    ".git",
    "__pycache__",
    "output",
    "veraPDF-files",
    "pdfs",
    "verapdf_local",
    ".idea",
    "build",
    "dist",
    "TU_Dortmund_Corporate_Design",
    "models_local",
    ".vscode",
    "resources",  # Zu viele Binaries
}

# Diese Dateiendungen und speziellen Namen wollen wir sehen
INCLUDE_EXT = {
    ".py",
    ".html",
    ".css",
    ".js",
    ".json",
    ".toml",
    ".sh",
    ".md",
    ".txt",
}

SPECIAL_FILES = {"Dockerfile", "requirements.txt", ".gitignore"}


def print_project(output_path: Path) -> None:
    """Durchsucht das Projektverzeichnis und schreibt den Code in die Zieldatei."""
    project_root = Path.cwd()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as out_file:
        out_file.write("=== PROJECT STRUCTURE & CONTENT ===\n\n")

        for file_path in project_root.rglob("*"):
            # Ist es eine Datei?
            if not file_path.is_file():
                continue

            # Ist sie in einem ignorierten Ordner?
            if any(part in IGNORE_DIRS for part in file_path.parts):
                continue

            # Ist es eine Ziel-Datei?
            if file_path.suffix in INCLUDE_EXT or file_path.name in SPECIAL_FILES:
                # Das Skript selbst ignorieren
                if file_path.name == "show_code.py":
                    continue

                relative_path = file_path.relative_to(project_root)
                header = f"\n{'=' * 20} START OF FILE: ./{relative_path} {'=' * 20}\n\n"
                footer = f"\n\n{'=' * 20} END OF FILE: ./{relative_path} {'=' * 20}\n\n"

                out_file.write(header)
                try:
                    out_file.write(file_path.read_text(encoding="utf-8"))
                except Exception as e:
                    out_file.write(f"[Fehler beim Lesen der Datei: {e}]")
                out_file.write(footer)

    print(f"✅ Projekt-Code wurde erfolgreich exportiert nach:\n   {output_path}")


if __name__ == "__main__":
    # Pfad explizit wie gewünscht gesetzt
    target_file = Path("/home/harald/Dokumente/PDF-A11y-Converter/mein_projekt.txt")
    print_project(target_file)
