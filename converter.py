"""
PDF-A11y-Converter (Standalone)
Service für KI-Rekonstruktion (Marker + BLIP).
"""

import os

# ==============================================================================
# 0. UMGEBUNGSVARIABLEN & CACHE (MUSS VOR ALLEN KI-IMPORTEN PASSIEREN!)
# ==============================================================================
m_path = os.path.expanduser("~/.pdf-a11y-models")
os.makedirs(m_path, exist_ok=True)

os.environ["HF_HOME"] = m_path
os.environ["MARKER_CACHE_DIR"] = m_path
os.environ["SURYA_CACHE_DIR"] = m_path
os.environ["DATALAB_CACHE_DIR"] = m_path
os.environ["MODEL_CACHE_DIR"] = m_path

# Anti-Deadlock Limits für lokale CPUs
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAX_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
# ==============================================================================

import argparse
import base64
import gc
import re
import time
import unicodedata
import logging
import subprocess
import shutil
from io import BytesIO

import markdown
import marker.models
import pikepdf
import torch
from marker.converters.pdf import PdfConverter
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from transformers import BlipForConditionalGeneration, BlipProcessor

torch.set_num_threads(1)

# --- 1. LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("pdf-converter")

# --- 2. BLIP VISION MODEL (SINGLETON) ---
class BlipModel:
    _instance = None
    processor = None
    model = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            model_id = "Salesforce/blip-image-captioning-base"
            logger.info(f"🤖 Lade Vision-Modell: {model_id}")
            cls.processor = BlipProcessor.from_pretrained(model_id)
            cls.model = BlipForConditionalGeneration.from_pretrained(model_id)
            cls.model.to("cpu")
            cls._instance = cls
        return cls._instance

def get_image_description(pil_image):
    try:
        blip = BlipModel.get_instance()
        inputs = blip.processor(pil_image, return_tensors="pt")
        out = blip.model.generate(**inputs, max_new_tokens=40)
        return blip.processor.decode(out[0], skip_special_tokens=True).capitalize()
    except Exception as err:
        logger.error(f"❌ BLIP-Fehler: {err}")
        return "Visual representation"

# --- 3. PDF PROCESSING LOGIC ---
def _apply_pdfua_metadata(pdf_path, original_docinfo, doc_lang):
    logger.info("🔧 Finalisiere PDF-Metadaten für ISO 14289-1 (PDF/UA-1)...")
    if not os.path.exists(pdf_path): return
    try:
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            if "/Info" in pdf.trailer: del pdf.trailer["/Info"]
            for key, value in original_docinfo.items(): pdf.docinfo[key] = value
            title_text = str(original_docinfo.get("/Title", "")).strip() or "Barrierefreies Dokument"
            pdf.docinfo["/Title"] = title_text
            with pdf.open_metadata() as meta:
                meta["dc:title"] = title_text
                meta["pdfuaid:part"] = "1"
                if "pdfaid:part" in meta: del meta["pdfaid:part"]
                if "pdfaid:conformance" in meta: del meta["pdfaid:conformance"]
            pdf.Root["/Lang"] = doc_lang
            if "/ViewerPreferences" not in pdf.Root: pdf.Root.ViewerPreferences = pikepdf.Dictionary()
            pdf.Root.ViewerPreferences["/DisplayDocTitle"] = True
            if "/MarkInfo" not in pdf.Root: pdf.Root.MarkInfo = pikepdf.Dictionary()
            pdf.Root.MarkInfo["/Marked"] = True
            pdf.save(pdf_path, force_version="1.7")
    except Exception as pipe_err:
        logger.warning(f"⚠️ Pikepdf Warnung (Metadaten): {pipe_err}")

def _process_images(md_text, images_dict):
    if not images_dict: return md_text
    logger.info(f"🤖 Verarbeite {len(images_dict)} Bilder via BLIP...")
    for img_name, pil_img in images_dict.items():
        alt_text = get_image_description(pil_img)
        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        img_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{img_str}"
        pattern = r"!\[.*?\]\(" + re.escape(img_name) + r"\)"
        replacement = f"![{alt_text}]({data_uri})"
        md_text = re.sub(pattern, replacement, md_text)
    return md_text

def guess_and_fix_structure(md_text, images_dict):
    logger.info("🤖 Bereinige Steuerzeichen...")
    md_text = unicodedata.normalize("NFC", md_text)
    md_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\xad\u200b]", "", md_text)
    md_text = re.sub(r"[\uE000-\uF8FF]", "", md_text)
    md_text = md_text.replace("[ ]", "☐").replace("[x]", "☑").replace("[X]", "☑")
    md_text = _process_images(md_text, images_dict)
    logger.info("🤖 Prüfe und korrigiere Überschriften-Hierarchie...")
    lines = md_text.split("\n")
    current_level = 0
    has_headings = False
    for i, line in enumerate(lines):
        match = re.match(r"^\s*(#+)\s+(.*)", line)
        if match:
            has_headings = True
            level = len(match.group(1))
            if current_level == 0: level = 1
            elif level > current_level + 1: level = current_level + 1
            current_level = level
            lines[i] = f"{'#' * level} {match.group(2)}"
    if not has_headings:
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith(("<img", "!", "|")):
                lines[i] = f"# {line.strip()}"
                break
    return "\n".join(lines)

