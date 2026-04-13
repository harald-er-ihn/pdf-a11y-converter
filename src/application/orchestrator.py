# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Der Semantic Orchestrator.
Leitet die PDF-Analyse, ruft isolierte Worker-Prozesse auf und sammelt.
Implementiert das Blackboard-Pattern, Sensor-Fusion und den Audit Trail.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, List, Any

import pikepdf
from PIL import Image

from src.pdf_diagnostics import PDFPreflightScanner
from src.repair import repair_spatial_dom
from src.plugins.workers import PluginManager, WorkerManifest

logger = logging.getLogger("pdf-converter")


def _get_pdf_lang(input_path: Path) -> str:
    try:
        with pikepdf.open(str(input_path)) as pdf:
            if "/Lang" in pdf.Root:
                lang = str(pdf.Root.Lang).strip("() /")
                if lang:
                    return lang
            meta = pdf.open_metadata()
            if "dc:language" in meta:
                lang_meta = meta["dc:language"]
                if isinstance(lang_meta, list):
                    return str(lang_meta[0])
                return str(lang_meta)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("XMP-Sprache nicht lesbar: %s", e)

    try:
        import fitz  # pylint: disable=import-outside-toplevel
        from langdetect import detect  # pylint: disable=import-outside-toplevel

        doc = fitz.open(input_path)
        text = " ".join([p.get_text() for p in doc[:3]])
        doc.close()

        if len(text.strip()) > 20:
            det = detect(text)
            bcp = {"en": "en-US", "de": "de-DE", "es": "es-ES", "fr": "fr-FR"}
            return bcp.get(det, det)
    except ImportError:
        logger.warning("Tipp: 'pip install langdetect' für Auto-Language!")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Spracherkennung fehlgeschlagen: %s", e)

    return "de-DE"


