# ${/workers/table_worker/color_grid_extractor.py}
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

"""
Universal Color-Grid-Extractor für Infografik-Tabellen.

Erkennt Tabellen-Struktur via Farb-Hintergründe.
Funktioniert mit beliebigen Farbpaletten (nicht nur blau).

Architektur:
  Phase 1: Farb-Clustering → Identifiziere Zell-Färbungen
  Phase 2: Gitter-Erkennung → Finde Zell-Grenzen
  Phase 3: Text-Zuordnung → Ordne Texte den Zellen zu
  Phase 4: Struktur-Normalisierung → HTML-Grid

Pattern: Adapter (OpenCV → PyMuPDF Bridge)
Effizienz: O(n) Bildverarbeitung, nicht DL
"""

import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)

import cv2
import numpy as np

logger = logging.getLogger("color-grid-extractor")


class ColorClusterAnalyzer:
    """
    Analysiert Farbverteilung in Bildern.

    K-Means Clustering zur Identifikation von
    Zell-Färbungen + Hintergrund.
    """

    def __init__(
        self,
        n_clusters: int = 8,
        min_pixel_ratio: float = 0.01,
    ):
        """
        Args:
            n_clusters: Anzahl Farb-Cluster
            min_pixel_ratio: Min. % des Bildes
                             um als "Farbe" zu gelten
        """
        self.n_clusters = n_clusters
        self.min_pixel_ratio = min_pixel_ratio

    def analyze_image_colors(
        self,
        image: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Cluster Farben im Bild (K-Means).

        Args:
            image: RGB numpy array (H, W, 3)

        Returns:
            {
              "clusters": [...],
              "labels": LabelMap,
              "dominant_colors": [...],
              "color_areas": {...}
            }
        """
        if image is None or image.size == 0:
            return {
                "clusters": [],
                "labels": None,
                "dominant_colors": [],
                "color_areas": {},
            }

        # Normalisiere auf uint8
        if image.dtype != np.uint8:
            image = ((image / image.max()) * 255).astype(np.uint8)

        # Reshape für K-Means
        pixels = image.reshape((-1, 3))
        pixels = np.float32(pixels)

        # K-Means Clustering
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            100,
            0.2,
        )
        _, labels, centers = cv2.kmeans(
            pixels,
            self.n_clusters,
            None,
            criteria,
            10,
            cv2.KMEANS_RANDOM_CENTERS,
        )

        centers = np.uint8(centers)
        labels = labels.reshape(image.shape[:2])

        # Berechne Häufigkeiten
        unique, counts = np.unique(
            labels,
            return_counts=True,
        )
        total_pixels = image.shape[0] * image.shape[1]

        # Filter: nur Cluster mit min_pixel_ratio
        color_areas = {}
        dominant_colors = []

        for cluster_id, count in zip(unique, counts):
            ratio = count / total_pixels
            if ratio >= self.min_pixel_ratio:
                color = centers[cluster_id]
                color_areas[int(cluster_id)] = {
                    "color_rgb": tuple(color),
                    "pixel_count": int(count),
                    "ratio": float(ratio),
                }
                dominant_colors.append((int(cluster_id), color))

        logger.debug(
            f"K-Means: {len(dominant_colors)} dominante Farben gefunden"
        )

        return {
            "clusters": centers.tolist(),
            "labels": labels,
            "dominant_colors": dominant_colors,
            "color_areas": color_areas,
        }

    @staticmethod
    def hex_from_rgb(
        rgb: Tuple[int, int, int],
    ) -> str:
        """Konvertiere RGB zu Hex."""
        return "#{:02x}{:02x}{:02x}".format(*rgb)


class GridEdgeDetector:
    """
    Erkennt Gitter-Grenzen via Farbgradienten.

    Sucht nach vertikalen und horizontalen
    Kanten (= Zellgrenzen).
    """

    def __init__(
        self,
        gradient_threshold: float = 50.0,
        min_edge_length: int = 20,
    ):
        """
        Args:
            gradient_threshold: Min. Gradienten-Stärke
            min_edge_length: Min. Kantenlänge
        """
        self.gradient_threshold = gradient_threshold
        self.min_edge_length = min_edge_length

    def detect_grid_lines(
        self,
        image: np.ndarray,
    ) -> Tuple[List[int], List[int]]:
        """
        Erkenne vertikale + horizontale Linien.

        Args:
            image: RGB numpy array

        Returns:
            (vertical_x_coords, horizontal_y_coords)
        """
        if image is None or image.size == 0:
            return [], []

        # Konvertiere zu Graustufen
        if len(image.shape) == 3:
            gray = cv2.cvtColor(
                image,
                cv2.COLOR_RGB2GRAY,
            )
        else:
            gray = image

        # Canny Edge Detection
        edges = cv2.Canny(
            gray,
            50,
            150,
        )

        # Hough Line Transform
        try:
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=50,
                minLineLength=self.min_edge_length,
                maxLineGap=10,
            )
        except Exception:
            logger.warning("HoughLinesP fehlgeschlagen, nutze Fallback")
            return self._fallback_line_detection(gray)

        if lines is None:
            return [], []

        # Klassifiziere Linien
        vertical_lines = []
        horizontal_lines = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # Berechne Winkel
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)

            if dx < dy:
                # Vertikal
                x_center = (x1 + x2) // 2
                vertical_lines.append(x_center)
            else:
                # Horizontal
                y_center = (y1 + y2) // 2
                horizontal_lines.append(y_center)

        # Dedupliziere durch Clustering
        vertical_x = self._cluster_coordinates(vertical_lines)
        horizontal_y = self._cluster_coordinates(horizontal_lines)

        logger.debug(
            f"Grid-Linien: {len(vertical_x)} "
            f"vertikal, {len(horizontal_y)} "
            f"horizontal"
        )

        return sorted(vertical_x), sorted(horizontal_y)

    @staticmethod
    def _cluster_coordinates(
        coords: List[int],
    ) -> List[int]:
        """
        Cluster ähnliche Koordinaten.

        Fallback für einzelne Linie mit
        leichten Schwankungen.
        """
        if not coords:
            return []

        coords = sorted(coords)
        clusters = []
        current_cluster = [coords[0]]

        for coord in coords[1:]:
            if coord - current_cluster[-1] < 15:
                current_cluster.append(coord)
            else:
                clusters.append(sum(current_cluster) // len(current_cluster))
                current_cluster = [coord]

        clusters.append(sum(current_cluster) // len(current_cluster))

        return clusters

    @staticmethod
    def _fallback_line_detection(
        gray: np.ndarray,
    ) -> Tuple[List[int], List[int]]:
        """
        Fallback: Histogramm-basierte
        Zellenerkennung.
        """
        # X-Projektion (vertikale Linien)
        x_hist = np.sum(
            gray < 200,
            axis=0,
        )
        x_threshold = np.mean(x_hist) * 0.5
        vertical_x = np.where(x_hist > x_threshold)[0].tolist()

        # Y-Projektion (horizontale Linien)
        y_hist = np.sum(
            gray < 200,
            axis=1,
        )
        y_threshold = np.mean(y_hist) * 0.5
        horizontal_y = np.where(y_hist > y_threshold)[0].tolist()

        return vertical_x, horizontal_y


class GridCellExtractor:
    """
    Extrahiert Tabellenzellen-Bounding-Boxes
    aus Gitter-Koordinaten.
    """

    @staticmethod
    def extract_cells(
        vertical_lines: List[int],
        horizontal_lines: List[int],
        image_width: int,
        image_height: int,
        min_cell_size: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Generiere Zell-Bounding-Boxes.

        Args:
            vertical_lines: X-Koordinaten
            horizontal_lines: Y-Koordinaten
            image_width: Bild-Breite
            image_height: Bild-Höhe
            min_cell_size: Min. Zellengröße

        Returns:
            Liste von {
              "bbox": (x0, y0, x1, y1),
              "row": int,
              "col": int
            }
        """
        cells = []

        # Ergänze Grenzen
        x_coords = [0] + sorted(set(vertical_lines)) + [image_width]
        y_coords = [0] + sorted(set(horizontal_lines)) + [image_height]

        for row_idx in range(len(y_coords) - 1):
            for col_idx in range(len(x_coords) - 1):
                y0 = y_coords[row_idx]
                y1 = y_coords[row_idx + 1]
                x0 = x_coords[col_idx]
                x1 = x_coords[col_idx + 1]

                width = x1 - x0
                height = y1 - y0

                # Überspringe zu kleine Zellen
                if width < min_cell_size or height < min_cell_size:
                    continue

                cells.append(
                    {
                        "bbox": (x0, y0, x1, y1),
                        "row": row_idx,
                        "col": col_idx,
                        "width": width,
                        "height": height,
                    }
                )

        logger.debug(
            f"Extrahiert {len(cells)} Zellen: "
            f"{len(y_coords) - 1} Reihen × "
            f"{len(x_coords) - 1} Spalten"
        )

        return cells


class TextCellMapper:
    """
    Ordnet PyMuPDF Text-Spans den
    Tabellenzellen zu.
    """

    @staticmethod
    def map_text_to_cells(
        cells: List[Dict[str, Any]],
        text_words: List[tuple],
        scale_factor: float = 72.0 / 150.0,
    ) -> Dict[Tuple[int, int], List[str]]:
        """
        Zuordnung: Text → Zelle.

        Args:
            cells: Zell-Bounding-Boxes
            text_words: PyMuPDF get_text("words")
            scale_factor: Pixel zu PDF-Punkte

        Returns:
            {(row, col): [text_fragments]}
        """
        cell_text: Dict[
            Tuple[int, int],
            List[str],
        ] = {}

        for cell in cells:
            bbox = cell["bbox"]
            row = cell["row"]
            col = cell["col"]

            cell_key = (row, col)
            cell_text[cell_key] = []

            # Skaliere Zell-BBox auf PDF-Punkte
            x0_pdf = bbox[0] * scale_factor
            y0_pdf = bbox[1] * scale_factor
            x1_pdf = bbox[2] * scale_factor
            y1_pdf = bbox[3] * scale_factor

            # Zuordne Texte
            for word in text_words:
                # PyMuPDF: (x0, y0, x1, y1, text, ...)
                wx0, wy0, wx1, wy1, text = word[:5]

                # Prüfe: Text-Center in Zelle?
                text_cx = (wx0 + wx1) / 2
                text_cy = (wy0 + wy1) / 2

                if x0_pdf <= text_cx <= x1_pdf and y0_pdf <= text_cy <= y1_pdf:
                    cell_text[cell_key].append(text)

        return cell_text


class ColorGridExtractor:
    """
    Hauptklasse: Orchestriert Universal
    Color-Grid-Extraktion.

    Pipeline:
      1. Farb-Clustering
      2. Gitter-Erkennung
      3. Zell-Extraktion
      4. Text-Zuordnung
      5. HTML-Grid-Generierung
    """

    def __init__(
        self,
        n_color_clusters: int = 8,
        gradient_threshold: float = 50.0,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Args:
            n_color_clusters: K-Means Cluster
            gradient_threshold: Edge-Detection
            logger_instance: Optional Logger
        """
        self.color_analyzer = ColorClusterAnalyzer(n_clusters=n_color_clusters)
        self.edge_detector = GridEdgeDetector(
            gradient_threshold=gradient_threshold
        )
        self.logger = logger_instance or logging.getLogger(__name__)

    def extract_color_grid_table(
        self,
        image: np.ndarray,
        text_words: List[tuple],
        page_width: float,
        page_height: float,
        scale_factor: float = 72.0 / 150.0,
    ) -> Dict[str, Any]:
        """
        Haupteinstieg: Extrahiere
        Farb-Gitter-Tabelle.

        Args:
            image: RGB numpy array (PIL konvertiert)
            text_words: PyMuPDF get_text("words")
            page_width: PDF-Seiten-Breite
            page_height: PDF-Seiten-Höhe
            scale_factor: Pixel zu PDF

        Returns:
            {
              "type": "color_grid_table",
              "html": HTML-Tabelle,
              "bbox": [x0, y0, x1, y1],
              "analysis": {...}
            }
        """
        self.logger.debug("🎨 Starte Color-Grid-Extraktion")

        if image is None or image.size == 0:
            self.logger.warning("Bild ist leer, return {}")
            return {}

        # Phase 1: Farb-Clustering
        color_analysis = self.color_analyzer.analyze_image_colors(image)

        if not color_analysis["dominant_colors"]:
            self.logger.debug("Keine dominanten Farben gefunden")
            return {}

        # Phase 2: Gitter-Erkennung
        vertical_x, horizontal_y = self.edge_detector.detect_grid_lines(image)

        if not vertical_x or not horizontal_y:
            self.logger.debug("Keine Gitter-Linien gefunden")
            return {}

        # Phase 3: Zell-Extraktion
        cells = GridCellExtractor.extract_cells(
            vertical_x,
            horizontal_y,
            image.shape[1],
            image.shape[0],
        )

        if not cells:
            self.logger.debug("Keine Zellen extrahiert")
            return {}

        # Phase 4: Text-Zuordnung
        cell_text = TextCellMapper.map_text_to_cells(
            cells,
            text_words,
            scale_factor,
        )

        # Phase 5: HTML-Grid generieren
        html_table = self._generate_html_table(
            cells,
            cell_text,
        )

        self.logger.info(
            f"✅ Color-Grid extrahiert: "
            f"{len(set(c['row'] for c in cells))} "
            f"Reihen, "
            f"{len(set(c['col'] for c in cells))} "
            f"Spalten"
        )

        return {
            "type": "color_grid_table",
            "html": html_table,
            "bbox": [
                0,
                0,
                page_width,
                page_height,
            ],
            "analysis": {
                "colors": (color_analysis["color_areas"]),
                "grid_rows": (len(set(c["row"] for c in cells))),
                "grid_cols": (len(set(c["col"] for c in cells))),
            },
        }

    @staticmethod
    def _generate_html_table(
        cells: List[Dict[str, Any]],
        cell_text: Dict[
            Tuple[int, int],
            List[str],
        ],
    ) -> str:
        """Generiere HTML-Tabelle."""
        if not cells:
            return ""

        # Berechne Gitter-Dimensionen
        max_row = max(c["row"] for c in cells)
        max_col = max(c["col"] for c in cells)

        # 2D-Grid für HTML
        grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]

        for (row, col), texts in cell_text.items():
            if row <= max_row and col <= max_col:
                grid[row][col] = " ".join(texts)

        # Generiere HTML
        html_str = "<table style='width:100%;'>\n"
        for r_idx, row_data in enumerate(grid):
            html_str += "  <tr>\n"
            for c_idx, cell_content in enumerate(row_data):
                tag = "th" if r_idx == 0 else "td"
                content = cell_content or ("&#8203;")
                html_str += f"    <{tag}>{content}</{tag}>\n"
            html_str += "  </tr>\n"
        html_str += "</table>"

        return html_str
