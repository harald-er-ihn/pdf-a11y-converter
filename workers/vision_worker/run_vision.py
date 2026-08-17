# workers/vision_worker/run_vision.py
# PDF A11y Converter - Vision Worker
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Bildbeschreibung.

Strategie:
1. Für texttragende Bilder zuerst lokale OCR mit Tesseract.
2. OCR-Text normalisieren und offensichtliche Signaturen nicht als Text übernehmen.
3. BLIP nur als Fallback verwenden, wenn OCR keinen brauchbaren Text liefert.

100% Offline: Gibt klare Fehlermeldungen zurück, falls Modelle fehlen.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 🚀 OFFLINE-MODE ERZWINGEN
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

PROJECT_ROOT = WORKER_ROOT.parent
LOCAL_MODEL_DIR = PROJECT_ROOT / "resources" / "models" / "blip"

from common import (
    cleanup_memory,
    configure_torch_runtime,
    setup_worker_logging,
    write_error_contract,
)

logger = setup_worker_logging("vision-worker")
configure_torch_runtime()

import torch
from PIL import Image, ImageEnhance, ImageOps
from transformers import BlipForConditionalGeneration, BlipProcessor


OCR_LANG = "deu+eng"
OCR_PSM = "6"


def _preprocess_for_ocr(pil_img: Image.Image) -> Image.Image:
    """
    Robuste Vorverarbeitung für kleine Logos/Textgrafiken:
    - RGB/Alpha vereinheitlichen
    - 4x Upscaling
    - Graustufen
    - Autokontrast
    - Kontrastverstärkung
    """
    img = pil_img.convert("RGB")

    w, h = img.size
    if w > 0 and h > 0:
        img = img.resize((w * 4, h * 4), Image.Resampling.LANCZOS)

    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return img


def _run_tesseract_ocr(pil_img: Image.Image) -> str:
    """
    Führt Tesseract per CLI aus, damit keine zusätzliche Python-Abhängigkeit
    wie pytesseract erforderlich ist.
    """
    if not shutil.which("tesseract"):
        logger.warning("Tesseract nicht gefunden; OCR wird übersprungen.")
        return ""

    ocr_img = _preprocess_for_ocr(pil_img)

    with tempfile.TemporaryDirectory(prefix="pdf_a11y_ocr_") as tmpdir:
        tmp_path = Path(tmpdir) / "ocr_input.png"
        ocr_img.save(tmp_path)

        cmd = [
            "tesseract",
            str(tmp_path),
            "stdout",
            "-l",
            OCR_LANG,
            "--psm",
            OCR_PSM,
        ]

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Tesseract OCR Timeout.")
            return ""

        if proc.returncode != 0:
            logger.warning(
                "Tesseract OCR fehlgeschlagen: %s", proc.stderr.strip()
            )
            return ""

        return proc.stdout or ""


