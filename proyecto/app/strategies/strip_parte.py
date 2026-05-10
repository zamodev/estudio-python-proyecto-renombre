"""Estrategia que detecta y elimina referencias PARTE del nombre de archivos ZIP."""

from __future__ import annotations

import re
from typing import Optional

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class StripParteStrategy(FileStrategy):
    """Elimina sufijos PARTE del stem de archivos ZIP antes del análisis documental.

    Solo actúa sobre archivos .zip que tengan zip_policy configurada.
    Detecta tokens PARTE usando los patrones definidos en zip_policy.json
    y trunca el stem desde el primer token PARTE en adelante.

    Ejemplo:
        ASEMB_RQL034230400001_23941949_CSV_PARTE_II.zip
        → ASEMB_RQL034230400001_23941949.zip
        → context.is_parte = True
    """

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile
        self._compiled_patterns: tuple[re.Pattern[str], ...] = ()

        if rule_profile.zip_policy:
            self._compiled_patterns = tuple(
                re.compile(pattern)
                for pattern in rule_profile.zip_policy.parte_detection_patterns
            )

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        if context.suffix != ".zip" or not self._compiled_patterns:
            return context

        working_stem = context.stem
        tokens = working_stem.split("_")

        # Busca el primer token (o par de tokens) que coincide con un patrón PARTE
        cut_index = self._find_parte_cut_index(tokens)

        if cut_index is None:
            return context

        clean_tokens = tokens[:cut_index]
        if not clean_tokens:
            return context

        clean_stem = "_".join(clean_tokens)
        context.is_parte = True
        context.update_filename(f"{clean_stem}{context.suffix}")
        context.tokens = clean_tokens
        context.add_fix(
            f"Se eliminó la referencia PARTE del nombre: '{working_stem}' → '{clean_stem}'."
        )
        return context

    def _find_parte_cut_index(self, tokens: list[str]) -> Optional[int]:
        """Devuelve el índice del primer token donde empieza una referencia PARTE.

        Evalúa tanto tokens individuales como pares de tokens adyacentes
        para capturar variantes como 'CSV_PARTE' o 'VI_PARTE'.
        """

        for i, token in enumerate(tokens):
            # Token individual (ej: PARTE_1, PARTE_II)
            for pattern in self._compiled_patterns:
                if pattern.fullmatch(token):
                    return i

            # Par con el token anterior (ej: tokens[i-1]='CSV', tokens[i]='PARTE')
            if i > 0:
                pair = f"{tokens[i - 1]}_{token}"
                for pattern in self._compiled_patterns:
                    if pattern.fullmatch(pair):
                        return i - 1

        return None
