# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
import logging
import os
import platform
import tarfile
import urllib.request
import zipfile
from src.config import get_model_cache_dir

logger = logging.getLogger("pdf-converter")


def get_java_paths():
    """
    Sucht Java. Findet es keines im Cache, wird ein portables Open-Source
    JRE 21 in den Modell-Cache heruntergeladen.
    Rückgabe: (Pfad_zur_java_exe, Pfad_zum_JAVA_HOME)
    """
    cache_dir = get_model_cache_dir()
    jre_dir = cache_dir / "jre"

    system = platform.system().lower()
    exe_name = "java.exe" if system == "windows" else "java"

    # 1. Prüfe, ob wir es schon heruntergeladen haben
    if jre_dir.exists():
        for path in jre_dir.rglob(exe_name):
            if path.is_file() and "bin" in path.parts:
                return str(path), str(path.parent.parent)

    # 2. Nicht gefunden -> Automatisch herunterladen!
    logger.info("☕ Java (JRE) wird für veraPDF heruntergeladen (einmalig)...")

    api_os = (
        "windows" if system == "windows" else ("mac" if system == "darwin" else "linux")
    )
    arch = platform.machine().lower()
    api_arch = (
        "x64"
        if arch in ["x86_64", "amd64"]
        else ("aarch64" if arch in ["arm64", "aarch64"] else None)
    )

    if not api_arch:
        logger.error("❌ Architektur %s nicht unterstützt für auto-JRE.", arch)
        return None, None

    url = f"https://api.adoptium.net/v3/binary/latest/21/ga/{api_os}/{api_arch}/jre/hotspot/normal/eclipse"
    jre_dir.mkdir(parents=True, exist_ok=True)
    download_path = jre_dir / ("jre.zip" if system == "windows" else "jre.tar.gz")

    try:
        urllib.request.urlretrieve(url, download_path)
        logger.info("📦 Entpacke Java Runtime...")
        if system == "windows":
            with zipfile.ZipFile(download_path, "r") as zip_ref:
                zip_ref.extractall(jre_dir)
        else:
            with tarfile.open(download_path, "r:gz") as tar_ref:
                tar_ref.extractall(jre_dir)
        download_path.unlink()

        for path in jre_dir.rglob(exe_name):
            if path.is_file() and "bin" in path.parts:
                if system != "windows":
                    os.chmod(path, 0o755)
                logger.info("✅ Java JRE erfolgreich bereitgestellt!")
                return str(path), str(path.parent.parent)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fehler beim Java-Download: %s", e)
        return None, None

    return None, None
