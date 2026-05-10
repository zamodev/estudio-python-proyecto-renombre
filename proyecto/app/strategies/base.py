"""Interfaz base para todas las estrategias de transformación de archivos."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import FileContext


class FileStrategy(ABC):
    """Contrato para cada estrategia dentro del canal de procesamiento."""

    @abstractmethod
    def apply(self, context: FileContext) -> FileContext:
        """Transforma o valida el contexto actual del archivo."""

        pass