def _save_to_pdf(html_text, output_path, doc_lang, title_text):
    css_style = """
    @page { size: A4; margin: 2.5cm; }
    body { font-family: Arial, Helvetica, sans-serif; font-size: 11pt; line-height: 1.5; color: #222; }
    h1, h2, h3, h4 { page-break-after: avoid; color: #000; }
    img { max-width: 250px; max-height: 150px; display: block; margin-bottom: 1.5em; page-break-inside: avoid; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 1.5em; }
    tr { page-break-inside: avoid; }
    th, td { border: 1px solid #444; padding: 6px; text-align: left; }
    th { background-color: #f9f9f9; font-weight: bold; }
    ul { list-style-type: none; padding-left: 1rem; }
    li::before { content: '- '; margin-left: -1rem; }
    """
    full_html = f"<!DOCTYPE html>\n<html lang='{doc_lang}'>\n<head><meta charset='UTF-8'>\n<title>{title_text}</title>\n</head>\n<body>\n<main>\n{html_text}\n</main>\n</body>\n</html>"
    font_config = FontConfiguration()
    custom_css = CSS(string=css_style, font_config=font_config)
    HTML(string=full_html, base_url=os.getcwd()).write_pdf(output_path, stylesheets=[custom_css], font_config=font_config, pdf_variant="pdf/ua-1")

def _get_marker_models():
    for name in["load_all_models", "load_models", "create_model_dict"]:
        if name in dir(marker.models): return getattr(marker.models, name)()
    raise ImportError("Keine Lade-Funktion in marker.models gefunden.")

def _init_marker():
    global m_path
    logger.info(f"🤖 Lade KI-Modelle in den Arbeitsspeicher (Cache: {m_path})...")
    return PdfConverter(artifact_dict=_get_marker_models())

class AIEngine:
    _instance = None
    def __init__(self):
        self.converter = _init_marker()
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            logger.info("🚀 Lade AIEngine Singleton...")
            cls._instance = cls()
        return cls._instance

def improve_with_marker(input_path, output_path):
    original_docinfo = {}
    try:
        with pikepdf.open(input_path) as orig_pdf:
            if "/Info" in orig_pdf.trailer:
                for k, v in orig_pdf.docinfo.items(): original_docinfo[k] = str(v)
    except Exception: pass

    try:
        start_time = time.time()
        logger.info(f"✨ Modus: KI-Rekonstruktion ({os.path.basename(input_path)})")
        
        converter = AIEngine.get_instance().converter
        
        logger.info("🤖 Stage 2: KI-Textextraktion gestartet.")
        rendered = converter(input_path)
        md_content = rendered.markdown
        images_dict = getattr(rendered, "images", {})

        doc_lang = "de-DE"
        if hasattr(rendered, "metadata") and rendered.metadata:
            meta_lang = rendered.metadata.get("language")
            if meta_lang and len(meta_lang) >= 2:
                doc_lang = meta_lang if "-" in meta_lang else f"{meta_lang}-DE"

        logger.info("🤖 Stage 2.5: Strukturoptimierung...")
        md_content = guess_and_fix_structure(md_content, images_dict)

        logger.info(f"🤖 Stage 3: Erstelle echtes PDF/UA-1 ({doc_lang})...")
        html_text = markdown.markdown(md_content, extensions=["tables"])
        title_text = str(original_docinfo.get("/Title", "")).strip() or "Barrierefreies Dokument"

        _save_to_pdf(html_text, output_path, doc_lang, title_text)
        _apply_pdfua_metadata(output_path, original_docinfo, doc_lang)

        proc_time = time.time() - start_time
        
        # =========================================================
        # ECHTE VERAPDF PRÜFUNG (anstatt leerer Behauptungen!)
        # =========================================================
        verapdf_cmd = shutil.which("verapdf")
        if not verapdf_cmd and os.name == 'nt':
            verapdf_cmd = shutil.which("verapdf.bat")
            
        if verapdf_cmd:
            try:
                v_res = subprocess.run([verapdf_cmd, "--version"], capture_output=True, text=True, timeout=10)
                v_version = v_res.stdout.strip().splitlines()[0] if v_res.stdout else "Unbekannte Version"
                logger.info(f"🔍 Prüfe PDF/UA-1 Konformität mit {v_version}...")
                
                c_res = subprocess.run([verapdf_cmd, "--flavour", "ua1", "--format", "text", output_path], capture_output=True, text=True, timeout=120)
                v_out = c_res.stdout.strip().replace(output_path, os.path.basename(output_path))
                
                if "PASS" in v_out:
                    logger.info(f"✅ Fertig nach {proc_time:.1f}s – ERFOLG: PDF ist veraPDF-konform!")
                    logger.info(f"--- VeraPDF Report ---\n{v_out}\n----------------------")
                else:
                    logger.warning(f"⚠️ Fertig nach {proc_time:.1f}s – FEHLSCHLAG: PDF/UA-1 Fehler gefunden!")
                    logger.warning(f"--- VeraPDF Report ---\n{v_out}\n----------------------")
            except Exception as e:
                logger.warning(f"⚠️ Konnte VeraPDF nicht ausführen: {e}")
                logger.info(f"✅ Fertig nach {proc_time:.1f}s (ohne Check).")
        else:
            logger.info(f"✅ Fertig nach {proc_time:.1f}s. (Hinweis: 'verapdf' ist lokal nicht installiert, Check übersprungen).")

        del rendered
        gc.collect()
        return True
    except Exception as err:
        logger.error(f"❌ KI-Fehler: {err}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF A11y Converter - Standalone")
    parser.add_argument("input", help="Pfad zum Eingabe-PDF")
    parser.add_argument("output", help="Pfad zum Ausgabe-PDF")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Eingabedatei nicht gefunden: {args.input}")
        exit(1)
        
    improve_with_marker(args.input, args.output)
