#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Quality Measurement Tool (Oracle Validator).
Vergleicht die Original-Markdowns mit den generierten VSR-HTML-Dateien.
Berechnet Metriken für:
- Content Match (% des Textes erhalten)
- Sequence Match (% korrekte Lesereihenfolge)
- Tag Match (% semantische Korrektheit)
"""

import logging
import re
import sys
import webbrowser
from dataclasses import dataclass
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("quality-measure")


@dataclass
class SemanticBlock:
    """Repräsentiert einen logischen Textblock mit seinem PDF/UA-Tag."""

    tag: str
    text: str


class VSRTreeParser(HTMLParser):
    """
    Baut einen Baum aus der VSR-HTML auf und aggregiert
    Texte anhand der vergebenen Semantik-Label.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tree: Dict[str, Any] = {
            "tag": "ROOT",
            "classes": "",
            "text": [],
            "children": [],
            "parent": None,
            "semantic_label": None,
        }
        self.current = self.tree

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        node = {
            "tag": tag,
            "classes": attrs_dict.get("class", ""),
            "text": [],
            "children": [],
            "parent": self.current,
            "semantic_label": None,
        }
        self.current["children"].append(node)
        self.current = node  # type: ignore

    def handle_endtag(self, tag: str) -> None:
        if self.current["parent"] is not None:
            self.current = self.current["parent"]

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if not data:
            return

        if "tag-label" in self.current["classes"]:
            if self.current["parent"] is not None:
                self.current["parent"]["semantic_label"] = data.upper()
        elif "text-content" in self.current["classes"]:
            self.current["text"].append(data)

    def extract_blocks(self) -> List[SemanticBlock]:
        """Traversiert den Baum rekursiv und aggregiert markierte Blöcke."""
        blocks: List[SemanticBlock] = []
        target_tags = {
            "H1",
            "H2",
            "H3",
            "H4",
            "H5",
            "H6",
            "P",
            "TABLE",
            "LI",
            "FIGURE",
            "FORMULA",
            "MATH",
            "CAPTION",
            "NOTE",
            "FORM",
        }

        def _walk(node: Dict[str, Any]) -> None:
            lbl = node.get("semantic_label")
            if lbl in target_tags:
                # Sammle allen Text in diesem Knoten und seinen Kindern
                all_text = []

                def _collect_text(n: Dict[str, Any]) -> None:
                    all_text.extend(n.get("text", []))
                    for c in n.get("children", []):
                        _collect_text(c)

                _collect_text(node)
                combined_text = " ".join(all_text).strip()
                if combined_text:
                    blocks.append(SemanticBlock(lbl, combined_text))
            else:
                for c in node.get("children", []):
                    _walk(c)

        _walk(self.tree)
        return blocks


def parse_markdown_blocks(md_text: str) -> List[SemanticBlock]:
    """Wandelt rohes Markdown heuristisch in SemanticBlocks um."""
    blocks: List[SemanticBlock] = []
    current_tag = "P"
    current_text: List[str] = []

    def _push() -> None:
        if current_text:
            cleaned = " ".join(current_text).strip()
            if cleaned:
                blocks.append(SemanticBlock(current_tag, cleaned))
            current_text.clear()

    for line in md_text.splitlines():
        line = line.strip()
        if not line:
            _push()
            current_tag = "P"
            continue

        # Headers
        if line.startswith("#"):
            _push()
            level = len(line) - len(line.lstrip("#"))
            level = min(max(level, 1), 6)
            blocks.append(SemanticBlock(f"H{level}", line.lstrip("# ")))
            continue

        # Figures
        if line.startswith("!["):
            _push()
            alt_match = re.search(r"!\[(.*?)\]", line)
            alt_text = alt_match.group(1) if alt_match else "Image"
            blocks.append(SemanticBlock("FIGURE", alt_text))
            continue

        # Lists
        if re.match(r"^([-*•]|\d+\.)\s+", line):
            _push()
            cleaned = re.sub(r"^([-*•]|\d+\.)\s+", "", line)
            blocks.append(SemanticBlock("LI", cleaned))
            continue

        # Tables
        if line.startswith("|"):
            if current_tag != "TABLE":
                _push()
                current_tag = "TABLE"
            current_text.append(line.replace("|", " ").strip())
            continue

        # Formulas
        if line.startswith("$$"):
            _push()
            blocks.append(SemanticBlock("FORMULA", line.replace("$$", "").strip()))
            continue

        # Default P
        if current_tag not in ("P", "TABLE"):
            _push()
            current_tag = "P"

        current_text.append(line)

    _push()
    return blocks


