#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

from pathlib import Path
import argparse

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
    "build_temp",
    ".vscode",
    "resources",
}

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


def print_project(
    output_path: Path, start_path: Path, python_only: bool = False
) -> None:
    """Durchsucht ein Verzeichnis und schreibt den Code in die Zieldatei."""
    project_root = start_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as out_file:
        out_file.write(f"=== PROJECT STRUCTURE & CONTENT from {project_root} ===\n\n")

        for file_path in project_root.rglob("*"):
            if not file_path.is_file():
                continue

            if any(part in IGNORE_DIRS for part in file_path.parts):
                continue

            if python_only:
                if file_path.suffix != ".py":
                    continue
            else:
                if not (
                    file_path.suffix in INCLUDE_EXT or file_path.name in SPECIAL_FILES
                ):
                    continue

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

    print(f"✅ Code wurde exportiert nach:\n   {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Exportiert Projektcode in eine Textdatei"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Verzeichnis, das exportiert werden soll (z.B. tests)",
    )

    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Exportiert nur Python-Dateien (.py)",
    )

    args = parser.parse_args()

    start_dir = Path(args.path)
    target_file = Path("/home/harald/Dokumente/PDF-A11y-Converter/mein_projekt.txt")

    print_project(target_file, start_dir, python_only=args.python_only)
