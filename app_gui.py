#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Barriereoptimierte GUI für den PDF A11y Converter.
Implementiert saubere Threading-Isolation, Stream-Redirection
und eine responsive CustomTkinter Oberfläche.
"""

import logging
import multiprocessing
import os
import platform
import subprocess
import sys
import threading
import warnings
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk
from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

# Backend-Importe
from src.application.orchestrator import extract_to_spatial
from src.infrastructure.pdf.generator import generate_pdf_from_spatial
from src.infrastructure.validation.validation import check_verapdf, get_verapdf_version
from src.config import get_worker_python
from src.vsr_generator import generate_physical_vsr

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", message=".*urllib3.*")

# 🚀 FIX: Unterdrückt lästige GTK/GLib C-Level Warnungen auf Windows
os.environ["GIO_USE_VFS"] = "local"
os.environ["GLIB_LOG_LEVEL"] = "4"

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def get_resource_path(relative_path: str) -> str:
    """
    Ermittelt den absoluten Pfad zur Ressource.
    Berücksichtigt das PyInstaller _MEIPASS Verzeichnis.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


class TextboxHandler(logging.Handler):
    """Leitet Logging-Nachrichten in das GUI-Textfeld weiter."""

    def __init__(self, textbox: ctk.CTkTextbox, master_app: ctk.CTk) -> None:
        super().__init__()
        self.textbox = textbox
        self.app = master_app

    def emit(self, record: logging.LogRecord) -> None:
        """Übergibt den Log-Record an den Main-Thread."""
        msg = self.format(record)
        self.app.after(0, self._append_text, msg)

    def _append_text(self, msg: str) -> None:
        """Fügt den Text thread-sicher in die Textbox ein."""
        self.textbox.configure(state="normal")
        if self.textbox.get("end-2c", "end-1c") != "\n":
            self.textbox.insert("end-1c", "\n")
        self.textbox.insert("end-1c", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")
        self.app.update_idletasks()


class StreamRedirector:
    """Fängt stdout/stderr ab und sendet sie an die GUI."""

    def __init__(self, textbox: ctk.CTkTextbox, master_app: ctk.CTk) -> None:
        self.textbox = textbox
        self.app = master_app

    def write(self, text: str) -> None:
        """Schreibt den Stream-Input in die GUI."""
        if text:
            self.app.after(0, self._gui_write, text)

    def _gui_write(self, text: str) -> None:
        """Thread-sicheres Schreiben in das UI-Element."""
        self.textbox.configure(state="normal")
        if "\r" in text:
            valid_text = text.split("\r")[-1].strip()
            if valid_text:
                self.textbox.delete("end-1c linestart", "end-1c")
                self.textbox.insert("end-1c", valid_text)
        else:
            self.textbox.insert("end-1c", text)

        self.textbox.see("end")
        self.textbox.configure(state="disabled")
        self.app.update_idletasks()

    def flush(self) -> None:
        """Erforderlich für das Stream-Interface."""


class CustomTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
    """Fassade für Drag & Drop Funktionalität in CustomTkinter."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tkdnd_version = TkinterDnD._require(self)


# pylint: disable=too-many-ancestors
class App(CustomTkDnD):
    """Haupt-GUI-Klasse des PDF A11y Converters."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PDF A11y Converter")
        self.geometry("800x800")
        self.minsize(650, 700)

        self.selected_file: Optional[str] = None
        self.is_processing: bool = False
        self._verapdf_version_logged: bool = False
        self.converted_output_path: Optional[str] = None

        self._build_ui()
        self._setup_logging()
        self.info_button.focus_set()

    def _setup_logging(self) -> None:
        """Konfiguriert das systemweite Logging für die GUI."""
        logger = logging.getLogger("pdf-converter")
        logger.setLevel(logging.INFO)
        handler = TextboxHandler(self.log_textbox, self)
        fmt = logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S")
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        sys.stdout = StreamRedirector(self.log_textbox, self)  # type: ignore
        sys.stderr = StreamRedirector(self.log_textbox, self)  # type: ignore

    def _build_ui(self) -> None:
        """Baut die visuelle Struktur der Anwendung auf."""
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(10, 0))

        try:
            logo_path = get_resource_path("static/img/AccessibilityMatters.png")
            if os.path.exists(logo_path):
                logo_img = ctk.CTkImage(Image.open(logo_path), size=(159, 120))
                self.logo_label = ctk.CTkLabel(
                    self.header_frame, text="", image=logo_img
                )
                self.logo_label.pack(side="left", padx=(0, 10))
        except Exception:
            pass

        btn_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        btn_frame.pack(side="right", fill="y")

        self.info_button = ctk.CTkButton(
            btn_frame, text="Über / Hilfe", width=140, command=self.open_about_window
        )
        self.vsr_button = ctk.CTkButton(
            btn_frame,
            text="👁️ Visual Screenreader",
            width=160,
            command=self.show_visual_screenreader,
        )

        self.info_button.pack(side="right", padx=(10, 0))
        self.vsr_button.pack(side="right", padx=(10, 0))

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="PDF A11y Converter",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        self.title_label.pack(pady=(5, 10))

        self.drop_frame = ctk.CTkFrame(
            self.main_frame, width=450, height=140, border_width=2
        )
        self.drop_frame.pack(pady=10)
        self.drop_frame.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame, text="📄 PDF hier ablegen", font=ctk.CTkFont(size=15)
        )
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        self.drop_frame.bind("<Button-1>", self.browse_file)
        self.drop_label.bind("<Button-1>", self.browse_file)
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.handle_drop)

        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="Keine Datei ausgewählt.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.pack(pady=10)

        self.progressbar = ctk.CTkProgressBar(
            self.main_frame, mode="indeterminate", width=400
        )

        self.start_button = ctk.CTkButton(
            self.main_frame,
            text="PDF konvertieren",
            command=self.start_conversion,
            state="disabled",
            width=250,
            height=50,
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.start_button.pack(pady=15)

        self.log_textbox = ctk.CTkTextbox(
            self.main_frame, height=180, font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.log_textbox.pack(fill="both", expand=True, pady=(0, 10))

    def _populate_tab(self, tab: ctk.CTkFrame, path: str, fallback: str) -> None:
        """Lädt eine Textdatei in einen Tabview-Reiter."""
        textbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(fill="both", expand=True, padx=5, pady=5)
        content = fallback
        full_path = get_resource_path(path)

        if not os.path.exists(full_path):
            full_path = os.path.join(os.path.abspath("."), path)

        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"Fehler beim Laden: {e}"

        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

    def _populate_hardware_tab(self, tab: ctk.CTkFrame) -> None:
        """Startet den Hardware-Check im Hintergrund und aktualisiert das Tab."""
        textbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(fill="both", expand=True, padx=5, pady=5)
        textbox.insert("1.0", "Prüfe Hardware-Komponenten...\nBitte warten.")
        textbox.configure(state="disabled")

        threading.Thread(
            target=self._run_hw_check_thread, args=(textbox,), daemon=True
        ).start()

    def _run_hw_check_thread(self, textbox: ctk.CTkTextbox) -> None:
        """Führt den eigentlichen Hardware-Check über das Worker-Venv aus."""
        cpu_name = platform.processor() or "Unbekannte CPU"
        cores = multiprocessing.cpu_count()
        has_gpu, gpu_name = False, ""

        try:
            py_exe = get_worker_python("vision_worker")
            script = (
                "import torch; "
                "print(torch.cuda.is_available()); "
                "print(torch.cuda.get_device_name(0) "
                "if torch.cuda.is_available() else '')"
            )

            # 🚀 FIX: Isoliere die Umgebung, damit PyInstaller's PYTHONPATH
            # den Subprozess (das Venv) nicht korrumpiert! (Behebt Code 103)
            env = os.environ.copy()
            env.pop("PYTHONHOME", None)
            env.pop("PYTHONPATH", None)

            res = subprocess.run(
                [str(py_exe), "-c", script],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            output = res.stdout.strip().split("\n")

            if output and output[0] == "True":
                has_gpu = True
                gpu_name = output[1] if len(output) > 1 else "Unbekannte GPU"
        except Exception:
            pass

        if has_gpu:
            msg = (
                f"✅ Grafikkarte (GPU) aktiv: {gpu_name}\n"
                f"🖥️ CPU: {cpu_name} ({cores} Kerne)"
            )
        else:
            msg = f"❌ Keine GPU (CPU-Modus).\n🖥️ CPU: {cpu_name} ({cores} Kerne)"

        self.after(0, lambda: self._update_hw_textbox(textbox, msg))

    def _update_hw_textbox(self, textbox: ctk.CTkTextbox, msg: str) -> None:
        """Aktualisiert die Textbox im GUI-Thread."""
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", msg)
        textbox.configure(state="disabled")

    def open_about_window(self) -> None:
        """Zeigt die Dokumentationen im Tabview-Pattern an."""
        about_win = ctk.CTkToplevel(self)
        about_win.title("Dokumentation & Hilfe")
        about_win.geometry("850x650")
        about_win.resizable(True, True)

        # 🚀 FIX: Zwingt das Fenster garantiert vor das Hauptfenster!
        about_win.attributes("-topmost", True)
        about_win.after(150, lambda: about_win.attributes("-topmost", False))
        about_win.focus_force()

        tabview = ctk.CTkTabview(about_win)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._populate_tab(
            tabview.add("Über"), "static/docs/about.txt", "PDF A11y Converter"
        )
        self._populate_hardware_tab(tabview.add("Hardware"))
        self._populate_tab(tabview.add("README"), "README.md", "README nicht gefunden.")
        self._populate_tab(
            tabview.add("Architektur"), "ARCHITECTURE.md", "Architektur fehlt."
        )
        self._populate_tab(
            tabview.add("Lizenzen"), "static/docs/licenses.txt", "Lizenzen fehlen."
        )

    def browse_file(self, _event: Any = None) -> None:
        """Öffnet den File-Picker Dialog."""
        if not self.is_processing:
            path = filedialog.askopenfilename(filetypes=[("PDF Dateien", "*.pdf")])
            if path:
                self._set_file(path)

    def handle_drop(self, event: Any) -> None:
        """Behandelt das Drag & Drop Event."""
        if not self.is_processing:
            self._set_file(event.data.strip("{}"))

    def _set_file(self, path: str) -> None:
        """Setzt die ausgewählte Datei und resettet den Zustand."""
        if not path.lower().endswith(".pdf"):
            messagebox.showerror("Fehler", "Bitte eine PDF-Datei wählen.")
            return
        self.selected_file = path
        self.start_button.configure(state="normal")
        self.status_label.configure(
            text=f"Ausgewählt: {os.path.basename(path)}", text_color="green"
        )
        self.converted_output_path = None

    def start_conversion(self) -> None:
        """Startet den Thread für die Konvertierung."""
        if not self.selected_file:
            return

        self.is_processing = True
        self.start_button.configure(state="disabled")
        self.vsr_button.configure(state="disabled")
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
        self.progressbar.pack(before=self.start_button)
        self.progressbar.start()

        threading.Thread(target=self._run_phase_1, args=(self.selected_file,)).start()

    def _run_phase_1(self, input_path: str) -> None:
        """Führt die Datenextraktion und Preflight-Analyse durch."""
        logger = logging.getLogger("pdf-converter")
        if not self._verapdf_version_logged:
            logger.info("🛠️ Validierungs-Software: %s", get_verapdf_version())
            self._verapdf_version_logged = True

        logger.info("🔍 Prüfe Original-PDF (%s)...", os.path.basename(input_path))

        initial_check = check_verapdf(input_path, is_final=False)
        if initial_check.get("passed", False):
            logger.info("🟢 Original-PDF ist bereits konform.")
        else:
            logger.info("🔴 Original-PDF ist NICHT barrierefrei.")

        try:
            spatial_dom, images, doc_lang, docinfo = extract_to_spatial(input_path)
            self._run_phase_3(spatial_dom, images, doc_lang, docinfo)
        except Exception as e:
            logger.error("Fehler in Phase 1: %s", e)
            self.after(0, self._cancel_process, "Fehler bei der Extraktion.")

    def _run_phase_3(
        self, spatial_dom: dict, images: dict, doc_lang: str, docinfo: dict
    ) -> None:
        """Generiert das finale PDF und validiert es."""
        if not self.selected_file:
            return

        base, ext = os.path.splitext(self.selected_file)
        output_path = f"{base}_pdfua{ext}"
        try:
            success = generate_pdf_from_spatial(
                spatial_dom, self.selected_file, images, output_path, docinfo, doc_lang
            )
            if success:
                self.converted_output_path = output_path
            self.after(0, self._finish, success, output_path)
        except Exception as e:
            logging.getLogger("pdf-converter").error("Fehler Phase 3: %s", e)
            self.after(0, self._finish, False, str(e))

    def _cancel_process(self, msg: str) -> None:
        """Bricht den GUI-Zustand sauber ab."""
        self.is_processing = False
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.start_button.configure(state="normal")
        self.vsr_button.configure(state="normal")
        self.status_label.configure(text=msg, text_color="orange")

    def _finish(self, success: bool, output_path: str) -> None:
        """Schließt die Konvertierung in der GUI ab."""
        self.is_processing = False
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.start_button.configure(state="normal")
        self.vsr_button.configure(state="normal")
        if success:
            self.status_label.configure(
                text=f"Erfolgreich: {os.path.basename(output_path)}", text_color="green"
            )
        else:
            self.status_label.configure(text="Fehler", text_color="red")

    def show_visual_screenreader(self) -> None:
        """Startet den Visual Screenreader Workflow."""
        if self.is_processing:
            messagebox.showinfo("Info", "Konvertierung läuft noch...")
            return

        target_pdf = None
        if self.converted_output_path and os.path.exists(self.converted_output_path):
            target_pdf = self.converted_output_path
        elif self.selected_file and os.path.exists(self.selected_file):
            target_pdf = self.selected_file
        else:
            messagebox.showwarning("Fehlt", "Bitte zuerst ein PDF auswählen.")
            return

        threading.Thread(target=self._run_vsr_thread, args=(target_pdf,)).start()

    def _run_vsr_thread(self, pdf_path: str) -> None:
        """Führt das physische VSR Parsing im Hintergrund aus."""
        logger = logging.getLogger("pdf-converter")
        self.after(0, lambda: self.vsr_button.configure(state="disabled"))

        try:
            p_path = Path(pdf_path)
            logger.info("📄 Analysiere physischen Tag-Baum von %s...", p_path.name)

            vsr_html = p_path.with_suffix(".visualscreenreader.html")

            success = generate_physical_vsr(p_path, vsr_html)

            if success:
                self.after(0, lambda: webbrowser.open(f"file://{vsr_html.absolute()}"))
                logger.info("👁️ Visual Screenreader geöffnet: %s", vsr_html.name)
            else:
                msg = (
                    "Dieses PDF enthält keine Struktur-Tags (StructTreeRoot fehlt).\n"
                    "Der Screenreader würde dieses Dokument als komplett leer vorlesen!"
                )
                logger.warning(msg.replace("\n", " "))
                self.after(0, lambda: messagebox.showwarning("Keine Tags", msg))

        except Exception as e:
            logger.error("Fehler bei VSR-Erstellung: %s", e)
            err_msg = str(e)
            self.after(
                0, lambda: messagebox.showerror("Fehler", f"VSR Fehler: {err_msg}")
            )

        finally:
            self.after(0, lambda: self.vsr_button.configure(state="normal"))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    master_app = App()
    master_app.mainloop()