def _normalize_ocr_text(text: str) -> str:
    """
    Normalisiert OCR-Ausgaben vorsichtig.

    Wichtig: Keine aggressive semantische Korrektur.
    Ziel ist nur, typische OCR-Artefakte zu entfernen und Lesbarkeit zu erhöhen.
    """
    if not text:
        return ""

    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("|", " ")
    text = text.replace("—", "-")
    text = text.replace("–", "-")
    text = text.replace("ﬁ", "fi")
    text = text.replace("ﬂ", "fl")

    # Zeilenumbrüche als Trenner erhalten, aber leere Zeilen entfernen.
    lines = []
    for line in text.splitlines():
        line = line.strip()
        line = re.sub(r"\s+", " ", line)

        # Reine Symbol-/Artefakt-Zeilen entfernen.
        if not re.search(r"[A-Za-zÄÖÜäöüß0-9]", line):
            continue

        # Häufige führende OCR-Artefakte entfernen.
        line = re.sub(r"^[^\wÄÖÜäöüß]+", "", line)
        line = re.sub(r"[^\wÄÖÜäöüß.,;:!?()/%&+\- ]+$", "", line)

        if line:
            lines.append(line)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()

    # Häufige OCR-Verwechslungen aus deutschem Kontext.
    replacements = {
        "Munchen": "München",
        "Miinchen": "München",
        "Muenchen": "München",
        "fiir": "für",
        "fur": "für",
        "Okoprofit": "ÖKOPROFIT",
        "OKOPROFIT": "ÖKOPROFIT",
        "OEKOPROFIT": "ÖKOPROFIT",
    }
    for wrong, right in replacements.items():
        text = re.sub(
            rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE
        )

    # Führende OCR-Artefakte vor starken Schlüsselwörtern entfernen.
    # Beispiele:
    #   "A =? ÖKOPROFIT München 2022" -> "ÖKOPROFIT München 2022"
    #   "Lj Landeshauptstadt München ..." -> "Landeshauptstadt München ..."
    strong_markers = [
        "ÖKOPROFIT",
        "Landeshauptstadt",
        "Referat",
        "CIB",
        "Münchener",
        "München",
    ]
    for marker in strong_markers:
        m = re.search(rf"\b{re.escape(marker)}\b", text, flags=re.IGNORECASE)
        if m and 0 < m.start() <= 18:
            prefix = text[: m.start()].strip()
            prefix_words = re.findall(r"[A-Za-zÄÖÜäöüß0-9]+", prefix)

            # Nur sehr kurze Rauschpräfixe entfernen, keine echten Wörter wie "Logo".
            if (
                len(prefix_words) <= 2
                and not re.search(r"\d", prefix)
                and all(len(w) <= 2 for w in prefix_words)
            ):
                text = text[m.start() :].strip()
            break

    # Mehrfache Satzzeichen/Sonderzeichen reduzieren.
    text = re.sub(r"([,;:])\1+", r"\1", text)
    text = re.sub(r"\s+([,;:!?])", r"\1", text)

    return text.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zÄÖÜäöüß0-9]+", text or ""))


def _looks_like_signature_ocr(text: str) -> bool:
    """
    Heuristik: Signaturen/Unterschriften sollen nicht als normaler OCR-Text
    in den Alt-Text übernommen werden.

    Wir klassifizieren sehr kurze, personen-/handschriftartige OCR-Ergebnisse
    ohne Organisations-/Sachkontext und ohne Zahlen eher als Signatur.
    """
    if not text:
        return False

    t = text.strip()
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", t)
    has_digit = bool(re.search(r"\d", t))

    context_keywords = {
        "stadt",
        "landeshauptstadt",
        "münchen",
        "munchen",
        "referat",
        "arbeit",
        "wirtschaft",
        "klima",
        "umwelt",
        "umweltschutz",
        "ökoprofit",
        "oekoprofit",
        "zertifikat",
        "logo",
        "gmbh",
        "ag",
        "ev",
        "e.v",
        "universität",
        "university",
        "tu",
    }

    lower = t.lower()
    has_context = any(k in lower for k in context_keywords)

    if has_context or has_digit:
        return False

    # Sehr kurze OCR-Ergebnisse sind bei Signaturen häufig falsch-positive Namen.
    if 1 <= len(words) <= 3:
        # Beispiele: "Max Mustermann", "C Baumgartner", "Dr Huber"
        title_like = {"dr", "prof", "herr", "frau"}
        non_title_words = [
            w for w in words if w.lower().strip(".") not in title_like
        ]

        if 1 <= len(non_title_words) <= 2:
            return True

    # Kaum alphanumerischer Inhalt, aber OCR hat irgendetwas erkannt.
    alnum = re.findall(r"[A-Za-zÄÖÜäöüß0-9]", t)
    if len(alnum) < 6 and _word_count(t) <= 2:
        return True

    return False


def _is_useful_ocr_text(text: str) -> bool:
    """
    Entscheidet, ob OCR-Text stark genug ist, um BLIP zu ersetzen.
    """
    if not text:
        return False

    if _looks_like_signature_ocr(text):
        return False

    wc = _word_count(text)
    has_digit = bool(re.search(r"\d", text))
    has_umlaut_or_german_context = bool(
        re.search(
            r"Ä|Ö|Ü|ä|ö|ü|ß|München|Referat|Landeshauptstadt|ÖKOPROFIT|Zertifikat",
            text,
            flags=re.IGNORECASE,
        )
    )

    # Kurze Logos mit Jahreszahl sind gültig, z.B. "ÖKOPROFIT München 2022".
    if wc >= 2 and has_digit:
        return True

    # Organisations-/Behördentexte.
    if wc >= 3 and has_umlaut_or_german_context:
        return True

    # Allgemeiner längerer Text.
    if wc >= 5:
        return True

    return False


