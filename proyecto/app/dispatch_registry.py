"""Registro en memoria de archivos despachados a la carpeta destino.

Cuando el pipeline mueve un archivo a destino, lo registra aquí.
Cuando el RPA lo elimina de destino, DestinationWatcher llama a confirm()
y esta clase escribe la línea de confirmación en el reporte TXT.
"""

from __future__ import annotations

import os
import logging
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from app.config_models import ReportRetentionPolicy

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

    def __init__(
        self,
        destination_path: str,
        report_path: str,
        retention_policy: Optional[ReportRetentionPolicy] = None,
    ) -> None:
        self._destination_path = Path(destination_path)
        self._report_path = Path(report_path)
        self._retention_policy = retention_policy if retention_policy and retention_policy.enabled else None
        self._entries: dict[str, _DispatchEntry] = {}
        self._lock = threading.Lock()
        self._retention_stop_event = threading.Event()
        self._retention_thread: Optional[threading.Thread] = None

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
        date_str = confirmed_at.strftime("%Y-%m-%d")

        line = (
            f"{date_str}"
            f" | {confirmed_str}"
            f" | {filename}"
            f" | enviado: {sent_str}"
            f" | confirmado: {confirmed_str}"
            f" | peso: {size_str}"
        )

        self._write_line(line)
        logger.info("Confirmado por RPA: %s", line)

    def start_retention(self) -> None:
        """Inicia la depuración automática del reporte si existe una política activa."""

        if self._retention_policy is None:
            return

        if self._retention_thread and self._retention_thread.is_alive():
            return

        if self._retention_policy.cleanup_on_startup:
            self.cleanup_expired_entries()

        self._retention_stop_event.clear()
        self._retention_thread = threading.Thread(
            target=self._retention_loop,
            name=f"report-retention-{self._report_path.stem}",
            daemon=True,
        )
        self._retention_thread.start()

    def stop_retention(self) -> None:
        """Detiene la depuración automática del reporte."""

        if self._retention_thread is None:
            return

        self._retention_stop_event.set()
        self._retention_thread.join(timeout=5)
        self._retention_thread = None

    def cleanup_expired_entries(self) -> bool:
        """Elimina del TXT las líneas con más de N días de antigüedad.

        Devuelve True si se reescribió el archivo.
        """

        if self._retention_policy is None:
            return False

        cutoff_date = date.today() - timedelta(days=self._retention_policy.retention_days)

        with self._lock:
            if not self._report_path.exists():
                return False

            try:
                lines = self._report_path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                logger.error("No se pudo leer el reporte '%s': %s", self._report_path, exc)
                return False

            kept_lines: list[str] = []
            removed_count = 0

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                line_date = self._parse_line_date(line)
                if line_date is None:
                    if self._retention_policy.keep_unparseable_lines:
                        kept_lines.append(raw_line)
                    else:
                        removed_count += 1
                    continue

                if line_date >= cutoff_date:
                    kept_lines.append(raw_line)
                else:
                    removed_count += 1

            if removed_count == 0:
                return False

            self._atomic_write_lines(kept_lines)

        logger.info(
            "Reporte depurado: %s línea(s) eliminada(s) de '%s'.",
            removed_count,
            self._report_path,
        )
        return True

    # ------------------------------------------------------------------
    # Escritura del reporte
    # ------------------------------------------------------------------

    def _write_line(self, line: str) -> None:
        """Agrega una línea al reporte TXT de forma segura."""

        with self._lock:
            try:
                with self._report_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as exc:
                logger.error("No se pudo escribir en el reporte '%s': %s", self._report_path, exc)

    def _retention_loop(self) -> None:
        """Bucle en segundo plano que ejecuta la depuración periódica."""

        if self._retention_policy is None:
            return

        interval_seconds = self._retention_policy.cleanup_interval_minutes * 60
        while not self._retention_stop_event.wait(interval_seconds):
            self.cleanup_expired_entries()

    def _parse_line_date(self, line: str) -> Optional[date]:
        """Extrae la fecha de una línea del reporte si sigue el formato esperado."""

        date_token = line.split("|", 1)[0].strip()
        try:
            return datetime.strptime(date_token, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _atomic_write_lines(self, lines: list[str]) -> None:
        """Reescribe el reporte usando un archivo temporal y reemplazo atómico."""

        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self._report_path.parent),
                prefix=f".{self._report_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                for line in lines:
                    temp_file.write(line + "\n")

            os.replace(temp_path, self._report_path)
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
