# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Der Semantic Orchestrator (Enterprise Edition).
Nutzt ein DAG-Framework und dynamische Plugins zur parallelen Ausführung
der isolierten Worker-Prozesse. Führt die Sensor-Fusion (Merge-Phase) durch.
Integriert die 'Shared AI Runtime' via dynamischer PYTHONPATH Injection.
"""

import json
import logging
import os
import sys
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Dict, Tuple, List, Any, Optional

import pikepdf
from PIL import Image

from src.config import get_worker_python, _get_app_base_dir
from src.infrastructure.dag_executor import DAGExecutor, DAGTask
from src.pdf_diagnostics import PDFPreflightScanner
from src.plugins.base import WorkerPlugin
from src.plugins.plugin_loader import PluginLoader
from src.repair import repair_spatial_dom
from src.vision import get_image_descriptions

logger = logging.getLogger("pdf-converter")


@dataclass
class ExtractionResult:
    """DTO für die Rückgabe der Map & Reduce Phase (Sensor Fusion)."""

    spatial_dom: Dict[str, Any]
    images_dict: Dict[str, Tuple[Image.Image, str]]
    doc_lang: str
    original_meta: Dict[str, str]


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


# pylint: disable=too-few-public-methods
class SemanticOrchestrator:
    """Orchestriert die Pipeline, lädt Plugins und führt die Sensor Fusion durch."""

    def __init__(self) -> None:
        self.base_dir = _get_app_base_dir()
        self.workers_dir = self.base_dir / "workers"

        # Enterprise-sicheres Temp-Verzeichnis (verhindert PermissionErrors)
        sys_temp = Path(tempfile.gettempdir())
        self.temp_dir = sys_temp / "pdf-a11y-jobs"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _inject_runtime_pythonpath(self, env: Dict[str, str]) -> None:
        """Injiziert den Pfad zur Shared AI Runtime in die Umgebungsvariablen."""
        from src.runtime_bootstrap import get_global_runtime_dir

        is_frozen = getattr(sys, "frozen", False)

        if not is_frozen and (self.base_dir / "runtime" / "ai_env").exists():
            # Dev-Modus (Source Code)
            runtime_dir = self.base_dir / "runtime" / "ai_env"
            logger.debug("Nutze lokale Entwickler-Runtime: %s", runtime_dir)
        else:
            # Produktions-Modus (ProgramData)
            runtime_dir = get_global_runtime_dir() / "ai_env"

        if sys.platform == "win32":
            runtime_site = runtime_dir / "Lib" / "site-packages"
        else:
            site_pkgs = list(runtime_dir.glob("lib/python*/site-packages"))
            runtime_site = site_pkgs[0] if site_pkgs else runtime_dir / "lib"

        if runtime_site.exists():
            env["PYTHONPATH"] = (
                str(runtime_site) + os.pathsep + env.get("PYTHONPATH", "")
            )
        else:
            logger.warning(
                "⚠️ Globale AI Runtime nicht gefunden unter: %s", runtime_site
            )

    def _get_optimized_environment(self) -> Dict[str, str]:
        """
        Baut ein hochoptimiertes Environment-Dict für die KI-Worker.
        Nutzt das externe Skript runtime_optimizer.py, um Hardware-Features
        (bfloat16, CUDA) zu erkennen, ohne Torch in den Main-Prozess zu laden.
        """
        env = os.environ.copy()

        # 1. PYTHONPATH für die Shared AI Runtime injizieren
        self._inject_runtime_pythonpath(env)

        # 2. Hardware-Erkennung via Subprocess
        hw_info = {"cuda": False, "bf16": False, "cpu_count": 4}
        try:
            # Wir nutzen den Python-Interpreter der Runtime, der Torch kennt
            py_exe = get_worker_python("vision_worker")
            opt_script = self.base_dir / "src" / "runtime_optimizer.py"

            res = subprocess.run(
                [str(py_exe), str(opt_script)],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            # Das Skript gibt uns ein sauberes JSON zurück
            hw_info = json.loads(res.stdout.strip())
            logger.debug("🧠 Hardware-Profil geladen: %s", hw_info)
        except Exception as e:
            logger.warning(
                "⚠️ Hardware-Erkennung fehlgeschlagen. Nutze CPU-Fallback. (%s)", e
            )

        # 3. Precision Switching (Entscheidet über float32, float16 oder bfloat16)
        precision = "fp32"
        if hw_info.get("cuda"):
            precision = "bf16" if hw_info.get("bf16") else "fp16"
            env["CUDA_VISIBLE_DEVICES"] = (
                "0"  # Verhindert, dass Worker auf falschen GPUs landen
            )
            logger.debug("⚡ Aktiviere GPU-Beschleunigung mit %s Precision", precision)

        # Wir übergeben die Precision an die Worker via Environment-Variable
        env["PDF_A11Y_PRECISION"] = precision

        # 4. Torch Runtime Tuning (Aggressive CPU/Memory Optimierungen)
        env["PYTORCH_CUDA_ALLOC_CONF"] = (
            "max_split_size_mb:128"  # Verhindert Memory-Fragmentation
        )
        env["TOKENIZERS_PARALLELISM"] = "false"  # Verhindert Deadlocks in Transformers

        # CPU Threads limitieren, damit sich parallele Worker im DAG nicht gegenseitig blockieren!
        # (Nimmt maximal die halbe CPU-Kern-Zahl, aber höchstens 8)
        optimal_threads = str(min(8, max(1, hw_info.get("cpu_count", 4) // 2)))
        env["OMP_NUM_THREADS"] = optimal_threads
        env["MKL_NUM_THREADS"] = optimal_threads

        return env

    def _run_plugin_task(
        self,
        plugin: WorkerPlugin,
        input_pdf: Path,
        job_dir: Path,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Führt ein Worker-Plugin isoliert aus (Graceful Degradation).
        """
        try:
            py_exe = get_worker_python(plugin.name)
        except FileNotFoundError as e:
            logger.error(str(e))
            return None

        cmd_args = plugin.get_arguments(input_pdf, job_dir, context)
        script_path = self.workers_dir / plugin.name / plugin.script_name
        cmd = [str(py_exe), str(script_path)] + cmd_args

        try:
            # 🚀 HIER: Wir holen uns das hochoptimierte Environment!
            opt_env = self._get_optimized_environment()

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                env=opt_env,  # 🚀 HIER: Wir übergeben es an den Worker-Prozess!
                cwd=str(self.base_dir),
            )

            out_file = plugin.get_output_path(job_dir)
            if out_file.exists():
                with open(out_file, "r", encoding="utf-8") as f:
                    return json.load(f)

            logger.warning("⚠️ Plugin '%s' lief durch, aber Output fehlt.", plugin.name)
            return None

        except subprocess.CalledProcessError as e:
            logger.error(
                "❌ Worker '%s' ist abgestürzt (Code %s).", plugin.name, e.returncode
            )
            err_msg = e.stderr.strip() if e.stderr else "Kein Error-Log verfügbar."
            logger.error(
                "--- WORKER ERROR LOG ---\n%s\n------------------------", err_msg
            )
            return None
        except Exception as e:
            logger.error("❌ Systemfehler beim Ausführen von %s: %s", plugin.name, e)
            return None

    def _translate_content(
        self,
        spatial_dom: Dict[str, Any],
        images_dict: Dict[str, Tuple[Image.Image, str]],
        doc_lang: str,
        job_dir: Path,
    ) -> None:
        """Übersetzt Alt-Texte und mappt sie präzise in den Spatial DOM."""
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

        args = ["--input", str(in_json), "--output", str(out_json), "--lang", doc_lang]

        try:
            py_exe = get_worker_python("translation_worker")
            script_path = self.workers_dir / "translation_worker" / "run_translation.py"
            cmd = [str(py_exe), str(script_path)] + args

            # 🚀 HIER: Auch die Translation-Chain bekommt das optimierte Environment!
            opt_env = self._get_optimized_environment()

            logger.info("▶ Starte Translation-Chain: 'translation_worker'...")
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                env=opt_env,
                cwd=str(self.base_dir),
            )
            if out_json.exists():
                with open(out_json, "r", encoding="utf-8") as f:
                    trans_results = json.load(f)

                for img_name in list(images_dict.keys()):
                    if img_name in trans_results:
                        img_obj, _ = images_dict[img_name]
                        images_dict[img_name] = (img_obj, trans_results[img_name])

                for p_idx, e_idx, ref_key in dom_alt_refs:
                    if ref_key in trans_results:
                        el = spatial_dom["pages"][p_idx]["elements"][e_idx]
                        el["alt_text"] = trans_results[ref_key]

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Übersetzung übersprungen: %s", e)

        self._assign_alt_texts_to_dom(spatial_dom, images_dict)

    def _assign_alt_texts_to_dom(
        self,
        spatial_dom: Dict[str, Any],
        images_dict: Dict[str, Tuple[Image.Image, str]],
    ) -> None:
        """Weist die Alt-Texte den leeren Layout-Figures zu."""
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

    def _merge_signatures(
        self, spatial_dom: Dict[str, Any], signatures: List[Dict[str, Any]]
    ) -> None:
        """Webt erkannte Unterschriften als Grafiken in den Spatial DOM ein."""
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
            logger.info("📝 %s Unterschrift(en) integriert.", total_sigs)

    def _merge_tables(
        self, spatial_dom: Dict[str, Any], table_pages: List[Dict[str, Any]]
    ) -> None:
        """Webt Tabellen in den Spatial DOM ein und entfernt Kollisionen."""
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
        """Webt interaktive Formularfelder als Dummy-Elemente ein."""
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
        """Webt erkannte Fußnoten in den Spatial DOM ein."""
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

                    if any(_is_inside(cx, cy, f["bbox"]) for f in f_elements):
                        base_el["type"] = "Note"
                        total_notes += 1
                break
        if total_notes > 0:
            logger.info("📝 %s Textblöcke als Fußnote markiert.", total_notes)

    def _merge_formulas(
        self, spatial_dom: Dict[str, Any], formula_data: Dict[str, Any]
    ) -> None:
        """Ersetzt kaputte OCR-Mülltexte durch echtes LaTeX von Nougat."""
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
        """Lässt den Vision-Worker Alt-Texte generieren."""
        images_dict = {}
        image_paths = spatial_dom.get("images", {})
        if not image_paths:
            return images_dict

        alt_texts = get_image_descriptions(image_paths, job_dir)
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

    def extract(self, input_path: Path, doc_lang: str) -> ExtractionResult:
        """
        Orchestriert die Map & Reduce Phase via DAG und Plugin-Framework.
        Gibt die internen Daten als ExtractionResult DTO zurück.
        """
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = self.temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        scanner = PDFPreflightScanner(input_path)
        diagnostics = scanner.analyze()

        context = {"lang": doc_lang, "force_ocr": diagnostics.force_ocr_extraction}
        orig_meta = _extract_original_metadata(input_path)

        # 1. MAP PHASE (Dynamische Plugin-Ermittlung)
        plugins = PluginLoader.load_all(str(self.workers_dir))
        dag_tasks = []

        for plugin in plugins:
            action = partial(
                self._run_plugin_task, plugin, input_path, job_dir, context
            )
            dag_tasks.append(
                DAGTask(
                    name=plugin.name, action=action, dependencies=plugin.dependencies
                )
            )

        # 2. PARALLEL EXECUTION (DAG)
        executor = DAGExecutor(max_workers=4)
        dag_results = executor.execute(dag_tasks)

        blackboard_results = {k: v for k, v in dag_results.items() if v is not None}

        # 3. REDUCE PHASE (Sensor Fusion)
        if "layout_worker" not in blackboard_results:
            logger.error("❌ Der Layout-Basis-Worker ist fehlgeschlagen!")
            if logger.getEffectiveLevel() != logging.DEBUG:
                shutil.rmtree(job_dir, ignore_errors=True)
            return ExtractionResult({}, {}, doc_lang, orig_meta)

        spatial_dom = blackboard_results["layout_worker"]
        spatial_dom["needs_visual_reconstruction"] = (
            diagnostics.needs_visual_reconstruction
        )

        if "signature_worker" in blackboard_results:
            self._merge_signatures(
                spatial_dom, blackboard_results["signature_worker"].get("pages", [])
            )
        if "table_worker" in blackboard_results:
            self._merge_tables(
                spatial_dom, blackboard_results["table_worker"].get("pages", [])
            )
        if "formula_worker" in blackboard_results:
            self._merge_formulas(spatial_dom, blackboard_results["formula_worker"])
        if "footnote_worker" in blackboard_results:
            self._merge_footnotes(
                spatial_dom, blackboard_results["footnote_worker"].get("pages", [])
            )
        if "form_worker" in blackboard_results:
            self._merge_forms(
                spatial_dom, blackboard_results["form_worker"].get("fields", [])
            )

        # 4. TRANSLATION CHAIN
        images_dict = self._process_images(spatial_dom, job_dir)
        self._translate_content(spatial_dom, images_dict, doc_lang, job_dir)

        # 5. REPAIR & SANITIZATION
        spatial_dom = repair_spatial_dom(spatial_dom, input_path)

        if logger.getEffectiveLevel() != logging.DEBUG:
            shutil.rmtree(job_dir, ignore_errors=True)

        return ExtractionResult(
            spatial_dom=spatial_dom,
            images_dict=images_dict,
            doc_lang=doc_lang,
            original_meta=orig_meta,
        )


