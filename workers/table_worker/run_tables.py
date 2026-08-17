# ${/workers/table_worker/run_tables.py}
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

"""
Deep-Learning + Color-Grid Table Worker (TATR + CGE).

Nutzt Microsoft Table-Transformer zur strukturellen
Analyse von Tabellen. Mappt PyMuPDF-Textspans in
visuell erkannte Rasterzellen.

Löst randlose Tabellen und Spielpläne durch:
  1. Color-Grid-Extraction (Infografiken)
  2. Deep-Learning-TATR (traditionelle Tabellen)
  3. Fallback: PyMuPDF Text-Grid

Architektur:
  Phase 1: Preflight-Screening (schnelle Heuristik)
    → Identifiziere Seiten mit Tabellen-Kandidaten
  Phase 2: Color-Grid-Extraktion (Farbgitter)
    → Erkenne Infografik-Tabellen
  Phase 3: Deep-Learning TATR (nur Kandidaten)
    → Tiefe Analyse + Rasterzuordnung
  Phase 4: Table Repair Facade (via Orchestrator)
    → Strukturelle Reparatur

Effizienz: O(n) für Screening + CGE, nur O(m) für
DL wo m=Tabellen
"""

import argparse
import html
import json
import sys
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Set,
    Tuple,
)

import cv2
import fitz  # PyMuPDF
import numpy as np
import torch
from PIL import Image
from transformers import (
    DetrImageProcessor,
    TableTransformerForObjectDetection,
)

# SYSTEM-PATH FIX
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import (
    cleanup_memory,
    configure_torch_runtime,
    setup_worker_logging,
    write_error_contract,
)
from color_grid_extractor import (
    ColorGridExtractor,
)

PROJECT_ROOT = WORKER_ROOT.parent
MODEL_DET = PROJECT_ROOT / "resources" / "models" / "tatr-det"
MODEL_REC = PROJECT_ROOT / "resources" / "models" / "tatr-rec"

logger = setup_worker_logging("table-tatr-cge")
configure_torch_runtime()


