# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Formel-Erkennung (Nougat).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Generator, Iterable, Optional

# 🚀 SYSTEM-PATH FIX für common import
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("formula-worker")
configure_torch_runtime()


def apply_nougat_pypdfium_adapter() -> None:
    """Adapter Pattern: Überbrückt API-Inkompatibilität von Nougat und pypdfium2 >=4.0."""
    try:
        import pypdfium2 as pdfium  # pylint: disable=import-outside-toplevel

        orig_init = pdfium.PdfDocument.__init__

        def patched_init(self: Any, input_data: Any, *args: Any, **kwargs: Any) -> None:
            if hasattr(input_data, "resolve"):
                input_data = str(input_data)
            orig_init(self, input_data, *args, **kwargs)

        pdfium.PdfDocument.__init__ = patched_init

        if not hasattr(pdfium.PdfDocument, "render"):

            def legacy_render_adapter(
                self: Any,
                converter: Callable,
                page_indices: Optional[Iterable[int]] = None,
                scale: float = 1.0,
                **kwargs: Any,
            ) -> Generator[Any, None, None]:
                indices = page_indices if page_indices is not None else range(len(self))
                for i in indices:
                    page = self[i]
                    bitmap = page.render(scale=scale, **kwargs)
                    yield converter(bitmap)

            pdfium.PdfDocument.render = legacy_render_adapter
            logger.debug("✅ pypdfium2 Adapter für Nougat erfolgreich injiziert.")

    except Exception as e:
        logger.warning("⚠️ Konnte pypdfium2 Adapter nicht anwenden: %s", e)


def _get_nougat_main() -> Optional[Callable]:
    """Löst den Einstiegspunkt für Nougat dynamisch auf (Fail-Fast)."""
    try:
        import predict  # type: ignore # pylint: disable=import-outside-toplevel

        return predict.main
    except ImportError:
        try:
            from nougat.cli import main as nougat_main  # type: ignore # pylint: disable=import-outside-toplevel

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
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    temp_out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Lade Nougat-OCR für komplexe Mathematik...")

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
        logger.error("❌ Fataler Fehler im Formula-Worker: %s", e)
        sys.exit(1)

    finally:
        # 🚀 ENTERPRISE MEMORY CLEANUP
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