def _get_lis_length(arr: List[int]) -> int:
    """Berechnet die Longest Increasing Subsequence (Längste aufsteigende Teilfolge)."""
    if not arr:
        return 0
    lis = [1] * len(arr)
    for i in range(1, len(arr)):
        for j in range(0, i):
            if arr[i] > arr[j] and lis[i] < lis[j] + 1:
                lis[i] = lis[j] + 1
    return max(lis)


def evaluate_document(
    md_blocks: List[SemanticBlock], vsr_blocks: List[SemanticBlock]
) -> Tuple[float, float, float]:
    """Berechnet die 3 Kernmetriken: Content Match, Sequence Match, Tag Match."""
    if not md_blocks:
        return 100.0, 100.0, 100.0
    if not vsr_blocks:
        return 0.0, 0.0, 0.0

    content_scores = []
    tag_matches = 0
    matched_vsr_indices = []

    for md_b in md_blocks:
        best_ratio = 0.0
        best_idx = -1
        best_tag = ""

        # Suche den besten Match in den VSR Blöcken
        for v_idx, vsr_b in enumerate(vsr_blocks):
            ratio = SequenceMatcher(
                None, md_b.text.lower(), vsr_b.text.lower()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = v_idx
                best_tag = vsr_b.tag

        content_scores.append(best_ratio)

        # Wenn der Text gefunden wurde (Toleranz > 30% Ähnlichkeit)
        if best_ratio > 0.3:
            matched_vsr_indices.append(best_idx)
            md_tag = md_b.tag.upper()
            v_tag = best_tag.upper()
            
            # Tag Toleranzen
            if md_tag == v_tag or (
                md_tag == "FORMULA" and v_tag in ("FORMULA", "MATH")
            ):
                tag_matches += 1

    content_match = (sum(content_scores) / len(md_blocks)) * 100.0
    tag_match = (tag_matches / len(md_blocks)) * 100.0

    seq_match = 0.0
    if matched_vsr_indices:
        lis_len = _get_lis_length(matched_vsr_indices)
        seq_match = (lis_len / len(matched_vsr_indices)) * 100.0

    return content_match, seq_match, tag_match


def generate_html_report(results: List[Dict[str, Any]], out_path: Path) -> None:
    """Generiert ein hübsches HTML Dashboard."""
    
    if not results:
        avg_c, avg_s, avg_t = 0.0, 0.0, 0.0
    else:
        avg_c = sum(r["content"] for r in results) / len(results)
        avg_s = sum(r["sequence"] for r in results) / len(results)
        avg_t = sum(r["tags"] for r in results) / len(results)
        
    global_score = (avg_c + avg_s + avg_t) / 3.0

    def get_color(val: float) -> str:
        if val >= 90:
            return "#4CAF50"  # Grün
        if val >= 70:
            return "#FFC107"  # Gelb
        return "#F44336"  # Rot

    rows = ""
    for r in results:
        c_col = get_color(r["content"])
        s_col = get_color(r["sequence"])
        t_col = get_color(r["tags"])
        
        rows += f"""
        <div class="card">
            <h3>{r['name']}</h3>
            
            <div class="metric">
                <span class="label">Inhalt ({r['content']:.1f}%)</span>
                <div class="bar-bg"><div class="bar-fill" style="width: {r['content']}%; background: {c_col};"></div></div>
            </div>
            
            <div class="metric">
                <span class="label">Reihenfolge ({r['sequence']:.1f}%)</span>
                <div class="bar-bg"><div class="bar-fill" style="width: {r['sequence']}%; background: {s_col};"></div></div>
            </div>
            
            <div class="metric">
                <span class="label">Tags ({r['tags']:.1f}%)</span>
                <div class="bar-bg"><div class="bar-fill" style="width: {r['tags']}%; background: {t_col};"></div></div>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>PDF A11y Converter - Quality Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; color: #333; margin: 0; padding: 40px; }}
        h1 {{ text-align: center; color: #2c3e50; }}
        .dashboard {{ display: flex; justify-content: center; gap: 30px; margin-bottom: 40px; }}
        .score-box {{ background: #fff; padding: 20px 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; }}
        .score-val {{ font-size: 36px; font-weight: bold; color: {get_color(global_score)}; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; max-width: 1200px; margin: 0 auto; }}
        .card {{ background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .card h3 {{ margin-top: 0; font-size: 16px; border-bottom: 1px solid #eee; padding-bottom: 10px; word-break: break-all; }}
        .metric {{ margin-bottom: 12px; }}
        .label {{ display: block; font-size: 13px; font-weight: 600; margin-bottom: 5px; color: #555; }}
        .bar-bg {{ background: #e0e0e0; height: 10px; border-radius: 5px; overflow: hidden; }}
        .bar-fill {{ height: 100%; border-radius: 5px; transition: width 0.5s ease-in-out; }}
    </style>
</head>
<body>
    <h1>📊 PDF A11y Converter - Qualitäts-Audit</h1>
    
    <div class="dashboard">
        <div class="score-box">
            <div>Gesamt-Score</div>
            <div class="score-val">{global_score:.1f}%</div>
        </div>
        <div class="score-box">
            <div>Ø Inhalt</div>
            <div class="score-val" style="color: {get_color(avg_c)}">{avg_c:.1f}%</div>
        </div>
        <div class="score-box">
            <div>Ø Reihenfolge</div>
            <div class="score-val" style="color: {get_color(avg_s)}">{avg_s:.1f}%</div>
        </div>
        <div class="score-box">
            <div>Ø Tags</div>
            <div class="score-val" style="color: {get_color(avg_t)}">{avg_t:.1f}%</div>
        </div>
    </div>
    
    <div class="grid">
        {rows}
    </div>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    tests_dir = project_root / "tests"
    
    if not tests_dir.exists():
        logger.error("❌ Verzeichnis 'tests/' nicht gefunden.")
        sys.exit(1)

    logger.info("🔍 Analysiere Testdaten in '%s'...", tests_dir)
    results = []

    for md_file in tests_dir.glob("*.md"):
        vsr_name = f"{md_file.stem}_pdfua.visualscreenreader.html"
        vsr_file = tests_dir / vsr_name
        
        with open(md_file, "r", encoding="utf-8") as f:
            md_text = f.read()
            md_blocks = parse_markdown_blocks(md_text)

        if not vsr_file.exists():
            logger.warning("⚠️ Kein VSR-Output für %s gefunden. Score 0.", md_file.name)
            results.append({"name": md_file.name, "content": 0.0, "sequence": 0.0, "tags": 0.0})
            continue

        with open(vsr_file, "r", encoding="utf-8") as f:
            vsr_html = f.read()
            
        parser = VSRTreeParser()
        parser.feed(vsr_html)
        vsr_blocks = parser.extract_blocks()

        c_match, s_match, t_match = evaluate_document(md_blocks, vsr_blocks)
        results.append({
            "name": md_file.name,
            "content": c_match,
            "sequence": s_match,
            "tags": t_match
        })
        logger.info("✔️ %s -> Inhalt: %d%% | Seq: %d%% | Tag: %d%%", 
                    md_file.name, int(c_match), int(s_match), int(t_match))

    out_html = tests_dir / "quality_report.html"
    generate_html_report(results, out_html)

    logger.info("🎉 Qualitätsmessung abgeschlossen!")
    logger.info("👉 Report ansehen: file://%s", out_html.absolute())
    
    # Optional: Report direkt im Browser öffnen
    try:
        webbrowser.open(f"file://{out_html.absolute()}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
