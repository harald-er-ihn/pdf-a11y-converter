#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Entwickler-Werkzeug zur Initialisierung der lokalen Entwicklungsumgebung.
Baut die 'Shared AI Runtime' und die Worker-Venvs, OHNE das Projekt zu kompilieren.
Ersetzt das veraltete Bash-Skript rebuild_worker_venvs.sh.
"""

import sys
from pathlib import Path

# Wir nutzen einfach die Logik aus unserem neuen Build-System wieder!
# Damit sind Dev-Build und Production-Build 100% synchron.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_workers import WorkerPackager


def main() -> None:
    print("🛠️ Initialisiere PDF A11y Converter Entwicklungs-Umgebung...")

    packager = WorkerPackager()

    # Im Dev-Modus ist der Ziel-Ordner direkt das Projekt-Root!
    project_root = Path(__file__).resolve().parent.parent

    # 1. Master Runtime bauen
    print("\n1️⃣ Erstelle Shared AI Runtime...")
    shared_dir = packager.build_shared_ai_runtime(project_root)

    # 2. Worker Venvs bauen
    print("\n2️⃣ Erstelle deduplizierte Worker-Venvs...")
    workers_dir = project_root / "workers"

    if not workers_dir.exists():
        print(f"❌ Worker-Ordner nicht gefunden unter {workers_dir}")
        sys.exit(1)

    for w_dir in workers_dir.iterdir():
        if w_dir.is_dir() and (w_dir / "requirements.txt").exists():
            packager.package_worker(w_dir, shared_dir)

    print("\n🎉 Lokale Entwicklungsumgebung ist einsatzbereit!")
    print("Tipp: Du kannst nun direkt './cli.py mein_dokument.pdf' aufrufen.")


if __name__ == "__main__":
    main()
