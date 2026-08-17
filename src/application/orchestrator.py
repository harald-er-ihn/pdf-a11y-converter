# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Der Semantic Orchestrator.
Leitet die PDF-Analyse, ruft isolierte Worker-Prozesse auf und sammelt.
Implementiert Parallel-Execution, Blackboard-Pattern und Sensor-Fusion.
Bricht bei Formularen detailliert ab und warnt bei Formeln.
"""

import concurrent.futures
import json
import logging
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import pikepdf
from PIL import Image

from src.config import get_job_root_dir
from src.application.adapters import (
    ColumnAdapter,
    CaptionAdapter,
    HeaderFooterAdapter,
    FootnoteAdapter,
    FormulaAdapter,
    LayoutAdapter,
    SignatureAdapter,
    TableAdapter,
    VisionAdapter,
)
from src.application.dom_transformer import DOMTransformer
from src.domain.spatial import SpatialDOM
from src.infrastructure.runtime.worker_runner import WorkerRunner
from src.infrastructure.pdf.mcid_text_extractor import (
    extract_mcid_text_signals,
)
from src.infrastructure.pdf.tag_extractor import (
    collect_struct_texts,
    extract_existing_tags,
    find_struct_nodes_by_tag,
)
from src.pdf_diagnostics import PDFPreflightScanner
from src.plugins.workers import PluginManager, WorkerManifest
from src.repair import repair_spatial_dom

logger = logging.getLogger("pdf-converter")


def _get_pdf_lang(input_path: Path) -> str:
    """Extrahiert die PDF-Sprache aus Metadaten oder per Heuristik."""
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
    except Exception as e:
        logger.debug("XMP-Sprache nicht lesbar: %s", e)

    return "de-DE"


def _extract_original_metadata(input_path: Path) -> dict[str, str]:
    """Sichert Metadaten für das Overlay-Dokument."""
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
    except Exception as e:
        logger.debug("Konnte Original-Metadaten nicht lesen: %s", e)

    if not meta.get("/Title"):
        meta["/Title"] = input_path.stem.replace("_", " ")

    return meta


class SemanticOrchestrator:
    """Orchestriert die isolierten Experten-Worker typsicher."""

    def __init__(self) -> None:
        self.plugin_manager = PluginManager()
        self.temp_dir = get_job_root_dir()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _execute_map_task(
        self,
        worker: WorkerManifest,
        input_path: Path,
        job_dir: Path,
        diagnostics: Any,
        doc_lang: str,
    ) -> Dict[str, Any]:
        """Führt einen Plugin-Worker isoliert aus."""
        target_json = job_dir / f"{worker.name}_result.json"
        worker_args = [
            "--input",
            str(input_path),
            "--output",
            str(target_json),
        ]

        if worker.accepts_force_ocr and diagnostics.force_ocr_extraction:
            worker_args.append("--force-ocr")
        if worker.requires_lang:
            worker_args.extend(["--lang", doc_lang])

        logger.info("▶ Starte Spezialist: '%s'...", worker.name)
        t_start = time.time()
        success, stderr = WorkerRunner.execute(worker, worker_args)
        duration = round(time.time() - t_start, 2)

        data = None
        err = None
        coord_sys = "top_left_points"

        manifest_file = worker.worker_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                    coord_sys = manifest_data.get(
                        "coordinate_system", "top_left_points"
                    )
            except Exception:
                pass

        if target_json.exists():
            try:
                with open(target_json, "r", encoding="utf-8") as f:
                    worker_data = json.load(f)

                if worker_data.get("status") == "error":
                    err = worker_data.get("error", {})
                elif success:
                    data = worker_data
            except json.JSONDecodeError:
                pass

        if not success and not err:
            err = {
                "type": "UnmanagedCrash",
                "message": "Worker ist unerwartet abgestürzt.",
                "details": stderr,
            }

        return {
            "name": worker.name,
            "success": success and data is not None,
            "duration": duration,
            "data": data,
            "error": err,
            "coord_sys": coord_sys,
        }

    def _assign_alt_texts_to_dom(
        self,
        spatial_dom: SpatialDOM,
        images_dict: Dict[str, Tuple[Image.Image, str]],
        existing_figure_alts: list[str] | None = None,
    ) -> SpatialDOM:
        """Injeziert Alt-Texte typsicher in das SpatialDOM."""
        alt_by_image_name = {
            image_name: alt_text
            for image_name, (_, alt_text) in images_dict.items()
        }

        fallback_alts = [alt for _, alt in images_dict.values()]
        fallback_idx = 0

        existing_figure_alts = existing_figure_alts or []
        existing_alt_idx = 0

        for page in spatial_dom.pages:
            for el in page.elements:
                if el.type != "figure" or el.alt_text:
                    continue

                image_name = None
                if el.items:
                    for item in el.items:
                        candidate = item.get("image")
                        if candidate:
                            image_name = str(candidate)
                            break

                if (
                    image_name
                    and image_name in alt_by_image_name
                    and self._is_useful_existing_alt(
                        alt_by_image_name[image_name]
                    )
                ):
                    el.alt_text = alt_by_image_name[image_name]
                elif existing_alt_idx < len(existing_figure_alts):
                    el.alt_text = existing_figure_alts[existing_alt_idx]
                    existing_alt_idx += 1
                elif fallback_idx < len(fallback_alts):
                    el.alt_text = fallback_alts[fallback_idx]
                    fallback_idx += 1
                else:
                    el.alt_text = "Abbildung"

        return SpatialDOM.model_validate(spatial_dom.model_dump())

    @staticmethod
    def _is_useful_existing_alt(text: str) -> bool:
        """Filtert generische oder kaputte Alt-Texte."""
        t = re.sub(r"\s+", " ", (text or "")).strip()
        if len(t) < 3:
            return False

        low = t.lower()
        generic = {
            "bild",
            "image",
            "figure",
            "abbildung",
            "grafik",
            "graphic",
            "objekt",
            "object",
        }
        if low in generic:
            return False

        # Reine Pfad-/Dateinamen oder XObject-Artefakte nicht übernehmen.
        if re.fullmatch(r"(?:image|img|xobject|im)\W*\d+\.?\w*", low):
            return False

        return True

    def _collect_existing_figure_alts(
        self,
        existing_tags: Dict[str, Any],
    ) -> list[str]:
        """
        Sammelt vorhandene Figure-Alt-Texte als schwaches Fallback-Signal.

        Wichtig: Bei Figure-Alts dürfen Duplikate erhalten bleiben, weil mehrere
        Bilder legitim denselben Alt-Text tragen können, z.B. mehrere
        Unterschriften. Die Reihenfolge folgt dem vorhandenen StructTree, wird
        aber nur als schwaches Fallback-Signal behandelt.
        """
        if existing_tags.get("status") != "success":
            return []

        result: list[str] = []
        figure_nodes = find_struct_nodes_by_tag(existing_tags, {"Figure"})

        for node in figure_nodes:
            # Priorität innerhalb eines Figure-Knotens: /Alt vor /ActualText vor /Title.
            for field in ("alt", "actual_text", "title"):
                value = node.get(field)
                if not value:
                    continue

                cleaned = re.sub(r"\s+", " ", str(value)).strip()
                if not self._is_useful_existing_alt(cleaned):
                    continue

                result.append(cleaned)
                break

        return result

    def _translate_content(
        self,
        spatial_dom: SpatialDOM,
        images_dict: Dict[str, Tuple[Image.Image, str]],
        doc_lang: str,
        job_dir: Path,
        audit_trail: Dict[str, Any],
        existing_figure_alts: list[str] | None = None,
    ) -> SpatialDOM:
        """Übersetzt Vision-Texte via NLLB-200 Plugin."""
        texts_to_translate = {}
        for img_name, (_, alt_text) in images_dict.items():
            texts_to_translate[img_name] = alt_text

        dom_alt_refs = []
        for p_idx, page in enumerate(spatial_dom.pages):
            for e_idx, el in enumerate(page.elements):
                if el.type == "figure" and el.alt_text:
                    ref_key = f"dom_{p_idx}_{e_idx}"
                    texts_to_translate[ref_key] = el.alt_text
                    dom_alt_refs.append((p_idx, e_idx, ref_key))

        if not texts_to_translate:
            return self._assign_alt_texts_to_dom(
                spatial_dom, images_dict, existing_figure_alts
            )

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
            success, stderr = WorkerRunner.execute(manifest, args)
            audit_trail["workers"][manifest.name] = {
                "status": "success" if success else "error",
                "duration_sec": round(time.time() - t_start, 2),
            }

            worker_data = {}
            if out_json.exists():
                try:
                    with open(out_json, "r", encoding="utf-8") as f:
                        worker_data = json.load(f)
                except json.JSONDecodeError:
                    pass

                if worker_data.get("status") == "error":
                    audit_err = worker_data["error"]
                    audit_trail["workers"][manifest.name]["error_details"] = (
                        audit_err
                    )
                elif success:
                    for img_name in list(images_dict.keys()):
                        if img_name in worker_data:
                            img_obj, _ = images_dict[img_name]
                            images_dict[img_name] = (
                                img_obj,
                                worker_data[img_name],
                            )

                    for p_idx, e_idx, ref_key in dom_alt_refs:
                        if ref_key in worker_data:
                            el = spatial_dom.pages[p_idx].elements[e_idx]
                            el.alt_text = worker_data[ref_key]

            if not success and worker_data.get("status") != "error":
                logger.error(
                    "❌ Crash in 'translation_worker':\n%s", stderr.strip()
                )
                audit_trail["workers"][manifest.name]["error_details"] = {
                    "type": "UnmanagedCrash",
                    "message": "Worker abgestürzt",
                    "details": stderr,
                }

        return self._assign_alt_texts_to_dom(
            spatial_dom, images_dict, existing_figure_alts
        )

    def _process_images(
        self,
        spatial_dom: SpatialDOM,
        job_dir: Path,
        audit_trail: Dict[str, Any],
    ) -> Dict[str, Tuple[Image.Image, str]]:
        """Ruft die Vision-KI via Plugin-Schnittstelle auf."""
        images_dict = {}
        image_paths = spatial_dom.images
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
            success, stderr = WorkerRunner.execute(manifest, args)
            audit_trail["workers"][manifest.name] = {
                "status": "success" if success else "error",
                "duration_sec": round(time.time() - t_start, 2),
            }

            if output_json.exists():
                try:
                    with open(output_json, "r", encoding="utf-8") as f:
                        worker_data = json.load(f)
                except json.JSONDecodeError:
                    pass

                if worker_data.get("status") == "error":
                    audit_err = worker_data["error"]
                    audit_trail["workers"][manifest.name]["error_details"] = (
                        audit_err
                    )

            if not success and worker_data.get("status") != "error":
                logger.error(
                    "❌ Crash in 'vision_worker':\n%s", stderr.strip()
                )
                audit_trail["workers"][manifest.name]["error_details"] = {
                    "type": "UnmanagedCrash",
                    "message": "Worker abgestürzt",
                    "details": stderr,
                }

        alt_texts = (
            VisionAdapter.parse(worker_data)
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
            except Exception:
                pass

        return images_dict

    def extract(
        self, input_path: Path, doc_lang: str
    ) -> Tuple[SpatialDOM, Dict, Dict]:
        """Führt die Orchestrierung durch und schreibt den Audit-Trail."""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = self.temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        scanner = PDFPreflightScanner(input_path)
        diagnostics = scanner.analyze()

        # 🚀 ARCHITEKTUR-FIX: Ausführlicher Actionable-Error mit Verweis auf Doku
        if diagnostics.has_forms:
            msg = (
                "Interaktive Formulare (AcroForms) erkannt!\n"
                "Systembedingter Abbruch: Unser 'Semantic Overlay Pattern' stempelt das "
                "Originaldokument als flache Vektorgrafik in den Hintergrund. "
                "Interaktive Ausfüllfelder würden dabei ihre Funktion verlieren und "
                "für Screenreader unzugänglich werden.\n"
                "👉 Bitte konsultieren Sie die README.md (Abschnitt 'Systemgrenzen') für weitere Details."
            )
            raise ValueError(msg)

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

        existing_tags_path = job_dir / "existing_tags.json"
        existing_tags = extract_existing_tags(input_path, existing_tags_path)
        existing_tags_summary = existing_tags.get("summary", {})

        existing_mcid_text_path = job_dir / "existing_mcid_text.json"
        try:
            existing_mcid_text = extract_mcid_text_signals(
                input_path,
                existing_mcid_text_path,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(
                "⚠️ MCID-Text-Signale konnten nicht extrahiert werden: %s.",
                e,
            )
            existing_mcid_text = {
                "status": "error",
                "reason": str(e),
                "summary": {},
                "records": [],
            }
            with open(existing_mcid_text_path, "w", encoding="utf-8") as f:
                json.dump(existing_mcid_text, f, ensure_ascii=False, indent=2)

        existing_mcid_text_summary = existing_mcid_text.get("summary", {})

        audit_trail["pre_tag_extraction"] = {
            "status": existing_tags.get("status"),
            "is_tagged": existing_tags.get("is_tagged", False),
            "reason": existing_tags.get("reason"),
            "artifact": str(existing_tags_path),
            "summary": existing_tags_summary,
            "mcid_text_signals": {
                "status": existing_mcid_text.get("status"),
                "reason": existing_mcid_text.get("reason"),
                "artifact": str(existing_mcid_text_path),
                "summary": existing_mcid_text_summary,
            },
        }

        if existing_tags.get("status") == "success":
            logger.info(
                "🏷️ Vorhandene PDF-Tags extrahiert: %s Tags, %s MCIDs.",
                existing_tags_summary.get("tag_count", 0),
                existing_tags_summary.get("mcid_count", 0),
            )
        elif existing_tags.get("status") == "skipped":
            logger.info(
                "🏷️ Keine vorhandenen PDF-Tags extrahiert: %s.",
                existing_tags.get("reason", "unbekannter Grund"),
            )
        else:
            logger.warning(
                "⚠️ Vorhandene PDF-Tags konnten nicht sauber extrahiert werden: %s.",
                existing_tags.get("reason", "unbekannter Fehler"),
            )

        if existing_mcid_text.get("status") == "success":
            logger.info(
                "🔎 MCID-Text-Signale extrahiert: %s Records.",
                existing_mcid_text_summary.get("mcid_text_count", 0),
            )
        elif existing_mcid_text.get("status") == "skipped":
            logger.info(
                "🔎 Keine MCID-Text-Signale extrahiert: %s.",
                existing_mcid_text.get("reason", "unbekannter Grund"),
            )
        else:
            logger.warning(
                "⚠️ MCID-Text-Signale konnten nicht sauber extrahiert werden: %s.",
                existing_mcid_text.get("reason", "unbekannter Fehler"),
            )

        existing_figure_alts = self._collect_existing_figure_alts(
            existing_tags
        )

        existing_heading_nodes = find_struct_nodes_by_tag(
            existing_tags,
            {"H", "H1", "H2", "H3", "H4", "H5", "H6"},
        )
        existing_h1_nodes = find_struct_nodes_by_tag(existing_tags, {"H1"})

        existing_table_nodes = find_struct_nodes_by_tag(
            existing_tags, {"Table"}
        )
        existing_th_nodes = find_struct_nodes_by_tag(existing_tags, {"TH"})
        existing_td_nodes = find_struct_nodes_by_tag(existing_tags, {"TD"})

        audit_trail["pre_tag_extraction"]["signals"] = {
            "figure_alt_count": len(existing_figure_alts),
            "heading_tag_count": len(existing_heading_nodes),
            "h1_count": len(existing_h1_nodes),
            "table_tag_count": len(existing_table_nodes),
            "th_count": len(existing_th_nodes),
            "td_count": len(existing_td_nodes),
        }

        blackboard_results = {}
        blackboard_coord_sys = {}
        # Ignoriere form_worker komplett, da wir oben bereits hart abbrechen!
        map_workers = [
            w
            for w in self.plugin_manager.get_map_workers()
            if w.name not in {"form_worker", "formula_worker"}
        ]

        max_workers = min(2, len(map_workers)) if map_workers else 1

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        ) as ex:
            futures = []
            for worker in map_workers:
                futures.append(
                    ex.submit(
                        self._execute_map_task,
                        worker,
                        input_path,
                        job_dir,
                        diagnostics,
                        doc_lang,
                    )
                )

            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                w_name = res["name"]

                audit_trail["workers"][w_name] = {
                    "status": "success" if res["success"] else "error",
                    "duration_sec": res["duration"],
                }

                if res["error"]:
                    audit_trail["workers"][w_name]["error_details"] = res[
                        "error"
                    ]
                elif res["success"] and res["data"]:
                    blackboard_results[w_name] = res["data"]
                    blackboard_coord_sys[w_name] = res["coord_sys"]
                    logger.info(
                        "✅ '%s' fertig (%ss).", w_name, res["duration"]
                    )

        base_layout_name = None
        if "layout_worker_docling" in blackboard_results:
            base_layout_name = "layout_worker_docling"
        else:
            logger.warning(
                "⚠️ Docling fehlgeschlagen. Starte Marker-Fallback..."
            )
            marker_manifest = self.plugin_manager.get_worker(
                "layout_worker_marker"
            )
            if marker_manifest:
                res = self._execute_map_task(
                    marker_manifest, input_path, job_dir, diagnostics, doc_lang
                )
                audit_trail["workers"][res["name"]] = {
                    "status": "success" if res["success"] else "error",
                    "duration_sec": res["duration"],
                }
                if res["error"]:
                    audit_trail["workers"][res["name"]]["error_details"] = res[
                        "error"
                    ]
                elif res["success"] and res["data"]:
                    blackboard_results[res["name"]] = res["data"]
                    blackboard_coord_sys[res["name"]] = res["coord_sys"]
                    base_layout_name = "layout_worker_marker"
                    logger.info(
                        "✅ '%s' fertig (%ss).", res["name"], res["duration"]
                    )

        if not base_layout_name:
            logger.error(
                "❌ Der Layout-Basis-Worker ist komplett fehlgeschlagen!"
            )
            return SpatialDOM(), {}, audit_trail

        raw_spatial_dom = blackboard_results[base_layout_name]
        layout_c_sys = blackboard_coord_sys.get(
            base_layout_name, "top_left_points"
        )

        try:
            if base_layout_name == "layout_worker_docling":
                spatial_dom = LayoutAdapter.normalize_docling(
                    raw_spatial_dom, layout_c_sys
                )
            else:
                spatial_dom = LayoutAdapter.normalize_marker(
                    raw_spatial_dom, layout_c_sys
                )

            vis_recon = diagnostics.needs_visual_reconstruction
            spatial_dom.needs_visual_reconstruction = vis_recon
        except Exception as e:
            logger.error("❌ Spatial DOM Validierung fehlgeschlagen: %s", e)
            return SpatialDOM(), {}, audit_trail

        formula_types = {"formula", "equation", "math"}

        def _looks_like_formula_text(text: str) -> bool:
            """
            Heuristik für Formel-Kandidaten, wenn der Layout-Worker keine
            expliziten formula/equation/math-Typen geliefert hat.

            Wichtig: Diese Heuristik entscheidet nur, ob der formula_worker
            gestartet wird. Die eigentliche Formel-Extraktion bleibt Aufgabe
            des formula_worker.
            """
            t = re.sub(r"\s+", " ", (text or "")).strip()
            if len(t) < 3:
                return False

            # Unicode Mathematical Alphanumeric Symbols, z.B. 𝐼𝑜𝑈, 𝐴, 𝐵.
            has_math_alpha = bool(re.search(r"[\U0001D400-\U0001D7FF]", t))

            # Mathematische Operatoren/Symbole, inklusive typografischem Minus.
            has_math_symbol = bool(re.search(r"[=+*/^⋅×÷−√∑∫∩∪≤≥≈≠±∞|]", t))

            # Griechische Zeichen, häufig in Formeln/Konstanten.
            has_greek = bool(
                re.search(
                    r"[αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]", t
                )
            )

            # Funktions-/Formelstruktur wie IoU(A, B) = oder Score(E1, E2) =
            has_function_shape = bool(re.search(r"\$[^)]{1,80}\$\s*=", t))

            if has_math_alpha and (has_math_symbol or has_function_shape):
                return True

            if has_greek and "=" in t:
                return True

            if has_function_shape and has_math_symbol:
                return True

            # LaTeX-/ASCII-Hinweise für andere Testdokumente.
            if re.search(
                r"\\(?:frac|sqrt|sum|int)|\b(?:frac|sqrt|sum|int)\b", t
            ):
                return True

            return False

        layout_formula_candidates = [
            (page.page_num, el.text or "", el.type)
            for page in spatial_dom.pages
            for el in page.elements
            if (el.type or "").lower() in formula_types
            or _looks_like_formula_text(el.text or "")
        ]

        pdf_formula_candidates = []
        if not layout_formula_candidates:
            try:
                import fitz  # pylint: disable=import-outside-toplevel

                with fitz.open(input_path) as doc:
                    for page_idx, pdf_page in enumerate(doc, start=1):
                        for line in pdf_page.get_text(
                            "text", sort=True
                        ).splitlines():
                            line = line.strip()
                            if _looks_like_formula_text(line):
                                pdf_formula_candidates.append((page_idx, line))
                                break
                        if pdf_formula_candidates:
                            break
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "Formel-Heuristik via PyMuPDF übersprungen: %s", e
                )

        existing_formula_tag_names = {"Formula", "Math", "Equation"}
        pretag_formula_nodes = []
        pretag_formula_text_candidates = []

        if existing_tags.get("status") == "success":
            pretag_formula_nodes = find_struct_nodes_by_tag(
                existing_tags,
                existing_formula_tag_names,
            )

            for text_value in collect_struct_texts(
                existing_tags,
                None,
                fields=("actual_text", "alt", "title"),
            ):
                if _looks_like_formula_text(text_value):
                    pretag_formula_text_candidates.append(text_value)

        audit_trail["pre_tag_extraction"].setdefault("signals", {}).update(
            {
                "formula_tag_count": len(pretag_formula_nodes),
                "formula_text_candidate_count": len(
                    pretag_formula_text_candidates
                ),
            }
        )

        has_formula_candidates = bool(
            layout_formula_candidates
            or pdf_formula_candidates
            or pretag_formula_nodes
            or pretag_formula_text_candidates
        )

        if has_formula_candidates:
            logger.info(
                "🧮 Formel-Kandidaten erkannt: "
                "layout=%d, pdf_text=%d, existing_tags=%d, existing_text=%d",
                len(layout_formula_candidates),
                len(pdf_formula_candidates),
                len(pretag_formula_nodes),
                len(pretag_formula_text_candidates),
            )

        if has_formula_candidates:
            formula_manifest = self.plugin_manager.get_worker("formula_worker")
            if formula_manifest:
                res = self._execute_map_task(
                    formula_manifest,
                    input_path,
                    job_dir,
                    diagnostics,
                    doc_lang,
                )
                audit_trail["workers"][res["name"]] = {
                    "status": "success" if res["success"] else "error",
                    "duration_sec": res["duration"],
                }
                if res["error"]:
                    audit_trail["workers"][res["name"]]["error_details"] = res[
                        "error"
                    ]
                elif res["success"] and res["data"]:
                    blackboard_results[res["name"]] = res["data"]
                    blackboard_coord_sys[res["name"]] = res["coord_sys"]
                    logger.info(
                        "✅ '%s' fertig (%ss).",
                        res["name"],
                        res["duration"],
                    )
        else:
            audit_trail["workers"]["formula_worker"] = {
                "status": "skipped",
                "duration_sec": 0,
                "reason": "no_formula_candidates_in_layout_text_or_existing_tags",
            }
            logger.info(
                "⏭️ Überspringe 'formula_worker': "
                "keine Formel-Kandidaten im Layout, PDF-Text oder vorhandenen Tags."
            )

        page_heights = {
            page.page_num: page.height for page in spatial_dom.pages
        }

        if "header_footer_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get(
                "header_footer_worker", "top_left_points"
            )
            artifacts = HeaderFooterAdapter.parse(
                blackboard_results["header_footer_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_artifacts(
                spatial_dom, artifacts
            )

        if "column_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get(
                "column_worker", "top_left_points"
            )
            cols = ColumnAdapter.parse(
                blackboard_results["column_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_columns(spatial_dom, cols)

        if "caption_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get(
                "caption_worker", "top_left_points"
            )
            caps = CaptionAdapter.parse(
                blackboard_results["caption_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_captions(spatial_dom, caps)

        if "signature_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get(
                "signature_worker", "top_left_points"
            )
            sig = SignatureAdapter.parse(
                blackboard_results["signature_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_signatures(spatial_dom, sig)

        if "table_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get("table_worker", "top_left_points")
            tbl = TableAdapter.parse(
                blackboard_results["table_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_tables(spatial_dom, tbl)

        # FORMEL WARNUNG
        if "formula_worker" in blackboard_results:
            f_md = FormulaAdapter.parse(blackboard_results["formula_worker"])
            if f_md and ("$$" in f_md or "\\[" in f_md or "\\(" in f_md):
                logger.warning(
                    "⚠️ WARNUNG: Das Dokument enthält mathematische Formeln! "
                    "Die MathML-Einbettung ist formal korrekt, wird jedoch von "
                    "vielen Screenreadern noch fehlerhaft interpretiert."
                )
            spatial_dom = DOMTransformer.merge_formulas(spatial_dom, f_md)

        if "footnote_worker" in blackboard_results:
            c_sys = blackboard_coord_sys.get(
                "footnote_worker", "top_left_points"
            )
            fn = FootnoteAdapter.parse(
                blackboard_results["footnote_worker"], c_sys, page_heights
            )
            spatial_dom = DOMTransformer.merge_footnotes(spatial_dom, fn)

        images_dict = self._process_images(spatial_dom, job_dir, audit_trail)
        spatial_dom = self._translate_content(
            spatial_dom,
            images_dict,
            doc_lang,
            job_dir,
            audit_trail,
            existing_figure_alts,
        )

        # 1. Tags anpassen (z.B. p -> h1)
        spatial_dom = repair_spatial_dom(spatial_dom, input_path)

        # 2. Zusammenhängende Sätze wieder zu sauberen Absätzen mergen!
        spatial_dom = DOMTransformer.optimize_reading_flow(spatial_dom)

        if logger.getEffectiveLevel() != logging.DEBUG:
            # Die Pre-Tag-Artefakte sind Teil des Audit-Trails und müssen auch
            # außerhalb des Debug-Modus erhalten bleiben. Transiente Worker-
            # Artefakte werden entfernt.
            preserved_artifacts = {
                "existing_tags.json",
                "existing_mcid_text.json",
            }
            for artifact in job_dir.iterdir():
                if artifact.name in preserved_artifacts:
                    continue
                try:
                    if artifact.is_dir():
                        shutil.rmtree(artifact, ignore_errors=True)
                    else:
                        artifact.unlink(missing_ok=True)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.debug("Konnte Job-Artefakt nicht entfernen: %s", e)

        return spatial_dom, images_dict, audit_trail


def extract_to_spatial(
    input_path: str,
) -> Tuple[SpatialDOM, Dict[str, Any], str, Dict[str, str], Dict[str, Any]]:
    """Haupt-Einstiegspunkt für die GUI/CLI."""
    pdf_path = Path(input_path)
    logger.info("✨ Starte Orchestrierung für %s...", pdf_path.name)

    doc_lang = _get_pdf_lang(pdf_path)
    pipeline = SemanticOrchestrator()

    spatial_dom, images_dict, audit_trail = pipeline.extract(
        pdf_path, doc_lang
    )
    orig_meta = _extract_original_metadata(pdf_path)

    return spatial_dom, images_dict, doc_lang, orig_meta, audit_trail
