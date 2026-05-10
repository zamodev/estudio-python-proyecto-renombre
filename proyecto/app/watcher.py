"""Integración con Watchdog para carpetas y archivos entrantes."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.exceptions import FileProcessingError, FileStabilityError
from app.processor import FileProcessor

logger = logging.getLogger(__name__)


class FileHandler(FileSystemEventHandler):
    """Convierte eventos del sistema de archivos en operaciones de procesamiento."""

    def __init__(self, processor: FileProcessor, stable_wait_seconds: int = 1, stability_checks: int = 3):
        self.processor = processor
        self.stable_wait_seconds = stable_wait_seconds
        self.stability_checks = stability_checks

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self._handle_file(Path(event.dest_path))

    def _handle_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            return

        try:
            if not self._wait_until_stable(file_path):
                raise FileStabilityError(f"El archivo no se estabilizó a tiempo: {file_path.name}")

            self.processor.process(str(file_path))
        except (FileProcessingError, FileStabilityError) as exc:
            logger.exception("No se pudo procesar %s: %s", file_path.name, exc)
        except Exception as exc:
            logger.exception("Error inesperado al procesar %s: %s", file_path.name, exc)

    def _wait_until_stable(self, file_path: Path) -> bool:
        """Espera hasta que el tamaño del archivo deje de cambiar antes de procesarlo."""

        previous_size = -1

        for _ in range(self.stability_checks):
            if not file_path.exists():
                return False

            current_size = file_path.stat().st_size

            if current_size == previous_size:
                return True

            previous_size = current_size
            time.sleep(self.stable_wait_seconds)

        return False


class DirectoryWatcher:
    """Vigila una carpeta y procesa archivos usando un canal dedicado."""

    def __init__(
        self,
        name: str,
        watch_path: str,
        processor: FileProcessor,
        process_existing_on_startup: bool = True,
        recursive: bool = False,
        stable_wait_seconds: int = 1,
        stability_checks: int = 3,
    ):
        self.name = name
        self.watch_path = Path(watch_path)
        self.watch_path.mkdir(parents=True, exist_ok=True)
        self.processor = processor
        self.process_existing_on_startup = process_existing_on_startup
        self.recursive = recursive
        self.stable_wait_seconds = stable_wait_seconds
        self.stability_checks = stability_checks
        self.observer = Observer()
        self._handler = FileHandler(
            processor=self.processor,
            stable_wait_seconds=self.stable_wait_seconds,
            stability_checks=self.stability_checks,
        )

    def start(self):
        """Inicia la observación del directorio."""

        self.observer.schedule(self._handler, str(self.watch_path), recursive=self.recursive)
        
        if self.process_existing_on_startup:
            self.scan_existing_files()

        self.observer.start()

        logger.info("[%s] Monitoreando carpeta: %s", self.name, self.watch_path)

    def stop(self):
        """Detiene la observación del directorio."""

        self.observer.stop()
        self.observer.join()

    def scan_existing_files(self):
        """Procesa los archivos ya presentes cuando arranca el watcher."""

        logger.info("[%s] Escaneando archivos existentes en: %s", self.name, self.watch_path)

        paths = self.watch_path.rglob("*") if self.recursive else self.watch_path.iterdir()

        for path in paths:
            if path.is_file():
                try:
                    self.processor.process(str(path))
                except Exception as exc:
                    logger.exception("[%s] No se pudo procesar %s: %s", self.name, path.name, exc)