class TableScreener:
    """
    Phase 1: Schnelle Heuristik-basierte
    Vorselektierung.

    Identifiziert Seiten, die wahrscheinlich
    Tabellen enthalten, OHNE Deep-Learning.

    Heuristiken:
      1. Grid-Pattern: Regelmäßige vertikale Lücken
      2. Whitespace-Gap: Breite horiz. Lücken
      3. Tab-Char-Count: Häufigkeit von Tabs
      4. Color-Density: Farbige Zellen
    """

    MIN_GRID_CONFIDENCE = 0.6
    TAB_DENSITY_THRESHOLD = 0.15
    MIN_COLOR_RATIO = 0.05  # 5% farbig

    @staticmethod
    def screen_page(
        page: fitz.Page,
        page_num: int,
    ) -> Tuple[bool, float]:
        """
        Schnell-Screening einer Seite.

        Args:
            page: PyMuPDF Seite
            page_num: Seitennummer

        Returns:
            (is_candidate, confidence_score)
        """
        scores = []

        # Heuristik 1: Whitespace-Gap-Analyse
        gap_score = TableScreener._analyze_whitespace_gaps(page)
        scores.append(gap_score)

        # Heuristik 2: Tab-Charakter-Dichte
        tab_score = TableScreener._analyze_tab_character_density(page)
        scores.append(tab_score)

        # Heuristik 3: Gitterstruktur
        grid_score = TableScreener._analyze_grid_pattern(page)
        scores.append(grid_score)

        # Heuristik 4: Farb-Dichte
        color_score = TableScreener._analyze_color_density(page)
        scores.append(color_score)

        # Aggregiere Scores
        avg_score = sum(scores) / len(scores)

        is_candidate = avg_score >= TableScreener.MIN_GRID_CONFIDENCE

        return is_candidate, avg_score

    @staticmethod
    def _analyze_whitespace_gaps(
        page: fitz.Page,
    ) -> float:
        """Erkenne vertikale Whitespace-Gaps."""
        words = page.get_text("words")

        if not words:
            return 0.0

        x_positions = sorted(
            set([word[0] for word in words] + [word[2] for word in words])
        )

        if len(x_positions) < 3:
            return 0.0

        gaps = [
            x_positions[i + 1] - x_positions[i]
            for i in range(len(x_positions) - 1)
        ]

        large_gaps = [g for g in gaps if g > 15]

        if not large_gaps:
            return 0.0

        large_gap_ratio = len(large_gaps) / len(gaps)
        return min(large_gap_ratio, 1.0)

    @staticmethod
    def _analyze_tab_character_density(
        page: fitz.Page,
    ) -> float:
        """Prüfe Dichte von Tab-Zeichen."""
        text = page.get_text()

        if not text:
            return 0.0

        tab_count = text.count("\t")
        newline_count = text.count("\n")

        if newline_count == 0:
            return 0.0

        tab_ratio = tab_count / newline_count
        return min(
            tab_ratio / (TableScreener.TAB_DENSITY_THRESHOLD * 2),
            1.0,
        )

    @staticmethod
    def _analyze_grid_pattern(
        page: fitz.Page,
    ) -> float:
        """Erkenne Grid-Muster."""
        words = page.get_text("words")

        if len(words) < 4:
            return 0.0

        y_positions = sorted(set([word[1] for word in words]))

        if len(y_positions) < 2:
            return 0.0

        heights = [
            y_positions[i + 1] - y_positions[i]
            for i in range(len(y_positions) - 1)
        ]

        if not heights:
            return 0.0

        avg_height = sum(heights) / len(heights)
        variance = sum((h - avg_height) ** 2 for h in heights) / len(heights)

        std_dev = variance**0.5
        regularity_score = max(
            1.0 - (std_dev / 10.0),
            0.0,
        )

        return regularity_score

    @staticmethod
    def _analyze_color_density(
        page: fitz.Page,
    ) -> float:
        """Erkenne Farbige Zellen."""
        try:
            pix = page.get_pixmap(dpi=150)
            img = np.array(
                Image.frombytes(
                    "RGB",
                    [pix.width, pix.height],
                    pix.samples,
                )
            )

            # Berechne Sättigung im HSV
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            saturation = hsv[:, :, 1]

            # Pixels mit hoher Sättigung (> 50%)
            high_saturation = np.sum(saturation > 127)
            total_pixels = saturation.shape[0] * saturation.shape[1]

            color_ratio = high_saturation / total_pixels

            return min(
                color_ratio / TableScreener.MIN_COLOR_RATIO,
                1.0,
            )

        except Exception as e:
            logger.debug(f"Color-Analyse fehlgeschlagen: {str(e)}")
            return 0.0


class ColorGridTableAnalyzer:
    """
    Phase 2: Color-Grid-Extraktion.

    Nutzt ColorGridExtractor für
    Infografik-Tabellen.
    """

    def __init__(self) -> None:
        self.extractor = ColorGridExtractor(
            n_color_clusters=12,
            logger_instance=logger,
        )

    def analyze_page(
        self,
        page: fitz.Page,
        page_num: int,
    ) -> List[Dict[str, Any]]:
        """
        Extrahiere Color-Grid-Tabellen
        von einer Seite.

        Args:
            page: PyMuPDF Seite
            page_num: Seitennummer

        Returns:
            Liste von Tabellen-Objekten
        """
        try:
            # Rendere zu Bild
            pix = page.get_pixmap(dpi=150)
            img = np.array(
                Image.frombytes(
                    "RGB",
                    [pix.width, pix.height],
                    pix.samples,
                )
            )

            # Extrahiere Text
            text_words = page.get_text("words")

            # Hauptextraktion
            result = self.extractor.extract_color_grid_table(
                img,
                text_words,
                page.rect.width,
                page.rect.height,
            )

            if result and "html" in result:
                logger.info(f"Seite {page_num}: Color-Grid-Tabelle gefunden")
                return [result]

        except Exception as e:
            logger.debug(f"Color-Grid Fehler auf Seite {page_num}: {str(e)}")

        return []