def _extract_original_metadata(input_path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        with pikepdf.open(str(input_path)) as pdf:
            if "/Info" in pdf.trailer:
                meta.update({str(k): str(v) for k, v in pdf.docinfo.items()})
            xmp = pdf.open_metadata()
            if "dc:title" in xmp:
                title_obj = xmp["dc:title"]
                if isinstance(title_obj, list):
                    meta["/Title"] = str(title_obj[0])
                else:
                    meta["/Title"] = str(title_obj)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Konnte Original-Metadaten nicht lesen: %s", e)

    if not meta.get("/Title"):
        meta["/Title"] = input_path.stem.replace("_", " ")

    return meta


def _is_inside(center_x: float, center_y: float, box: List[float]) -> bool:
    return box[0] <= center_x <= box[2] and box[1] <= center_y <= box[3]


class SemanticOrchestrator:
    """Orchestriert die isolierten Experten-Worker."""

    def __init__(self) -> None:
        self.plugin_manager = PluginManager()
        self.temp_dir = Path(tempfile.gettempdir()) / "pdf-a11y-jobs"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _run_worker(self, manifest: WorkerManifest, args: List[str]) -> bool:
        script_path = manifest.worker_dir / manifest.script
        worker_venv = manifest.worker_dir / "venv"

        py_exe = (
            worker_venv / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else worker_venv / "bin" / "python"
        )

        if not py_exe.exists():
            if getattr(sys, "frozen", False):
                logger.error(
                    "❌ FATAL: Worker Venv fehlt im kompilierten Build (%s)!", py_exe
                )
                return False
            py_exe = Path(sys.executable)

        cmd = [str(py_exe), str(script_path)]
        cmd.extend(args)

        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        env["HF_HUB_OFFLINE"] = "1"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        env["DISABLE_TELEMETRY"] = "1"

        # 🚀 DER ULTIMATIVE UTF-8 FIX FÜR WINDOWS 11
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            # errors="replace" verhindert den harten UnicodeDecodeError endgültig
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=manifest.timeout_sec,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.error(
                "❌ Timeout (%ss) in '%s'.", manifest.timeout_sec, manifest.name
            )
            return False
        except subprocess.CalledProcessError as e:
            logger.error("❌ Crash in '%s' (Code %s)", manifest.name, e.returncode)
            if e.stderr:
                logger.error("--- WORKER STDERR ---\n%s", e.stderr.strip())
            return False
        except Exception as e:
            logger.error("❌ Systemfehler bei '%s': %s", manifest.name, e)
            return False

    def _assign_alt_texts_to_dom(
        self,
        spatial_dom: Dict[str, Any],
        images_dict: Dict[str, Tuple[Image.Image, str]],
    ) -> None:
        vision_alts = [alt for _, alt in images_dict.values()]
        v_idx = 0
        for page in spatial_dom.get("pages", []):
            for el in page.get("elements", []):
                if el.get("type") == "figure" and "alt_text" not in el:
                    if v_idx < len(vision_alts):
                        el["alt_text"] = vision_alts[v_idx]
                        v_idx += 1
                    else:
                        el["alt_text"] = "Abbildung"

    def _translate_content(
        self,
        spatial_dom: Dict[str, Any],
        images_dict: Dict[str, Tuple[Image.Image, str]],
        doc_lang: str,
        job_dir: Path,
        audit_trail: Dict[str, Any],
    ) -> None:
        texts_to_translate = {}
        for img_name, (_, alt_text) in images_dict.items():
            texts_to_translate[img_name] = alt_text

        dom_alt_refs = []
        for p_idx, page in enumerate(spatial_dom.get("pages", [])):
            for e_idx, el in enumerate(page.get("elements", [])):
                if el.get("type") == "figure" and "alt_text" in el:
                    ref_key = f"dom_{p_idx}_{e_idx}"
                    texts_to_translate[ref_key] = el["alt_text"]
                    dom_alt_refs.append((p_idx, e_idx, ref_key))

        if not texts_to_translate:
            self._assign_alt_texts_to_dom(spatial_dom, images_dict)
            return

        in_json = job_dir / "trans_in.json"
        out_json = job_dir / "trans_out.json"

        with open(in_json, "w", encoding="utf-8") as f:
            json.dump(texts_to_translate, f, ensure_ascii=False, indent=2)

        manifest = self.plugin_manager.get_worker("translation_worker")
        if manifest:
            logger.info("▶ Starte Spezialist: 'translation_worker'...")
            args = ["--input", str(in_json), "--output", str(out_json)]
            if manifest.requires_lang:
                args.extend(["--lang", doc_lang])

            t_start = time.time()
            success = self._run_worker(manifest, args)
            audit_trail["workers"][manifest.name] = {
                "status": "success" if success else "error",
                "duration_sec": round(time.time() - t_start, 2),
            }

            if out_json.exists():
                with open(out_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    audit_err = worker_data["error"]
                    audit_trail["workers"][manifest.name]["error_details"] = audit_err
                elif success:
                    for img_name in list(images_dict.keys()):
                        if img_name in worker_data:
                            img_obj, _ = images_dict[img_name]
                            images_dict[img_name] = (img_obj, worker_data[img_name])

                    for p_idx, e_idx, ref_key in dom_alt_refs:
                        if ref_key in worker_data:
                            el = spatial_dom["pages"][p_idx]["elements"][e_idx]
                            el["alt_text"] = worker_data[ref_key]

        self._assign_alt_texts_to_dom(spatial_dom, images_dict)

    def _merge_signatures(
        self, spatial_dom: Dict[str, Any], signatures: List[Dict]
    ) -> None:
        for s_page in signatures:
            p_num = s_page.get("page_num")
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") == p_num:
                    dom_page["elements"].extend(s_page.get("elements", []))
                    break

    def _merge_tables(
        self, spatial_dom: Dict[str, Any], table_pages: List[Dict]
    ) -> None:
        for t_page in table_pages:
            p_num = t_page.get("page_num")
            t_elements = t_page.get("elements", [])
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") == p_num:
                    filtered = []
                    for base_el in dom_page.get("elements", []):
                        b_box = base_el.get("bbox", [0, 0, 0, 0])
                        cx = (b_box[0] + b_box[2]) / 2.0
                        cy = (b_box[1] + b_box[3]) / 2.0
                        if not any(_is_inside(cx, cy, t["bbox"]) for t in t_elements):
                            filtered.append(base_el)
                    dom_page["elements"] = filtered + t_elements
                    break

    def _merge_forms(self, spatial_dom: Dict[str, Any], forms: List[Dict]) -> None:
        if forms and spatial_dom.get("pages"):
            for field in forms:
                spatial_dom["pages"][0]["elements"].append(
                    {
                        "type": "p",
                        "text": f"Feld: {field['name']} ({field['alt_text']})",
                        "bbox": [0, 0, 10, 10],
                    }
                )

    def _merge_footnotes(
        self, spatial_dom: Dict[str, Any], footnote_pages: List[Dict]
    ) -> None:
        for f_page in footnote_pages:
            p_num = f_page.get("page_num")
            f_elements = f_page.get("elements", [])
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") == p_num:
                    for base_el in dom_page.get("elements", []):
                        b_box = base_el.get("bbox", [0, 0, 0, 0])
                        cx = (b_box[0] + b_box[2]) / 2.0
                        cy = (b_box[1] + b_box[3]) / 2.0
                        if any(_is_inside(cx, cy, f["bbox"]) for f in f_elements):
                            base_el["type"] = "Note"
                    break

    def _merge_formulas(
        self, spatial_dom: Dict[str, Any], formula_data: Dict[str, Any]
    ) -> None:
        formula_md = formula_data.get("markdown", "")
        if not formula_md:
            return

        regex = r"(\$\$|\\\[|\\\()(.*?)(\$\$|\\\]|\\\))"
        latex_formulas = [
            m.group(2).strip() for m in re.finditer(regex, formula_md, flags=re.DOTALL)
        ]

        if not latex_formulas:
            return

        formula_idx = 0
        for page in spatial_dom.get("pages", []):
            for el in page.get("elements", []):
                text = el.get("text", "")
                is_garbage = len(text) < 25 and (
                    "̂" in text or "ݏ" in text or "\\" in text
                )

                if el.get("type") == "formula" or is_garbage:
                    if formula_idx < len(latex_formulas):
                        el["text"] = f"$$ {latex_formulas[formula_idx]} $$"
                        el["type"] = "p"
                        formula_idx += 1

    def _process_images(
        self, spatial_dom: Dict[str, Any], job_dir: Path, audit_trail: Dict[str, Any]
    ) -> Dict[str, Tuple[Image.Image, str]]:
        images_dict = {}
        image_paths = spatial_dom.get("images", {})
        if not image_paths:
            return images_dict

        input_json = job_dir / "vision_input.json"
        output_json = job_dir / "vision_output.json"

        with open(input_json, "w", encoding="utf-8") as f:
            json.dump(image_paths, f, ensure_ascii=False, indent=2)

        manifest = self.plugin_manager.get_worker("vision_worker")
        worker_data = {}

        if manifest:
            logger.info("▶ Starte Spezialist: 'vision_worker'...")
            args = ["--input", str(input_json), "--output", str(output_json)]

            t_start = time.time()
            success = self._run_worker(manifest, args)
            audit_trail["workers"][manifest.name] = {
                "status": "success" if success else "error",
                "duration_sec": round(time.time() - t_start, 2),
            }

            if output_json.exists():
                with open(output_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)
                if worker_data.get("status") == "error":
                    audit_err = worker_data["error"]
                    audit_trail["workers"][manifest.name]["error_details"] = audit_err

        alt_texts = (
            worker_data
            if (output_json.exists() and "status" not in worker_data)
            else {}
        )

        for img_name, img_path_str in image_paths.items():
            img_path = Path(img_path_str)
            if not img_path.exists():
                continue
            try:
                with Image.open(img_path) as img:
                    img.load()
                    images_dict[img_name] = (
                        img.copy(),
                        alt_texts.get(img_name, "Bild"),
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        return images_dict

    def extract(self, input_path: Path, doc_lang: str) -> Tuple[Dict, Dict, Dict]:
        """Führt die Orchestrierung durch und schreibt den Audit-Trail."""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = self.temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        scanner = PDFPreflightScanner(input_path)
        diagnostics = scanner.analyze()

        audit_trail: Dict[str, Any] = {
            "metadata": {
                "filename": input_path.name,
                "timestamp": datetime.now().isoformat(),
                "language": doc_lang,
                "job_id": job_id,
            },
            "diagnostics": {
                "is_tagged": diagnostics.is_tagged,
                "has_type3_fonts": diagnostics.has_type3_fonts,
                "needs_visual_reconstruction": diagnostics.needs_visual_reconstruction,
                "force_ocr": diagnostics.force_ocr_extraction,
            },
            "workers": {},
        }

        blackboard_results = {}

        # 1. MAP PHASE
        for worker in self.plugin_manager.get_map_workers():
            target_json = job_dir / f"{worker.name}_result.json"
            worker_args = ["--input", str(input_path), "--output", str(target_json)]

            if worker.accepts_force_ocr and diagnostics.force_ocr_extraction:
                worker_args.append("--force-ocr")
            if worker.requires_lang:
                worker_args.extend(["--lang", doc_lang])

            logger.info("▶ Starte Spezialist: '%s'...", worker.name)
            t_start = time.time()
            success = self._run_worker(worker, worker_args)
            duration = round(time.time() - t_start, 2)

            audit_trail["workers"][worker.name] = {
                "status": "success" if success else "error",
                "duration_sec": duration,
            }

            if target_json.exists():
                with open(target_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    err = worker_data["error"]
                    audit_trail["workers"][worker.name]["error_details"] = err
                elif success:
                    blackboard_results[worker.name] = worker_data
                    logger.info("✅ '%s' fertig (%ss).", worker.name, duration)

        # 2. REDUCE PHASE
        if "layout_worker" not in blackboard_results:
            logger.error("❌ Der Layout-Basis-Worker ist fehlgeschlagen!")
            return {}, {}, audit_trail

        spatial_dom = blackboard_results["layout_worker"]
        vis_recon = diagnostics.needs_visual_reconstruction
        spatial_dom["needs_visual_reconstruction"] = vis_recon

        if "signature_worker" in blackboard_results:
            sig = blackboard_results["signature_worker"].get("pages", [])
            self._merge_signatures(spatial_dom, sig)
        if "table_worker" in blackboard_results:
            tbl = blackboard_results["table_worker"].get("pages", [])
            self._merge_tables(spatial_dom, tbl)
        if "formula_worker" in blackboard_results:
            self._merge_formulas(spatial_dom, blackboard_results["formula_worker"])
        if "footnote_worker" in blackboard_results:
            fn = blackboard_results["footnote_worker"].get("pages", [])
            self._merge_footnotes(spatial_dom, fn)
        if "form_worker" in blackboard_results:
            frm = blackboard_results["form_worker"].get("fields", [])
            self._merge_forms(spatial_dom, frm)

        images_dict = self._process_images(spatial_dom, job_dir, audit_trail)
        self._translate_content(
            spatial_dom, images_dict, doc_lang, job_dir, audit_trail
        )

        spatial_dom = repair_spatial_dom(spatial_dom, input_path)

        if logger.getEffectiveLevel() != logging.DEBUG:
            shutil.rmtree(job_dir, ignore_errors=True)

        return spatial_dom, images_dict, audit_trail


def extract_to_spatial(
    input_path: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, str], Dict[str, Any]]:
    """Haupt-Einstiegspunkt für die GUI/CLI."""
    pdf_path = Path(input_path)
    logger.info("✨ Starte Orchestrierung für %s...", pdf_path.name)

    doc_lang = _get_pdf_lang(pdf_path)
    pipeline = SemanticOrchestrator()

    spatial_dom, images_dict, audit_trail = pipeline.extract(pdf_path, doc_lang)
    orig_meta = _extract_original_metadata(pdf_path)

    return spatial_dom, images_dict, doc_lang, orig_meta, audit_trail