def _get_optimized_environment(self) -> Dict[str, str]:
    """
    Baut ein hochoptimiertes Environment-Dict für die KI-Worker.
    Nutzt den runtime_optimizer, um Hardware-Features (bfloat16, CUDA) zu erkennen.
    """
    env = os.environ.copy()

    # 1. PYTHONPATH für die Shared AI Runtime injizieren
    self._inject_runtime_pythonpath(env)

    # 2. Hardware-Erkennung via Subprocess (isoliert den Main-Prozess von Torch)
    hw_info = {"cuda": False, "bf16": False, "cpu_count": 4}
    try:
        py_exe = get_worker_python("vision_worker")  # Nutzt die AI-Runtime
        opt_script = self.base_dir / "src" / "runtime_optimizer.py"

        res = subprocess.run(
            [str(py_exe), str(opt_script)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        hw_info = json.loads(res.stdout.strip())
        logger.info("🧠 Hardware-Profil geladen: %s", hw_info)
    except Exception as e:
        logger.warning(
            "⚠️ Hardware-Erkennung fehlgeschlagen. Nutze CPU-Fallback. (%s)", e
        )

    # 3. Precision Switching
    precision = "fp32"
    if hw_info.get("cuda"):
        precision = "bf16" if hw_info.get("bf16") else "fp16"
        env["CUDA_VISIBLE_DEVICES"] = "0"
        logger.info("⚡ Aktiviere GPU-Beschleunigung mit %s Precision", precision)

    env["PDF_A11Y_PRECISION"] = precision

    # 4. Torch Runtime Tuning (Aggressive Optimierungen)
    env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"
    env["TOKENIZERS_PARALLELISM"] = "false"

    # CPU Threads limitieren, damit sich parallele Worker nicht gegenseitig blockieren
    optimal_threads = str(min(8, max(1, hw_info.get("cpu_count", 4) // 2)))
    env["OMP_NUM_THREADS"] = optimal_threads
    env["MKL_NUM_THREADS"] = optimal_threads

    return env


def extract_to_spatial(input_path: str) -> ExtractionResult:
    """Einstiegspunkt für die Application-Facade."""
    pdf_path = Path(input_path)
    logger.info("✨ Starte parallele Orchestrierung (DAG) für %s...", pdf_path.name)

    doc_lang = _get_pdf_lang(pdf_path)
    logger.info("🗣️ Dokumenten-Sprache erkannt: %s", doc_lang)

    pipeline = SemanticOrchestrator()
    return pipeline.extract(pdf_path, doc_lang)
