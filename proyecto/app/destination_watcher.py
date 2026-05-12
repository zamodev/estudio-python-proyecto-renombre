"""Watcher sobre la carpeta destino para detectar cuando el RPA elimina archivos."""

from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.dispatch_registry import DispatchRegistry

logger = logging.getLogger(__name__)


class _DeletionHandler(FileSystemEventHandler):
    """Reacciona a eliminaciones en la carpeta destino."""

    def __init__(self, registry: DispatchRegistry) -> None:
        self._registry = registry

    def on_deleted(self, event):
        if event.is_directory:
            return

        filename = Path(event.src_path).name
        logger.debug("Eliminación detectada en destino: %s", filename)
        self._registry.confirm(filename)


class DestinationWatcher:
    """Vigila la carpeta destino y notifica al DispatchRegistry cuando el RPA elimina archivos.

    Parameters
    ----------
    name:
        Nombre identificador del watcher (para logs).
    destination_path:
        Carpeta destino que el RPA consume.
    registry:
        Registro de despacho compartido con el FileProcessor correspondiente.
    """

    def __init__(self, name: str, destination_path: str, registry: DispatchRegistry) -> None:
        self.name = name
        self._destination_path = Path(destination_path)
        self._destination_path.mkdir(parents=True, exist_ok=True)
        self._registry = registry
        self._observer = Observer()
        self._handler = _DeletionHandler(registry=self._registry)

    def start(self) -> None:
        """Inicia la observación de la carpeta destino."""

        self._observer.schedule(self._handler, str(self._destination_path), recursive=False)
        self._observer.start()
        logger.info("[%s] Vigilando eliminaciones en destino: %s", self.name, self._destination_path)

    def stop(self) -> None:
        """Detiene la observación de la carpeta destino."""

        self._observer.stop()
        self._observer.join()
