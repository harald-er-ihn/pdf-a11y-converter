# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Formel-Erkennung (Nougat).
Implementiert das Adapter Pattern, um eine API-Inkompatibilität zwischen
Nougat 0.1.17 und modernem pypdfium2 (>=4.0) elegant zur Laufzeit zu überbrücken.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Generator, Iterable, Optional

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("formula-worker")


def apply_nougat_pypdfium_adapter() -> None:
    """
    Adapter Pattern (Compatibility Layer):
    Nougat ruft intern `pdf.render(converter, page_indices, ...)` auf.
    Diese Methode existiert in modernen pypdfium2 Versionen nicht mehr auf
    Dokumenten-Ebene. Wir fangen das ab und mappen es auf die neue Page-Level API.
    """
    try:
        import pypdfium2 as pdfium

        # 1. PosixPath-Bug fixen (alte vs. neue pypdfium2 API)
        orig_init = pdfium.PdfDocument.__init__

        def patched_init(self: Any, input_data: Any, *args: Any, **kwargs: Any) -> None:
            if hasattr(input_data, "resolve"):
                input_data = str(input_data)
            orig_init(self, input_data, *args, **kwargs)

        pdfium.PdfDocument.__init__ = patched_init

        # 2. Den fehlenden render() Aufruf als Adapter implementieren
        if not hasattr(pdfium.PdfDocument, "render"):

            def legacy_render_adapter(
                self: Any,
                converter: Callable,
                page_indices: Optional[Iterable[int]] = None,
                scale: float = 1.0,
                **kwargs: Any,
            ) -> Generator[Any, None, None]:
                """
                Übersetzt Nougats Dokument-Render-Aufruf in eine Iteration
                über die einzelnen Seiten (Moderne v4+ API).
                """
                indices = page_indices if page_indices is not None else range(len(self))
                for i in indices:
                    page = self[i]
                    # Rendert die Seite (liefert ein PdfBitmap Objekt)
                    bitmap = page.render(scale=scale, **kwargs)
                    # Nougat übergibt oft 'pdfium.PdfBitmap.to_pil' als converter
                    yield converter(bitmap)

            # Die Adapter-Methode an die Klasse binden
            pdfium.PdfDocument.render = legacy_render_adapter
            logger.debug("✅ pypdfium2 Adapter für Nougat erfolgreich injiziert.")

    except Exception as e:
        logger.warning(f"⚠️ Konnte pypdfium2 Adapter nicht anwenden: {e}")


def _get_nougat_main() -> Optional[Callable]:
    """Löst den Einstiegspunkt für Nougat dynamisch auf (Fail-Fast)."""
    try:
        import predict  # type: ignore

        return predict.main
    except ImportError:
        try:
            from nougat.cli import main as nougat_main  # type: ignore

            return nougat_main
        except ImportError:
            return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Formula Worker (Nougat)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)
    temp_out_dir = output_json.parent / "nougat_temp"

    if not input_pdf.exists():
        logger.error(f"❌ Eingabedatei nicht gefunden: {input_pdf}")
        sys.exit(1)

    temp_out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Lade Nougat-OCR für komplexe Mathematik...")

    # ADAPTER ANWENDEN
    apply_nougat_pypdfium_adapter()

    nougat_main = _get_nougat_main()
    if not nougat_main:
        logger.error("❌ Nougat API konnte nicht geladen werden.")
        sys.exit(1)

    try:
        sys.argv = ["nougat", str(input_pdf), "--out", str(temp_out_dir), "--markdown"]
        nougat_main()

        mmd_file = temp_out_dir / f"{input_pdf.stem}.mmd"
        if not mmd_file.exists():
            raise FileNotFoundError("Nougat hat keine .mmd Datei generiert.")

        with open(mmd_file, "r", encoding="utf-8") as f:
            math_markdown = f.read()

        output_data = {"markdown": math_markdown, "images": {}}

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info("✅ Formel-Extraktion erfolgreich abgeschlossen.")

    except Exception as e:
        logger.error(f"❌ Fataler Fehler im Formula-Worker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
