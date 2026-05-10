"""Módulo responsable de filtrar el contenido interno de archivos ZIP.

Soporta dos modos de filtrado:
- 'parte': conserva solo extensiones permitidas (ej: .xls, .xlsx, .xlsm, .csv).
- 'general': elimina extensiones prohibidas (ej: videos, mensajes de correo).

El proceso usa un directorio temporal para no dejar artefactos en disco
si algo falla durante la extracción o recompresión.
"""

import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from app.config_models import ZipPolicy
from app.exceptions import FileProcessingError

logger = logging.getLogger(__name__)

FilterMode = Literal["parte", "general"]


class ZipContentFilter:
    """Filtra el contenido interno de un ZIP según la política configurada."""

    def __init__(self, policy: ZipPolicy):
        self._policy = policy
        self._compiled_parte_patterns = tuple(
            re.compile(pattern) for pattern in policy.parte_detection_patterns
        )

    def es_parte(self, original_filename: str) -> bool:
        """Devuelve True si el nombre del archivo contiene una referencia PARTE.

        Evalúa el stem normalizado (mayúsculas, espacios reemplazados por _)
        para ser consistente con la detección de StripParteStrategy.
        """

        stem = Path(original_filename).stem.upper().replace(" ", "_").replace("-", "_")
        tokens = [t for t in stem.split("_") if t]

        for i, token in enumerate(tokens):
            for pattern in self._compiled_parte_patterns:
                if pattern.fullmatch(token):
                    return True
            if i > 0:
                pair = f"{tokens[i - 1]}_{token}"
                for pattern in self._compiled_parte_patterns:
                    if pattern.fullmatch(pair):
                        return True
        return False

    def filter_zip(self, zip_path: Path, mode: FilterMode, dry_run: bool = False) -> None:
        """Filtra el contenido del ZIP en función del modo indicado.

        En modo 'parte': conserva solo las extensiones en parte_keep_extensions.
        En modo 'general': elimina las extensiones en general_remove_extensions.

        En dry_run=True solo registra en log qué archivos se eliminarían,
        sin extraer, filtrar ni recomprimir nada.

        Si el ZIP está corrupto o protegido con contraseña, registra el error
        y deja el archivo en origen sin modificar.
        """

        if not zipfile.is_zipfile(zip_path):
            logger.warning(
                "El archivo no es un ZIP válido o está corrupto, se deja en origen: %s",
                zip_path.name,
            )
            return

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                entries = zf.infolist()
                to_remove = self._entries_to_remove(entries, mode)

                if not to_remove:
                    logger.debug(
                        "ZIP sin archivos a eliminar en modo '%s': %s", mode, zip_path.name
                    )
                    return

                if dry_run:
                    names = [e.filename for e in to_remove]
                    logger.info(
                        "[DRY-RUN] ZIP %s (%s): se eliminarían %d archivo(s) internos: %s",
                        zip_path.name,
                        mode,
                        len(names),
                        ", ".join(names),
                    )
                    return

                self._repack_zip(zip_path, zf, entries, to_remove)

        except zipfile.BadZipFile:
            logger.warning(
                "ZIP corrupto o protegido con contraseña, se deja en origen: %s", zip_path.name
            )
        except Exception as exc:
            raise FileProcessingError(
                f"Error inesperado al filtrar el ZIP '{zip_path.name}': {exc}"
            ) from exc

    # ---------------------------------------------------------------------------
    # Métodos internos
    # ---------------------------------------------------------------------------

    def _entries_to_remove(
        self, entries: list[zipfile.ZipInfo], mode: FilterMode
    ) -> list[zipfile.ZipInfo]:
        """Devuelve la lista de entradas del ZIP que deben eliminarse."""

        result = []
        for entry in entries:
            if entry.is_dir():
                continue

            ext = Path(entry.filename).suffix.lower()

            if mode == "parte":
                if ext not in self._policy.parte_keep_extensions:
                    result.append(entry)
            else:
                if ext in self._policy.general_remove_extensions:
                    result.append(entry)

        return result

    def _repack_zip(
        self,
        zip_path: Path,
        original_zf: zipfile.ZipFile,
        all_entries: list[zipfile.ZipInfo],
        to_remove: list[zipfile.ZipInfo],
    ) -> None:
        """Reempaqueta el ZIP conservando solo las entradas que no deben eliminarse.

        Los archivos se escriben aplanados en la raíz del ZIP, eliminando
        cualquier subcarpeta interna. Así un archivo como:
            'SOL_RL03423040_23941949_PARTE_1/datos.csv'
        queda simplemente como:
            'datos.csv'
        """

        remove_names = {entry.filename for entry in to_remove}
        # Excluye directorios y entradas marcadas para eliminar
        keep_entries = [
            e for e in all_entries
            if e.filename not in remove_names and not e.is_dir()
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip_path = Path(tmp_dir) / zip_path.name

            with zipfile.ZipFile(tmp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as new_zf:
                for entry in keep_entries:
                    data = original_zf.read(entry.filename)
                    # Aplana la ruta: usa solo el nombre del archivo sin subcarpetas
                    flat_name = Path(entry.filename).name
                    new_zf.writestr(flat_name, data)

            shutil.move(str(tmp_zip_path), str(zip_path))

        logger.debug(
            "ZIP reempaquetado: %s (%d eliminado(s), %d conservado(s))",
            zip_path.name,
            len(to_remove),
            len(keep_entries),
        )
