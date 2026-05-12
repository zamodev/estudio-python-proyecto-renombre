"""Registro en memoria de archivos despachados a la carpeta destino.

Cuando el pipeline mueve un archivo a destino, lo registra aquí.
Cuando el RPA lo elimina de destino, DestinationWatcher llama a confirm()
y esta clase escribe la línea de confirmación en el reporte TXT.
"""

from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_NA = "N/D"


def _fmt_size(size_bytes: Optional[int]) -> str:
    """Convierte bytes a una cadena legible (KB, MB, GB)."""

    if size_bytes is None:
        return _NA

    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if size_bytes >= threshold:
            return f"{size_bytes / threshold:.2f} {unit}"

    return f"{size_bytes} B"


def _fmt_free(destination_path: Path) -> str:
    """Devuelve el espacio libre actual en la partición de destination_path."""

    try:
        usage = shutil.disk_usage(destination_path)
        return _fmt_size(usage.free)
    except OSError:
        return _NA


@dataclass
class _DispatchEntry:
    """Datos registrados al momento de despachar un archivo."""

    size_bytes: Optional[int]
    sent_at: datetime


class DispatchRegistry:
    """Registro thread-safe de archivos despachados a una carpeta destino.

    Parameters
    ----------
    destination_path:
        Carpeta destino que el RPA consume. Se usa para calcular espacio libre.
    report_path:
        Ruta del archivo TXT donde se escriben las líneas de confirmación.
    """

    def __init__(self, destination_path: str, report_path: str) -> None:
        self._destination_path = Path(destination_path)
        self._report_path = Path(report_path)
        self._entries: dict[str, _DispatchEntry] = {}
        self._lock = threading.Lock()

        self._report_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def register(self, filename: str, size_bytes: Optional[int]) -> None:
        """Registra un archivo recién movido a la carpeta destino."""

        with self._lock:
            self._entries[filename] = _DispatchEntry(
                size_bytes=size_bytes,
                sent_at=datetime.now(),
            )

        logger.debug("Registrado en despacho: %s (%s)", filename, _fmt_size(size_bytes))

    def confirm(self, filename: str) -> None:
        """Confirma que el RPA eliminó el archivo y escribe la línea de reporte."""

        confirmed_at = datetime.now()

        with self._lock:
            entry = self._entries.pop(filename, None)

        size_str = _fmt_size(entry.size_bytes if entry else None)
        sent_str = entry.sent_at.strftime("%H:%M:%S") if entry else _NA
        confirmed_str = confirmed_at.strftime("%H:%M:%S")
        free_str = _fmt_free(self._destination_path)
        date_str = confirmed_at.strftime("%Y-%m-%d")

        line = (
            f"{date_str} {confirmed_str}"
            f" | {filename}"
            f" | {size_str}"
            f" | enviado: {sent_str}"
            f" | confirmado: {confirmed_str}"
            f" | libre en destino: {free_str}"
        )

        self._write_line(line)
        logger.info("Confirmado por RPA: %s", line)

    # ------------------------------------------------------------------
    # Escritura del reporte
    # ------------------------------------------------------------------

    def _write_line(self, line: str) -> None:
        """Agrega una línea al reporte TXT de forma segura."""

        try:
            with self._report_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.error("No se pudo escribir en el reporte '%s': %s", self._report_path, exc)
