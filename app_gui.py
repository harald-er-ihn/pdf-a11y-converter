#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Barriereoptimierte GUI für den PDF A11y Converter.
Implementiert saubere Threading-Isolation (ThreadPoolExecutor) und
nutzt das Facade-Pattern (ConverterService) zur strikten Trennung
von UI und Business Logic.
"""
# pylint: disable=wrong-import-position, invalid-name, broad-exception-caught

import os
import sys
import platform

# 🚀 GTK3 Runtime + Strikte Warnungs-Unterdrückung für Windows (GUI-Spezifisch)
if platform.system().lower() == "windows":
    BASE_PATH = getattr(sys, "_MEIPASS", os.path.abspath("."))
    gtk3_bin = os.path.join(BASE_PATH, "gtk3", "bin")

    if os.path.exists(gtk3_bin):
        os.environ["PATH"] = gtk3_bin + os.pathsep + os.environ.get("PATH", "")
        os.environ["GIO_USE_VFS"] = "local"
        os.environ["GIO_MODULE_DIR"] = " "
        os.environ["G_MESSAGES_DEBUG"] = "none"

        fc_path = os.path.join(BASE_PATH, "gtk3", "etc", "fonts")
        if os.path.exists(fc_path):
            fc_path_unix = fc_path.replace("\\", "/")
            os.environ["FONTCONFIG_PATH"] = fc_path_unix

            fonts_conf = os.path.join(fc_path, "fonts.conf")
            if not os.path.exists(fonts_conf):
                try:
                    with open(fonts_conf, "w", encoding="utf-8") as f:
                        f.write(
                            '<?xml version="1.0"?><fontconfig>'
                            "<dir>C:/Windows/Fonts</dir></fontconfig>"
                        )
                except Exception:
                    pass

            os.environ["FONTCONFIG_FILE"] = fc_path_unix + "/fonts.conf"

        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(gtk3_bin)
            except Exception:
                pass


import logging
import multiprocessing
import subprocess
import webbrowser
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk
from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

# 🚀 FIX: Korrekter Import-Pfad (Application Layer) & Multi-Line (PEP 8 / E501)
from src.application.converter_service import ConverterService, ConversionResult
from src.config import get_worker_python
from src.vsr_generator import generate_physical_vsr


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def get_resource_path(relative_path: str) -> str:
    """Ermittelt den absoluten Pfad zur Ressource (auch im PyInstaller Bundle)."""
    app_base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(app_base_path, relative_path)


class TextboxHandler(logging.Handler):
    """
    Leitet Logging-Nachrichten thread-sicher in das GUI-Textfeld weiter.
    Ersetzt das fehleranfällige und blockierende sys.stdout Hijacking.
    """

    def __init__(self, textbox: ctk.CTkTextbox, master_app: ctk.CTk) -> None:
        super().__init__()
        self.textbox = textbox
        self.app = master_app

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        # after(0, ...) ist die einzig thread-sichere Methode für Tkinter-Updates
        self.app.after(0, self._append_text, msg)

    def _append_text(self, msg: str) -> None:
        self.textbox.configure(state="normal")
        if self.textbox.get("end-2c", "end-1c") != "\n":
            self.textbox.insert("end-1c", "\n")
        self.textbox.insert("end-1c", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")
        self.app.update_idletasks()


class CustomTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
    """Fassade für Drag & Drop Funktionalität in CustomTkinter."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tkdnd_version = TkinterDnD._require(self)


