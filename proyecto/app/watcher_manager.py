"""Administrador del ciclo de vida de uno o varios watchers de directorio."""

from __future__ import annotations

import logging
import time

from app.watcher import DirectoryWatcher

logger = logging.getLogger(__name__)


class WatcherManager:
    """Inicia, detiene y mantiene activos varios watchers."""

    def __init__(self, watchers: list[DirectoryWatcher]):
        self.watchers = watchers

    def start(self) -> None:
        """Inicia todos los watchers configurados."""

        for watcher in self.watchers:
            watcher.start()

    def stop(self) -> None:
        """Detiene todos los watchers configurados."""

        for watcher in self.watchers:
            watcher.stop()

    def run_forever(self) -> None:
        """Mantiene el proceso vivo hasta que el usuario lo interrumpe."""

        self.start()
        logger.info("Monitoreando %d carpeta(s).", len(self.watchers))

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Deteniendo monitoreo...")
        finally:
            self.stop()
