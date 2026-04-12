#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Zips the project source code, excluding unnecessary directories and files,
so it can be extracted on Windows 11 and used for building.
"""

import zipfile
from pathlib import Path
from typing import Set

# Directories to ignore
IGNORE_DIRS: Set[str] = {
    "venv",
    ".git",
    "__pycache__",
    "output",
    "veraPDF-files",
    "logs",
    "pdfs",
    "verapdf_local",
    ".idea",
    "build",
    "dist",
    "TU_Dortmund_Corporate_Design",
    "models_local",
    ".vscode",
    "build_temp",
    "veraPDF-validation-profiles-rel-1.28",  # 🚀 FIX: Toter Code mit zu tiefen Pfaden ausschließen!
}

# File extensions to include (Source Code)
INCLUDE_EXT: Set[str] = {
    ".py",
    ".ps1",
    ".html",
    ".css",
    ".js",
    ".json",
    ".toml",
    ".sh",
    ".md",
    ".txt",
    ".iss",
}

SPECIAL_FILES: Set[str] = {"Dockerfile", "requirements.txt", ".gitignore"}


def zip_project(zip_path: Path) -> None:
    """Creates a zip archive containing all relevant project files."""
    project_root = Path.cwd()
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in project_root.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip files in ignored directories
            if any(part in IGNORE_DIRS for part in file_path.parts):
                continue

            # Alles aus resources/ und static/ IMMER mitnehmen (Logos, VeraPDF, Modelle)
            is_resource = "resources" in file_path.parts or "static" in file_path.parts

            if (
                file_path.suffix in INCLUDE_EXT
                or file_path.name in SPECIAL_FILES
                or is_resource
            ):
                if file_path.name in {"zip_code.py", "show_code.py"}:
                    continue

                relative_path = file_path.relative_to(project_root)
                try:
                    zip_file.write(file_path, arcname=relative_path)
                except Exception as e:
                    print(f"⚠️  Could not add {relative_path}: {e}")
                else:
                    print(f"Added: {relative_path}")

    print(f"✅ Project code successfully zipped to:\n   {zip_path}")


if __name__ == "__main__":
    output_zip = Path.cwd() / "project_code.zip"
    zip_project(output_zip)
