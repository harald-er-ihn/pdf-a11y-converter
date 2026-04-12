# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
PDF/UA-1 und WCAG Validierung mit integrierter veraPDF-Instanz.
Nutzt Pydantic für strikte Datenverträge und dynamische Pfad-Auflösung.
Liest Master-Profile (XML) aus der config.json.
"""

import json
import logging
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from src.config import get_resource_path
from src.infrastructure.validation.verapdf_manager import get_verapdf_path

logger = logging.getLogger("pdf-converter")


class RuleSummary(BaseModel):
    clause: str = "Unbekannt"
    description: str = "Keine Beschreibung"
    failedChecks: int = 0


class ValidationDetails(BaseModel):
    failedRules: int = 0
    ruleSummaries: List[RuleSummary] = Field(default_factory=list)


class VeraValidationResult(BaseModel):
    compliant: bool = False
    details: Optional[ValidationDetails] = None


class ItemDetails(BaseModel):
    name: str = ""


class Job(BaseModel):
    itemDetails: Optional[ItemDetails] = None
    validationResult: List[VeraValidationResult] = Field(default_factory=list)


class Report(BaseModel):
    jobs: List[Job] = Field(default_factory=list)
    processingErrors: List[Dict] = Field(default_factory=list)


class VeraPDFResponse(BaseModel):
    report: Optional[Report] = None


@dataclass
class ValidationResult:
    """Strukturiertes Ergebnis für unser Hauptprogramm."""

    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    report: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "errors": self.errors, "report": self.report}


class VeraPDFValidator:
    """Kapselt den nativen, offline veraPDF-Validator plattformunabhängig."""

    def __init__(self) -> None:
        self.base_dir = get_resource_path("resources")
        self.system = platform.system().lower()
        self.java_cmd = self._get_java_path()

        script_path = get_verapdf_path()
        self.verapdf_home = (
            Path(script_path).parent if script_path else self.base_dir / "verapdf"
        )
        self.classpath = self._build_classpath()
        self.main_class = "org.verapdf.apps.GreenfieldCliWrapper"

    def _get_java_path(self) -> Path:
        exe_name = "java.exe" if self.system == "windows" else "java"
        os_folder = "macos" if self.system == "darwin" else self.system
        jre_dir = self.base_dir / os_folder / "jre"

        if jre_dir.exists():
            for p in jre_dir.rglob(exe_name):
                if "bin" in p.parts:
                    return p
        return Path(exe_name)

    def _build_classpath(self) -> str:
        bin_dir = self.verapdf_home / "bin"
        jars = list(bin_dir.glob("greenfield-apps-*.jar"))
        return (
            str(jars[0])
            if jars
            else str(self.base_dir / "verapdf" / "bin" / "greenfield-apps-1.28.2.jar")
        )

    def get_configured_profiles(self) -> Dict[str, Path]:
        config_path = get_resource_path("config/config.json")
        profiles = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg_profiles = json.load(f).get("verapdf_profiles", {})
                    for key, rel_path in cfg_profiles.items():
                        res_path = get_resource_path(rel_path)
                        if res_path.exists():
                            profiles[key] = res_path
            except Exception as e:
                logger.warning("Fehler config.json: %s", e)
        return profiles

    def is_available(self) -> bool:
        return self.java_cmd.exists()

    def _parse_validation_json(
        self, json_str: str, result: ValidationResult
    ) -> ValidationResult:
        try:
            vera_data = VeraPDFResponse.model_validate_json(json_str)
            result.report = vera_data.model_dump()
        except ValidationError as e:
            logger.debug("veraPDF JSON Parse Error:\n%s", e)
            result.errors.append("veraPDF Antwort ungültig.")
            return result

        if not vera_data.report or not vera_data.report.jobs:
            if vera_data.report and vera_data.report.processingErrors:
                for err in vera_data.report.processingErrors:
                    result.errors.append(f"Verarbeitungsfehler: {err}")
            else:
                result.errors.append("Kein Validierungsjob im Report gefunden.")
            return result

        job = vera_data.report.jobs[0]
        if not job.validationResult:
            result.errors.append("PDF konnte nicht validiert werden.")
            return result

        val_res = job.validationResult[0]
        result.passed = val_res.compliant

        if not result.passed and val_res.details:
            for rule in val_res.details.ruleSummaries:
                if rule.failedChecks > 0:
                    result.errors.append(f"Regel {rule.clause}: {rule.description}")

        return result

    def _execute_verapdf(
        self, cmd: List[str], result: ValidationResult
    ) -> ValidationResult:
        """Kapselt den Subprocess-Aufruf."""
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
            if proc.stderr.strip() and "Exception" not in proc.stderr:
                result.warnings.extend(
                    [line for line in proc.stderr.strip().splitlines() if line]
                )

            start_idx = proc.stdout.find("{")
            if start_idx == -1:
                result.errors.append("Keine JSON-Antwort von veraPDF.")
                return result

            return self._parse_validation_json(proc.stdout[start_idx:], result)

        except subprocess.TimeoutExpired:
            result.errors.append("veraPDF Timeout überschritten.")
            return result
        except Exception as e:
            result.errors.append(f"Systemfehler: {str(e)}")
            return result

    def validate(
        self,
        pdf_path: Union[str, Path],
        flavour: Optional[str] = None,
        profile_path: Optional[Path] = None,
    ) -> ValidationResult:
        """Erzeugt den veraPDF Command-String und initiiert die Validierung."""
        pdf_path = Path(pdf_path)
        result = ValidationResult(passed=False)

        if not pdf_path.exists() or not self.is_available():
            result.errors.append("PDF oder Java fehlt!")
            return result

        cmd = [
            str(self.java_cmd),
            "-Dfile.encoding=UTF8",
            "-XX:+IgnoreUnrecognizedVMOptions",
            f"-Dapp.home={self.verapdf_home}",
            f"-Dbasedir={self.verapdf_home}",
            "--add-exports=java.base/sun.security.pkcs=ALL-UNNAMED",
            "-cp",
            self.classpath,
            self.main_class,
        ]

        if profile_path:
            cmd.extend(["--profile", str(profile_path)])
        else:
            cmd.extend(["--flavour", flavour or "ua1"])

        cmd.extend(["--format", "json", str(pdf_path)])

        return self._execute_verapdf(cmd, result)

    def get_version(self) -> str:
        if not self.is_available():
            return "veraPDF nicht verfügbar"
        try:
            cmd = [
                str(self.java_cmd),
                "-Dfile.encoding=UTF8",
                f"-Dapp.home={self.verapdf_home}",
                f"-Dbasedir={self.verapdf_home}",
                "--add-exports=java.base/sun.security.pkcs=ALL-UNNAMED",
                "-cp",
                self.classpath,
                self.main_class,
                "--version",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return res.stdout.strip().split("\n")[0]
        except Exception as e:
            logger.debug("Konnte veraPDF-Version nicht abrufen: %s", e)
            return "veraPDF Version unbekannt"


_validator = VeraPDFValidator()


def check_verapdf(pdf_path: Union[str, Path], is_final: bool = False) -> dict:
    phase = "Endabnahme" if is_final else "Eingangsprüfung"
    logger.info("🔍 %s für '%s' mit veraPDF...", phase, Path(pdf_path).name)

    profiles = _validator.get_configured_profiles()
    res_ua1 = (
        _validator.validate(pdf_path, profile_path=profiles.get("PDFUA-1"))
        if "PDFUA-1" in profiles
        else _validator.validate(pdf_path, flavour="ua1")
    )

    if res_ua1.passed:
        logger.info("🟢 PASS: Dokument ist veraPDF-konform (PDF/UA-1)!")
    else:
        logger.warning("🔴 FAIL: veraPDF meldet Fehler bei PDF/UA-1!")
        for err in res_ua1.errors[:10]:
            logger.warning("   -> %s", err)

    wcag_profile = profiles.get("WCAG_2_2")
    if wcag_profile:
        res_wcag = _validator.validate(pdf_path, profile_path=wcag_profile)
        if res_wcag.passed:
            logger.info("🟢 PASS: Dokument ist veraPDF-konform (WCAG 2.2)!")
        else:
            logger.warning("🔴 FAIL: veraPDF meldet Fehler bei WCAG 2.2!")
            for err in res_wcag.errors[:10]:
                logger.warning("   -> %s", err)

    return res_ua1.to_dict()


def get_verapdf_version() -> str:
    return _validator.get_version()