# pylint: disable=too-many-ancestors, too-many-instance-attributes
class App(CustomTkDnD):
    """Haupt-GUI-Klasse. Agiert als reiner View & Controller."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PDF A11y Converter")
        self.geometry("800x800")
        self.minsize(650, 700)

        self.selected_file: Optional[Path] = None
        self.converted_output_path: Optional[Path] = None
        self.is_processing: bool = False

        # Sicherer Thread-Pool für Hintergrundaufgaben
        self.executor = ThreadPoolExecutor(max_workers=2)

        self._build_ui()
        self._setup_logging()
        self.info_button.focus_set()

    def _setup_logging(self) -> None:
        """Initialisiert das lokale Logging ins UI-Textfeld."""
        logger = logging.getLogger("pdf-converter")
        logger.setLevel(logging.INFO)

        # Vorherige Handler entfernen (verhindert doppelte Logs)
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        handler = TextboxHandler(self.log_textbox, self)
        fmt = logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S")
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    def _build_ui(self) -> None:
        """Erzeugt alle UI-Elemente."""
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
        """Füllt ein statisches Text-Tab aus einer Datei."""
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

    def _get_hardware_info(self) -> str:
        """Ermittelt Hardware-Daten isoliert (via Worker)."""
        cpu_name = platform.processor() or "Unbekannte CPU"
        cores = multiprocessing.cpu_count()
        has_gpu, gpu_name = False, ""

        try:
            py_exe = get_worker_python("vision_worker")
            script = (
                "import torch; print(torch.cuda.is_available()); "
                "print(torch.cuda.get_device_name(0) "
                "if torch.cuda.is_available() else '')"
            )
            res = subprocess.run(
                [str(py_exe), "-c", script], capture_output=True, text=True, timeout=10
            )
            output = res.stdout.strip().split("\n")

            if output and output[0] == "True":
                has_gpu = True
                gpu_name = output[1] if len(output) > 1 else "Unbekannte GPU"
        except Exception:
            pass

        if has_gpu:
            return f"✅ GPU aktiv: {gpu_name}\n🖥️ CPU: {cpu_name} ({cores} Kerne)"
        return f"❌ Keine GPU (CPU-Modus).\n🖥️ CPU: {cpu_name} ({cores} Kerne)"

    def _populate_hw_tab(self, tab: ctk.CTkFrame) -> None:
        """Füllt den Hardware-Tab asynchron mit Daten."""
        textbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(fill="both", expand=True, padx=5, pady=5)
        textbox.insert("1.0", "Ermittle Hardware-Infos...\nBitte warten.")
        textbox.configure(state="disabled")

        def _apply_text(text: str) -> None:
            textbox.configure(state="normal")
            textbox.delete("1.0", "end")
            textbox.insert("1.0", text)
            textbox.configure(state="disabled")

        def _update_info() -> None:
            info = self._get_hardware_info()
            self.after(0, _apply_text, info)

        self.executor.submit(_update_info)

    def open_about_window(self) -> None:
        about_win = ctk.CTkToplevel(self)
        about_win.title("Dokumentation & Hilfe")
        about_win.geometry("850x650")
        about_win.resizable(True, True)

        tabview = ctk.CTkTabview(about_win)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._populate_tab(
            tabview.add("Über"), "static/docs/about.txt", "PDF A11y Converter"
        )
        self._populate_tab(tabview.add("README"), "README.md", "README fehlt.")
        self._populate_tab(
            tabview.add("Architektur"), "ARCHITECTURE.md", "Architektur fehlt."
        )
        self._populate_tab(
            tabview.add("Lizenzen"), "static/docs/licenses.txt", "Lizenzen fehlen."
        )
        self._populate_hw_tab(tabview.add("Hardware"))

    def browse_file(self, _event: Any = None) -> None:
        if not self.is_processing:
            path = filedialog.askopenfilename(filetypes=[("PDF Dateien", "*.pdf")])
            if path:
                self._set_file(path)

    def handle_drop(self, event: Any) -> None:
        if not self.is_processing:
            self._set_file(event.data.strip("{}"))

    def _set_file(self, path: str) -> None:
        if not path.lower().endswith(".pdf"):
            messagebox.showerror("Fehler", "Bitte eine PDF-Datei wählen.")
            return

        self.selected_file = Path(path)
        self.start_button.configure(state="normal")
        self.status_label.configure(
            text=f"Ausgewählt: {self.selected_file.name}", text_color="green"
        )
        self.converted_output_path = None

    def start_conversion(self) -> None:
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

        out_path = self.selected_file.with_name(f"{self.selected_file.stem}_pdfua.pdf")

        # Sichere Entkopplung an ThreadPoolExecutor (Vermeidet GIL/GUI Blockierung)
        future = self.executor.submit(
            self._run_conversion_task, self.selected_file, out_path
        )
        future.add_done_callback(self._on_conversion_done)

    def _run_conversion_task(self, in_path: Path, out_path: Path) -> ConversionResult:
        """Hintergrund-Task: Ruft den Application Service auf."""
        service = ConverterService()
        return service.convert(in_path, out_path)

    def _on_conversion_done(self, future: Future) -> None:
        """Wird aufgerufen, wenn der Konvertierungsprozess endet."""
        try:
            result: ConversionResult = future.result()
            self.after(0, self._finish_ui_update, result)
        except Exception as e:
            err_result = ConversionResult(success=False, error_message=str(e))
            self.after(0, self._finish_ui_update, err_result)

    def _finish_ui_update(self, result: ConversionResult) -> None:
        """Aktualisiert die UI sicher im Haupt-Thread."""
        self.is_processing = False
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.start_button.configure(state="normal")
        self.vsr_button.configure(state="normal")

        if result.success and result.output_path:
            self.converted_output_path = result.output_path
            self.status_label.configure(
                text=f"Erfolgreich: {result.output_path.name}", text_color="green"
            )
        else:
            self.status_label.configure(
                text=f"Fehler: {result.error_message}", text_color="red"
            )

    def show_visual_screenreader(self) -> None:
        if self.is_processing:
            messagebox.showinfo("Info", "Konvertierung läuft noch...")
            return

        target_pdf = None
        if self.converted_output_path and self.converted_output_path.exists():
            target_pdf = self.converted_output_path
        elif self.selected_file and self.selected_file.exists():
            target_pdf = self.selected_file
        else:
            messagebox.showwarning("Fehlt", "Bitte zuerst ein PDF auswählen.")
            return

        self.executor.submit(self._run_vsr_task, target_pdf)

    def _run_vsr_task(self, pdf_path: Path) -> None:
        """Generiert den VSR im Hintergrund."""
        logger = logging.getLogger("pdf-converter")
        self.after(0, lambda: self.vsr_button.configure(state="disabled"))

        try:
            logger.info("📄 Analysiere physischen Tag-Baum von %s...", pdf_path.name)
            vsr_html = pdf_path.with_suffix(".visualscreenreader.html")
            success = generate_physical_vsr(pdf_path, vsr_html)

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

    # 🚀 NEU: Enterprise Bootstrap Loader triggern
    from src.runtime_bootstrap import ensure_runtime

    ensure_runtime()

    master_app = App()
    master_app.mainloop()
