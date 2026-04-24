#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Quality Measurement Tool (Oracle Validator) - Version 4.0 (Bag-of-Words Inclusion).
Nutzt eine ultra-robuste NLP Metrik (Bag-of-Words Overlap), um PDF-Silbentrennungen,
OCR-Artefakte und Layout-Zersplitterungen fehlerfrei zu messen.
"""

import logging
import re
import sys
import webbrowser
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("quality-measure")

TAG_TOLERANCES: Dict[str, Set[str]] = {
    "P": {"P", "CAPTION", "NOTE", "DIV", "TD", "TH", "LI", "L", "FORM"},
    "H1": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "H2": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "H3": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "H4": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "H5": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "H6": {"H1", "H2", "H3", "H4", "H5", "H6", "P", "DIV"},
    "LI": {"LI", "L", "P", "DIV"},
    "FIGURE": {"FIGURE", "IMG", "P", "DIV"},
    "TABLE": {"TABLE", "P", "DIV"},
    "FORMULA": {"FORMULA", "MATH", "P", "DIV"},
}


@dataclass
class SemanticBlock:
    tag: str
    text: str


class VSRTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tree: Dict[str, Any] = {
            "tag": "ROOT",
            "classes": [],
            "text": [],
            "children": [],
            "parent": None,
            "semantic_label": None,
        }
        self.current = self.tree
        self.is_in_label = False
        self.is_in_text = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()
        node = {
            "tag": tag,
            "classes": classes,
            "text": [],
            "children": [],
            "parent": self.current,
            "semantic_label": None,
        }
        self.current["children"].append(node)
        self.current = node  # type: ignore

        if "tag-label" in classes:
            self.is_in_label = True
        if "text-content" in classes:
            self.is_in_text = True

    def handle_endtag(self, tag: str) -> None:
        self.is_in_label = False
        self.is_in_text = False
        if self.current["parent"] is not None:
            self.current = self.current["parent"]

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if not data:
            return

        if self.is_in_label and self.current["parent"] is not None:
            self.current["parent"]["semantic_label"] = data.upper()
        elif self.is_in_text:
            self.current["text"].append(data)

    def extract_blocks(self) -> List[SemanticBlock]:
        blocks: List[SemanticBlock] = []
        valid_targets = {
            "H1",
            "H2",
            "H3",
            "H4",
            "H5",
            "H6",
            "P",
            "TABLE",
            "LI",
            "L",
            "FIGURE",
            "FORMULA",
            "MATH",
            "CAPTION",
            "NOTE",
            "FORM",
            "DIV",
        }

        def _walk(node: Dict[str, Any]) -> None:
            lbl = node.get("semantic_label")
            if lbl in valid_targets:
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

        if line.startswith("#"):
            _push()
            level = min(max(len(line) - len(line.lstrip("#")), 1), 6)
            blocks.append(SemanticBlock(f"H{level}", line.lstrip("# ")))
            continue

        if line.startswith("!["):
            _push()
            alt_match = re.search(r"!\[(.*?)\]", line)
            alt_text = alt_match.group(1) if alt_match else "Image"
            blocks.append(SemanticBlock("FIGURE", alt_text))
            continue

        if re.match(r"^([-*•]|\d+\.)\s+", line):
            _push()
            cleaned = re.sub(r"^([-*•]|\d+\.)\s+", "", line)
            blocks.append(SemanticBlock("LI", cleaned))
            continue

        if line.startswith("|"):
            if current_tag != "TABLE":
                _push()
                current_tag = "TABLE"
            current_text.append(line.replace("|", " ").strip())
            continue

        if line.startswith("$$"):
            _push()
            blocks.append(SemanticBlock("FORMULA", line.replace("$$", "").strip()))
            continue

        if current_tag not in ("P", "TABLE"):
            _push()
            current_tag = "P"

        current_text.append(line)

    _push()
    return blocks


def _get_lis_length(arr: List[int]) -> int:
    if not arr:
        return 0
    lis = [1] * len(arr)
    for i in range(1, len(arr)):
        for j in range(0, i):
            if arr[i] >= arr[j] and lis[i] < lis[j] + 1:
                lis[i] = lis[j] + 1
    return max(lis)


def get_bow_inclusion_ratio(md_text: str, vsr_text: str) -> float:
    """Berechnet robuste NLP Inclusion via Bag-of-Words Overlap."""
    md_words = re.sub(r"\W+", " ", md_text.lower()).split()
    vsr_words = re.sub(r"\W+", " ", vsr_text.lower()).split()

    if not md_words:
        return 1.0
    if not vsr_words:
        return 0.0

    vsr_counts = Counter(vsr_words)
    matched = 0

    for w in md_words:
        if vsr_counts[w] > 0:
            matched += 1
            vsr_counts[w] -= 1
        else:
            # Partial Match Toleranz für OCR-Hyphens und Silbentrennungen
            found_partial = False
            for vw in list(vsr_counts.keys()):
                if vsr_counts[vw] > 0 and (w in vw or vw in w) and len(w) > 3:
                    matched += 1
                    vsr_counts[vw] -= 1
                    found_partial = True
                    break

            # Sub-Wort Zusammensetzung
            if not found_partial and len(w) > 5:
                w1, w2 = w[: len(w) // 2], w[len(w) // 2 :]
                if vsr_counts[w1] > 0 and vsr_counts[w2] > 0:
                    matched += 1
                    vsr_counts[w1] -= 1
                    vsr_counts[w2] -= 1

    return matched / len(md_words)


def evaluate_document(
    md_blocks: List[SemanticBlock], vsr_blocks: List[SemanticBlock]
) -> Tuple[float, float, float]:
    if not md_blocks:
        return 100.0, 100.0, 100.0
    if not vsr_blocks:
        return 0.0, 0.0, 0.0

    content_scores = []
    tag_matches = 0
    matched_vsr_indices = []

    for md_b in md_blocks:
        best_score = 0.0
        best_idx = -1
        best_tag = ""

        # Sliding Window (bis zu 4 Blöcke kombiniert) für Seitenumbrüche
        for v_idx in range(len(vsr_blocks)):
            for window_size in range(1, 5):
                if v_idx + window_size > len(vsr_blocks):
                    continue

                combined_text = " ".join(
                    [b.text for b in vsr_blocks[v_idx : v_idx + window_size]]
                )

                ratio = get_bow_inclusion_ratio(md_b.text, combined_text)

                if ratio > best_score:
                    best_score = ratio
                    best_idx = v_idx
                    best_tag = vsr_blocks[v_idx].tag

        best_score = min(best_score, 1.0)
        content_scores.append(best_score * 100.0)

        # Toleranz: Ab 50% Wort-Inclusion werten wir es als strukturellen Treffer
        if best_score > 0.5:
            matched_vsr_indices.append(best_idx)
            md_tag = md_b.tag.upper()
            v_tag = best_tag.upper()

            allowed_tags = TAG_TOLERANCES.get(md_tag, {md_tag})
            if v_tag in allowed_tags:
                tag_matches += 1

    content_match = (sum(content_scores) / len(md_blocks)) if md_blocks else 100.0
    tag_match = (tag_matches / len(md_blocks)) * 100.0 if md_blocks else 100.0

    seq_match = 0.0
    if matched_vsr_indices:
        lis_len = _get_lis_length(matched_vsr_indices)
        seq_match = (lis_len / len(matched_vsr_indices)) * 100.0

    return content_match, seq_match, tag_match


def generate_html_report(results: List[Dict[str, Any]], out_path: Path) -> None:
    if not results:
        avg_c, avg_s, avg_t = 0.0, 0.0, 0.0
    else:
        avg_c = sum(r["content"] for r in results) / len(results)
        avg_s = sum(r["sequence"] for r in results) / len(results)
        avg_t = sum(r["tags"] for r in results) / len(results)

    global_score = (avg_c + avg_s + avg_t) / 3.0

    def get_color(val: float) -> str:
        if val >= 90:
            return "#4CAF50"
        if val >= 70:
            return "#FFC107"
        return "#F44336"

    rows = ""
    for r in results:
        c_col = get_color(r["content"])
        s_col = get_color(r["sequence"])
        t_col = get_color(r["tags"])

        rows += f"""
        <div class="card">
            <h3>{r["name"]}</h3>
            <div class="metric">
                <span class="label">Inhalt ({r["content"]:.1f}%)</span>
                <div class="bar-bg">
                    <div class="bar-fill" style="width: {r["content"]}%; background: {c_col};"></div>
                </div>
            </div>
            <div class="metric">
                <span class="label">Reihenfolge ({r["sequence"]:.1f}%)</span>
                <div class="bar-bg">
                    <div class="bar-fill" style="width: {r["sequence"]}%; background: {s_col};"></div>
                </div>
            </div>
            <div class="metric">
                <span class="label">Tags ({r["tags"]:.1f}%)</span>
                <div class="bar-bg">
                    <div class="bar-fill" style="width: {r["tags"]}%; background: {t_col};"></div>
                </div>
            </div>
        </div>
        """

    html_str = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>PDF A11y Converter - Quality Report V4</title>
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
    <h1>📊 PDF A11y - Quality Audit V4 (Bag-of-Words Inclusion)</h1>
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
        f.write(html_str)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    tests_dir = project_root / "tests"

    if not tests_dir.exists():
        logger.error("❌ Verzeichnis 'tests/' nicht gefunden.")
        sys.exit(1)

    logger.info("🔍 Analysiere Testdaten mit Bag-of-Words Inclusion Metric V4...")
    results = []

    for md_file in tests_dir.glob("*.md"):
        vsr_name = f"{md_file.stem}_pdfua.visualscreenreader.html"
        vsr_file = tests_dir / vsr_name

        with open(md_file, "r", encoding="utf-8") as f:
            md_blocks = parse_markdown_blocks(f.read())

        if not vsr_file.exists():
            logger.warning("⚠️ Kein VSR-Output für %s. Score 0.", md_file.name)
            results.append(
                {
                    "name": md_file.name,
                    "content": 0.0,
                    "sequence": 0.0,
                    "tags": 0.0,
                }
            )
            continue

        with open(vsr_file, "r", encoding="utf-8") as f:
            parser = VSRTreeParser()
            parser.feed(f.read())
            vsr_blocks = parser.extract_blocks()

        c_match, s_match, t_match = evaluate_document(md_blocks, vsr_blocks)
        results.append(
            {
                "name": md_file.name,
                "content": c_match,
                "sequence": s_match,
                "tags": t_match,
            }
        )
        logger.info(
            "✔️ %s -> Inhalt: %d%% | Seq: %d%% | Tag: %d%%",
            md_file.name,
            int(c_match),
            int(s_match),
            int(t_match),
        )

    out_html = tests_dir / "quality_report.html"
    generate_html_report(results, out_html)

    logger.info("🎉 Qualitätsmessung V4 abgeschlossen!")
    logger.info("👉 Report ansehen: file://%s", out_html.absolute())

    try:
        webbrowser.open(f"file://{out_html.absolute()}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