def _make_alt_text_from_ocr(text: str) -> str:
    """
    Alt-Text für texttragende Bilder.
    Kurz und klar, ohne zu behaupten, es sei zwingend ein Logo.
    """
    return f"Text im Bild: {text}"


def _generate_blip_alt_text(
    pil_img: Image.Image,
    processor: BlipProcessor,
    model: BlipForConditionalGeneration,
    device: str,
) -> str:
    inputs = processor(pil_img.convert("RGB"), return_tensors="pt").to(device)

    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=40)

    alt_text = processor.decode(output[0], skip_special_tokens=True).strip()
    if not alt_text:
        return "Bild"

    return alt_text.capitalize()


def main() -> None:
    parser = argparse.ArgumentParser(description="Vision Worker")
    parser.add_argument("--input", required=True, help="JSON mit Bild-Pfaden")
    parser.add_argument(
        "--output", required=True, help="Ausgabe-JSON für Alt-Texte"
    )
    args = parser.parse_args()

    input_json = Path(args.input)
    output_json = Path(args.output)

    if not input_json.exists():
        logger.error("Eingabedatei nicht gefunden: %s", input_json)
        sys.exit(1)

    with open(input_json, "r", encoding="utf-8") as f:
        images_dict = json.load(f)

    logger.info(
        "🤖 Lade Vision-Experten lokal. OCR zuerst, BLIP als Fallback: %s",
        LOCAL_MODEL_DIR.name,
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ARCHITEKTUR-FIX: Actionable Error Message für 100% Offline-Betrieb
    if not LOCAL_MODEL_DIR.exists():
        msg = (
            f"Lokales Modell fehlt in {LOCAL_MODEL_DIR}. "
            "Bitte fuehre 'python tools/download_models.py' aus, "
            "um die benoetigten Offline-Modelle herunterzuladen."
        )
        logger.error("❌ %s", msg)
        write_error_contract(output_json, "ModelNotFound", msg)
        sys.exit(1)

    model = None
    processor = None

    try:
        processor = BlipProcessor.from_pretrained(
            str(LOCAL_MODEL_DIR), local_files_only=True
        )
        model = (
            BlipForConditionalGeneration.from_pretrained(
                str(LOCAL_MODEL_DIR), local_files_only=True
            )
            .to(device)
            .eval()
        )

        results = {}

        for img_name, img_path_str in images_dict.items():
            img_path = Path(img_path_str)
            if not img_path.exists():
                results[img_name] = "Bild"
                continue

            with Image.open(img_path) as pil_img:
                pil_img = pil_img.convert("RGB")

                raw_ocr = _run_tesseract_ocr(pil_img)
                ocr_text = _normalize_ocr_text(raw_ocr)

                if _is_useful_ocr_text(ocr_text):
                    alt_text = _make_alt_text_from_ocr(ocr_text)
                    logger.info("OCR genutzt für %s: %s", img_name, ocr_text)
                elif _looks_like_signature_ocr(ocr_text):
                    alt_text = "Unterschrift"
                    logger.info(
                        "OCR als Signatur verworfen für %s: %s",
                        img_name,
                        ocr_text,
                    )
                else:
                    alt_text = _generate_blip_alt_text(
                        pil_img=pil_img,
                        processor=processor,
                        model=model,
                        device=device,
                    )
                    logger.info(
                        "BLIP-Fallback genutzt für %s. OCR war: %r",
                        img_name,
                        ocr_text,
                    )

                results[img_name] = alt_text

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("✅ Vision-Extraktion erfolgreich abgeschlossen.")

    except Exception as e:
        if "OutOfMemoryError" in type(e).__name__:
            write_error_contract(
                output_json,
                "OutOfMemory",
                "Grafikkartenspeicher (VRAM) ist voll.",
            )
        else:
            write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)
    finally:
        del model
        del processor
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
