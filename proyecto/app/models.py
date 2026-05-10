from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ProcessingStatus(str, Enum):
    """Estados posibles del procesamiento de un archivo."""

    PENDING = "PENDING"
    VALID = "VALID"
    AUTO_FIXED = "AUTO_FIXED"
    REJECTED = "REJECTED"


@dataclass
class FileContext:
    """Estado mutable del archivo a lo largo del pipeline de estrategias."""

    source_path: Path
    filename: str
    stem: str
    suffix: str
    original_filename: str
    original_stem: str
    tokens: list[str] = field(default_factory=list)
    document_type: Optional[str] = None
    rub: Optional[str] = None
    cedula: Optional[str] = None
    canonical_filename: Optional[str] = None
    fixes_applied: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    status: ProcessingStatus = ProcessingStatus.PENDING
    is_parte: bool = False

    @classmethod
    def from_path(cls, path: Path) -> "FileContext":
        """Construye el contexto inicial a partir de una ruta de archivo."""

        return cls(
            source_path=path,
            filename=path.name,
            stem=path.stem,
            suffix=path.suffix.lower(),
            original_filename=path.name,
            original_stem=path.stem,
        )

    def update_filename(self, new_filename: str) -> None:
        """Actualiza el nombre actual y recalcula nombre base y extensión."""

        self.filename = new_filename
        self.stem = Path(new_filename).stem
        self.suffix = Path(new_filename).suffix.lower()

    def update_tokens(self, tokens: list[str]) -> None:
        """Reemplaza los tokens actuales y sincroniza el nombre base."""

        self.tokens = [token for token in tokens if token]
        self.stem = "_".join(self.tokens)
        self.filename = f"{self.stem}{self.suffix}"

    def add_fix(self, message: str) -> None:
        """Registra una corrección aplicada si todavía no fue registrada."""

        if message not in self.fixes_applied:
            self.fixes_applied.append(message)

    def add_error(self, message: str) -> None:
        """Registra un error de validación si todavía no existe."""

        if message not in self.validation_errors:
            self.validation_errors.append(message)

    def clear_errors(self) -> None:
        """Limpia los errores de validación acumulados."""

        self.validation_errors.clear()

    def mark_valid(self) -> None:
        """Marca el archivo como válido o autocorregido según los cambios aplicados."""

        self.status = ProcessingStatus.AUTO_FIXED if self.has_changes else ProcessingStatus.VALID

    def mark_rejected(self, message: Optional[str] = None) -> None:
        """Marca el archivo como rechazado y, opcionalmente, agrega el motivo."""

        if message:
            self.add_error(message)
        self.status = ProcessingStatus.REJECTED

    @property
    def has_changes(self) -> bool:
        """Indica si el nombre actual difiere del original o se aplicaron fixes."""

        return self.filename != self.original_filename or bool(self.fixes_applied)
