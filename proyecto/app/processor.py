"""Canal de procesamiento de archivos: valida, renombra y mueve archivos."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Optional

from app.config_models import RuleProfile
from app.exceptions import FileProcessingError
from app.models import FileContext, ProcessingStatus
from app.registry import build_strategy
from app.zip_content_filter import ZipContentFilter

logger = logging.getLogger(__name__)


class FileProcessor:
    """Aplica una cadena de estrategias a un archivo y lo mueve a su destino."""

    def __init__(
        self,
        destination_path: str,
        strategies_config: list[dict],
        rule_profile: Optional[RuleProfile] = None,
        dry_run: bool = False,
    ):
        self.destination_path = Path(destination_path)
        self.rule_profile = rule_profile
        self.dry_run = dry_run
        self.strategies = [build_strategy(cfg, rule_profile=rule_profile) for cfg in strategies_config]
        self._processing_lock = threading.Lock()
        self._processing_paths: set[str] = set()
        self._zip_filter: Optional[ZipContentFilter] = (
            ZipContentFilter(rule_profile.zip_policy)
            if rule_profile and rule_profile.zip_policy
            else None
        )

        if not self.dry_run:
            self.destination_path.mkdir(parents=True, exist_ok=True)

    def process(self, file_path: str) -> None:
        """Procesa un archivo y lo mueve al destino configurado."""

        path = Path(file_path)

        if not path.exists() or not path.is_file():
            logger.debug("Se omite porque no es un archivo válido: %s", path)
            return

        processing_key = str(path.resolve()).lower()
        with self._processing_lock:
            if processing_key in self._processing_paths:
                logger.debug("Se omite el reprocesamiento concurrente de: %s", path)
                return
            self._processing_paths.add(processing_key)

        try:
            context = FileContext.from_path(path)

            for strategy in self.strategies:
                context = strategy.apply(context)

            if context.status == ProcessingStatus.REJECTED:
                logger.warning(
                    "Archivo rechazado y conservado en origen: %s. Motivos: %s",
                    context.original_filename,
                    "; ".join(context.validation_errors) or "Sin detalle.",
                )
                return

            if self.dry_run:
                final_destination_path = self.destination_path / context.filename
                if self._zip_filter and context.suffix == ".zip":
                    mode = "parte" if context.is_parte else "general"
                    self._zip_filter.filter_zip(context.source_path, mode=mode, dry_run=True)
                if context.status == ProcessingStatus.AUTO_FIXED:
                    logger.info(
                        "[DRY-RUN] Se movería con fixes a: %s. Fixes: %s",
                        final_destination_path,
                        "; ".join(context.fixes_applied) or "Sin detalle.",
                    )
                else:
                    logger.info("[DRY-RUN] Se movería a: %s", final_destination_path)
                return

            if self._zip_filter and context.suffix == ".zip":
                mode = "parte" if context.is_parte else "general"
                self._zip_filter.filter_zip(context.source_path, mode=mode, dry_run=False)

            final_source_path = self._rename_if_needed(context)
            final_destination_path = self.destination_path / context.filename

            shutil.move(str(final_source_path), str(final_destination_path))
            if context.status == ProcessingStatus.AUTO_FIXED:
                logger.info(
                    "Archivo corregido y movido a: %s. Fixes: %s",
                    final_destination_path,
                    "; ".join(context.fixes_applied) or "Sin detalle.",
                )
            else:
                logger.info("Archivo movido a: %s", final_destination_path)
        except FileProcessingError:
            raise
        except Exception as exc:
            raise FileProcessingError(f"No se pudo procesar '{path.name}': {exc}") from exc
        finally:
            with self._processing_lock:
                self._processing_paths.discard(processing_key)

    def _rename_if_needed(self, context: FileContext) -> Path:
        """Renombra el archivo solo si la cadena de estrategias cambió su nombre."""

        current_path = context.source_path
        desired_path = current_path.parent / context.filename

        if current_path.name != context.filename:
            try:
                current_path.rename(desired_path)
            except OSError as exc:
                raise FileProcessingError(
                    f"No se pudo renombrar '{current_path.name}' a '{context.filename}'."
                ) from exc
            context.source_path = desired_path
            logger.debug("Archivo renombrado a: %s", desired_path.name)

        return context.source_path

