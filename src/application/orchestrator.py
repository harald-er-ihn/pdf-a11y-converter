# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Der Semantic Orchestrator.
Leitet die PDF-Analyse, ruft isolierte Worker-Prozesse auf und sammelt.
Implementiert das Blackboard-Pattern und die Sensor-Fusion (Merge-Phase).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Tuple, List, Any

import pikepdf
from PIL import Image

from src.pdf_diagnostics import PDFPreflightScanner
from src.repair import repair_spatial_dom
from src.plugins.workers import PluginManager, WorkerManifest

logger = logging.getLogger("pdf-converter")


def _get_pdf_lang(input_path: Path) -> str:
    """Ermittelt die Sprache (via Metadaten oder KI-Erkennung)."""
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
    """Extrahiert PDF-Metadaten inkl. Dateinamen-Fallback für den Titel."""
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
    """Prüft, ob ein Mittelpunkt (x,y) innerhalb einer Bounding Box liegt."""
    return box[0] <= center_x <= box[2] and box[1] <= center_y <= box[3]


class SemanticOrchestrator:
    """Orchestriert die isolierten Experten-Worker."""

    def __init__(self) -> None:
        self.plugin_manager = PluginManager()
        self.temp_dir = Path(tempfile.gettempdir()) / "pdf-a11y-jobs"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _run_worker(self, manifest: WorkerManifest, args: List[str]) -> bool:
        """Führt einen isolierten Worker aus. Setzt Telemetrie-Blocker (Option A)."""
        script_path = manifest.worker_dir / manifest.script
        worker_venv = manifest.worker_dir / "venv"

        py_exe = (
            worker_venv / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else worker_venv / "bin" / "python"
        )

        if not py_exe.exists():
            if getattr(sys, "frozen", False):
                logger.error("❌ FATAL: Worker Venv fehlt im kompilierten Build (%s)!", py_exe)
                return False
            py_exe = Path(sys.executable)

        cmd = [str(py_exe), str(script_path)]
        cmd.extend(args)

        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        # 🚀 OPTION A: Telemetrie-freie Runtime-Isolation
        env["HF_HUB_OFFLINE"] = "1"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        env["DISABLE_TELEMETRY"] = "1"
        env["DO_NOT_TRACK"] = "1"
        env["ANONYMIZED_TELEMETRY"] = "False"
        env["HUGGINGFACE_CO_RESOLVE_ENDPOINT"] = "0"

        try:
            # 🚀 FIX: encoding="utf-8" ist überlebenswichtig auf Windows wegen Emojis!
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=manifest.timeout_sec,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.error(
                "❌ Worker '%s' hat das Timeout (%ss) überschritten und wurde gekillt!",
                manifest.name,
                manifest.timeout_sec,
            )
            return False
        except subprocess.CalledProcessError as e:
            # 🚀 FIX: Echten Crash-Log für den Admin sichtbar machen!
            logger.error("❌ Subprozess Crash in '%s' (Code %s)", manifest.name, e.returncode)
            if e.stderr:
                logger.error("--- WORKER ERROR LOG ---\n%s", e.stderr.strip())
            return False
        except Exception as e:
            logger.error("❌ Systemfehler beim Starten von '%s': %s", manifest.name, e)
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

            success = self._run_worker(manifest, args)

            if out_json.exists():
                with open(out_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    err = worker_data.get("error", {})
                    logger.warning(
                        "⚠️ Übersetzer meldet Problem [%s]: %s",
                        err.get("type", "Unknown"),
                        err.get("message", ""),
                    )
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
        self, spatial_dom: Dict[str, Any], signatures: List[Dict[str, Any]]
    ) -> None:
        total_sigs = 0
        for s_page in signatures:
            p_num = s_page.get("page_num")
            s_elements = s_page.get("elements", [])
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") == p_num:
                    dom_page["elements"].extend(s_elements)
                    total_sigs += len(s_elements)
                    break
        if total_sigs > 0:
            logger.info("📝 %s Unterschrift(en) ins Dokument integriert.", total_sigs)

    def _merge_tables(
        self, spatial_dom: Dict[str, Any], table_pages: List[Dict[str, Any]]
    ) -> None:
        total_tables = 0
        for t_page in table_pages:
            p_num = t_page.get("page_num")
            t_elements = t_page.get("elements", [])
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") != p_num:
                    continue

                filtered_elements = []
                for base_el in dom_page.get("elements", []):
                    b_box = base_el.get("bbox", [0, 0, 0, 0])
                    cx = (b_box[0] + b_box[2]) / 2.0
                    cy = (b_box[1] + b_box[3]) / 2.0
                    is_in_tab = any(_is_inside(cx, cy, t["bbox"]) for t in t_elements)
                    if not is_in_tab:
                        filtered_elements.append(base_el)

                dom_page["elements"] = filtered_elements
                dom_page["elements"].extend(t_elements)
                total_tables += len(t_elements)
                break

        if total_tables > 0:
            logger.info("📝 %s Tabellen integriert.", total_tables)

    def _merge_forms(
        self, spatial_dom: Dict[str, Any], forms: List[Dict[str, Any]]
    ) -> None:
        if not forms:
            return
        logger.info("📝 Verwebe %s Formularfelder...", len(forms))
        if spatial_dom.get("pages"):
            first_page = spatial_dom["pages"][0]
            for field in forms:
                first_page["elements"].append(
                    {
                        "type": "p",
                        "text": f"Feld: {field['name']} ({field['alt_text']})",
                        "bbox": [0, 0, 10, 10],
                    }
                )

    def _merge_footnotes(
        self, spatial_dom: Dict[str, Any], footnote_pages: List[Dict[str, Any]]
    ) -> None:
        total_notes = 0
        for f_page in footnote_pages:
            p_num = f_page.get("page_num")
            f_elements = f_page.get("elements", [])
            for dom_page in spatial_dom.get("pages", []):
                if dom_page.get("page_num") != p_num:
                    continue

                for base_el in dom_page.get("elements", []):
                    b_box = base_el.get("bbox", [0, 0, 0, 0])
                    cx = (b_box[0] + b_box[2]) / 2.0
                    cy = (b_box[1] + b_box[3]) / 2.0
                    is_fn = any(_is_inside(cx, cy, f["bbox"]) for f in f_elements)
                    if is_fn:
                        base_el["type"] = "Note"
                        total_notes += 1
                break

        if total_notes > 0:
            logger.info("📝 %s Textblöcke als Fußnote markiert.", total_notes)

    def _merge_formulas(
        self, spatial_dom: Dict[str, Any], formula_data: Dict[str, Any]
    ) -> None:
        formula_md = formula_data.get("markdown", "")
        if not formula_md:
            return

        latex_formulas = []
        matches = re.finditer(
            r"(\$\$|\\\[|\\\()(.*?)(\$\$|\\\]|\\\))", formula_md, flags=re.DOTALL
        )
        for m in matches:
            latex_formulas.append(m.group(2).strip())

        if not latex_formulas:
            return

        formula_idx = 0
        replaced_count = 0
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
                        replaced_count += 1

        if replaced_count > 0:
            logger.info("📝 %s Formeln eingewoben.", replaced_count)

    def _process_images(
        self, spatial_dom: Dict[str, Any], job_dir: Path
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
        if manifest:
            logger.info("▶ Starte Spezialist: 'vision_worker'...")
            args = ["--input", str(input_json), "--output", str(output_json)]
            success = self._run_worker(manifest, args)

            if output_json.exists():
                with open(output_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    err = worker_data.get("error", {})
                    logger.warning(
                        "⚠️ Vision-KI meldet Problem [%s]: %s",
                        err.get("type", "Unknown"),
                        err.get("message", ""),
                    )
            elif not success:
                logger.warning("⚠️ 'vision_worker' unerwartet abgestürzt.")
        else:
            logger.warning("⚠️ Vision-Worker nicht gefunden.")

        alt_texts = {}
        if output_json.exists() and "status" not in worker_data:
            alt_texts = worker_data

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
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("Fehler beim Laden von Bild %s: %s", img_name, e)

        return images_dict

    def extract(
        self, input_path: Path, doc_lang: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = self.temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        blackboard_results = {}
        scanner = PDFPreflightScanner(input_path)
        diagnostics = scanner.analyze()

        # 1. MAP PHASE
        for worker in self.plugin_manager.get_map_workers():
            target_json = job_dir / f"{worker.name}_result.json"
            worker_args = ["--input", str(input_path), "--output", str(target_json)]

            if worker.accepts_force_ocr and diagnostics.force_ocr_extraction:
                worker_args.append("--force-ocr")

            if worker.requires_lang:
                worker_args.extend(["--lang", doc_lang])

            logger.info("▶ Starte Spezialist: '%s'...", worker.name)
            success = self._run_worker(worker, worker_args)

            if target_json.exists():
                with open(target_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    err = worker_data.get("error", {})
                    logger.warning(
                        "⚠️ Experte '%s' meldet Problem [%s]: %s",
                        worker.name,
                        err.get("type", "Unknown"),
                        err.get("message", "Keine Details"),
                    )
                elif success:
                    blackboard_results[worker.name] = worker_data
                    logger.info("✅ '%s' dem Blackboard hinzugefügt.", worker.name)
            elif not success:
                logger.warning("⚠️ '%s' unerwartet abgestürzt.", worker.name)

        # 2. REDUCE PHASE (Sensor Fusion)
        if "layout_worker" not in blackboard_results:
            logger.error("❌ Der Layout-Basis-Worker ist fehlgeschlagen!")
            if logger.getEffectiveLevel() != logging.DEBUG:
                shutil.rmtree(job_dir, ignore_errors=True)
            return {}, {}

        spatial_dom = blackboard_results["layout_worker"]
        spatial_dom["needs_visual_reconstruction"] = (
            diagnostics.needs_visual_reconstruction
        )

        if "signature_worker" in blackboard_results:
            sig_pages = blackboard_results["signature_worker"].get("pages", [])
            self._merge_signatures(spatial_dom, sig_pages)

        if "table_worker" in blackboard_results:
            tbl_pages = blackboard_results["table_worker"].get("pages", [])
            self._merge_tables(spatial_dom, tbl_pages)

        if "formula_worker" in blackboard_results:
            self._merge_formulas(spatial_dom, blackboard_results["formula_worker"])

        if "footnote_worker" in blackboard_results:
            fn_pages = blackboard_results["footnote_worker"].get("pages", [])
            self._merge_footnotes(spatial_dom, fn_pages)

        if "form_worker" in blackboard_results:
            frm_fields = blackboard_results["form_worker"].get("fields", [])
            self._merge_forms(spatial_dom, frm_fields)

        images_dict = self._process_images(spatial_dom, job_dir)
        self._translate_content(spatial_dom, images_dict, doc_lang, job_dir)

        spatial_dom = repair_spatial_dom(spatial_dom, input_path)

        # 3. CLEANUP
        if logger.getEffectiveLevel() != logging.DEBUG:
            shutil.rmtree(job_dir, ignore_errors=True)

        return spatial_dom, images_dict


def extract_to_spatial(
    input_path: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, str]]:
    """Haupt-Einstiegspunkt für die GUI/CLI."""
    pdf_path = Path(input_path)
    logger.info("✨ Starte Orchestrierung für %s...", pdf_path.name)

    doc_lang = _get_pdf_lang(pdf_path)
    logger.info("🗣️ Dokumenten-Sprache erkannt: %s", doc_lang)

    pipeline = SemanticOrchestrator()
    spatial_dom, images_dict = pipeline.extract(pdf_path, doc_lang)
    orig_meta = _extract_original_metadata(pdf_path)

    return spatial_dom, images_dict, doc_lang, orig_meta