class DeepTableAnalyzer:
    """
    Phase 3: Deep-Learning Tabellen-Analyse
    (TATR).

    WIRD NUR auf nicht-Color-Grid-Seiten
    aufgerufen.
    """

    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = DetrImageProcessor.from_pretrained(str(MODEL_REC))
        self.model = (
            TableTransformerForObjectDetection.from_pretrained(str(MODEL_REC))
            .to(self.device)
            .eval()
        )

    def _get_page_image(
        self,
        page: fitz.Page,
    ) -> Image.Image:
        """Rendere Seite zu Bild (150 DPI)."""
        pix = page.get_pixmap(dpi=150)
        return Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples,
        )

    def _process_page(
        self,
        page: fitz.Page,
        page_num: int,
    ) -> List[Dict[str, Any]]:
        """Verarbeite Seite mit TATR."""
        img = self._get_page_image(page)
        inputs = self.processor(
            images=img,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        target_sizes = torch.tensor([img.size[::-1]])
        results = self.processor.post_process_object_detection(
            outputs,
            threshold=0.7,
            target_sizes=target_sizes,
        )[0]

        # Extrahiere Reihen und Spalten
        rows, cols = [], []
        for score, label, box in zip(
            results["scores"],
            results["labels"],
            results["boxes"],
        ):
            box_list = box.tolist()
            label_name = self.model.config.id2label[label.item()]
            if label_name == "table row":
                rows.append(box_list)
            elif label_name == "table column":
                cols.append(box_list)

        if not rows or not cols:
            return []

        rows.sort(key=lambda b: b[1])
        cols.sort(key=lambda b: b[0])

        words = page.get_text("words")
        scale = 72.0 / 150.0

        grid = [["" for _ in range(len(cols))] for _ in range(len(rows))]

        for w in words:
            wx = (w[0] + w[2]) / 2.0 / scale
            wy = (w[1] + w[3]) / 2.0 / scale

            r_idx, c_idx = -1, -1
            for i, r_box in enumerate(rows):
                if r_box[1] <= wy <= r_box[3]:
                    r_idx = i
                    break
            for j, c_box in enumerate(cols):
                if c_box[0] <= wx <= c_box[2]:
                    c_idx = j
                    break

            if r_idx != -1 and c_idx != -1:
                grid[r_idx][c_idx] += w[4] + " "

        return self._build_html_table(
            grid,
            page,
        )

    def _build_html_table(
        self,
        grid: List[List[str]],
        page: fitz.Page,
    ) -> List[Dict[str, Any]]:
        """Generiere HTML-Tabelle aus Grid."""
        if not grid or not grid[0]:
            return []

        html_str = "<table style='width:100%;'>\n"
        for r_idx, row in enumerate(grid):
            html_str += "  <tr>\n"
            for c_idx, cell in enumerate(row):
                tag = "th" if r_idx == 0 else "td"
                content = html.escape(cell.strip()) or "&#8203;"
                html_str += f"    <{tag}>{content}</{tag}>\n"
            html_str += "  </tr>\n"
        html_str += "</table>"

        return [
            {
                "type": "table",
                "html": html_str,
                "bbox": [
                    0,
                    0,
                    page.rect.width,
                    page.rect.height,
                ],
            }
        ]

    def analyze_candidates(
        self,
        pdf_path: Path,
        candidate_pages: Set[int],
    ) -> Dict[str, Any]:
        """
        Analysiere nur Kandidat-Seiten mit
        Deep-Learning.
        """
        spatial_data = {"pages": []}

        with fitz.open(pdf_path) as doc:
            for i, page in enumerate(doc):
                page_num = i + 1

                if page_num not in candidate_pages:
                    continue

                elements = self._process_page(
                    page,
                    page_num,
                )

                if elements:
                    spatial_data["pages"].append(
                        {
                            "page_num": page_num,
                            "width": (page.rect.width),
                            "height": (page.rect.height),
                            "elements": elements,
                        }
                    )

        return spatial_data


def main() -> None:
    """
    Haupteinstiegspunkt mit 4 Phasen.

    Phase 1: Screening
    Phase 2: Color-Grid-Extraktion
    Phase 3: Deep-Learning (Fallback)
    Phase 4: Repair (via Orchestrator)
    """
    parser = argparse.ArgumentParser(
        description="DL Table Worker + Color-Grid"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)

    args, _ = parser.parse_known_args()

    out_file = Path(args.output)

    if not MODEL_REC.exists():
        msg = "Deep-Learning Tabellen-Modell nicht gefunden."
        write_error_contract(
            out_file,
            "ModelNotFound",
            msg,
        )
        sys.exit(1)

    try:
        pdf_path = Path(args.input)

        logger.info("📋 Phase 1: Schnell-Screening")

        # PHASE 1: Screening
        candidate_pages: Set[int] = set()
        has_color_grid_pages: Set[int] = set()
        screener = TableScreener()

        with fitz.open(pdf_path) as doc:
            for i, page in enumerate(doc):
                page_num = i + 1

                is_candidate, confidence = screener.screen_page(
                    page,
                    page_num,
                )

                if is_candidate:
                    candidate_pages.add(page_num)
                    logger.debug(
                        f"Seite {page_num}: Kandidat (conf: {confidence:.2f})"
                    )

        if not candidate_pages:
            logger.info("✅ Keine Tabellen-Kandidaten, leeres Output")
            spatial_data = {"pages": []}
            with open(
                out_file,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    spatial_data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            sys.exit(0)

        logger.info(
            f"📊 {len(candidate_pages)} "
            f"Kandidat-Seiten: "
            f"{sorted(candidate_pages)}"
        )

        # PHASE 2: Color-Grid-Extraktion
        logger.info("🎨 Phase 2: Color-Grid-Extraktion")

        spatial_data = {"pages": []}
        cg_analyzer = ColorGridTableAnalyzer()

        with fitz.open(pdf_path) as doc:
            for i, page in enumerate(doc):
                page_num = i + 1

                if page_num not in candidate_pages:
                    continue

                elements = cg_analyzer.analyze_page(
                    page,
                    page_num,
                )

                if elements:
                    has_color_grid_pages.add(page_num)
                    spatial_data["pages"].append(
                        {
                            "page_num": page_num,
                            "width": (page.rect.width),
                            "height": (page.rect.height),
                            "elements": elements,
                        }
                    )

        logger.info(
            f"🎨 {len(has_color_grid_pages)} Color-Grid-Tabellen gefunden"
        )

        # PHASE 3: Deep-Learning (Fallback)
        remaining_candidates = candidate_pages - has_color_grid_pages

        if remaining_candidates:
            logger.info("🧠 Phase 3: Deep-Learning TATR")

            analyzer = DeepTableAnalyzer()
            dl_data = analyzer.analyze_candidates(
                pdf_path,
                remaining_candidates,
            )

            spatial_data["pages"].extend(dl_data["pages"])

            logger.info(f"🧠 {len(dl_data['pages'])} TATR-Tabellen gefunden")

        with open(
            out_file,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                spatial_data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        logger.info("✅ Tabellen-Extraktion abgeschlossen")

    except Exception as e:
        logger.error(
            "❌ Fehler im Table-Worker: %s",
            e,
        )
        write_error_contract(
            out_file,
            type(e).__name__,
            str(e),
        )
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
