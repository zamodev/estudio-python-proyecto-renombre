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

        # Si está habilitado, elimina sufijos romanos pegados al último token
        # (ej: '095784782II' → '095784782' cuando viene de '095784782II PARTE')
        if (
            self.rule_profile.zip_policy
            and self.rule_profile.zip_policy.strip_roman_suffix_from_token
        ):
            clean_tokens = self._strip_roman_from_last_token(clean_tokens)

        clean_stem = "_".join(clean_tokens)
        context.is_parte = True
        context.update_filename(f"{clean_stem}{context.suffix}")
        context.tokens = clean_tokens
        context.add_fix(
            f"Se eliminó la referencia PARTE del nombre: '{working_stem}' → '{clean_stem}'."
        )
        return context

    _ROMAN_CEDULA_RE = re.compile(r"^(\d{6,12})[IVX]+$")

    def _strip_roman_from_last_token(self, tokens: list[str]) -> list[str]:
        """Elimina un sufijo romano del último token si tiene forma de cédula+romano.

        Ejemplo: '095784782II' → '095784782'
        Solo actúa si el token tiene al menos 6 dígitos seguidos de letras romanas.
        """

        last = tokens[-1]
        match = self._ROMAN_CEDULA_RE.fullmatch(last)
        if match:
            clean_last = match.group(1)
            return [*tokens[:-1], clean_last]
        return tokens

    def _find_parte_cut_index(self, tokens: list[str]) -> Optional[int]:
        """Devuelve el índice del primer token donde empieza una referencia PARTE.

        Evalúa pares de tokens adyacentes PRIMERO para que variantes como
        'VI_PARTE' sean capturadas al nivel del par (devolviendo i-1)
        antes de que el patrón '^PARTE$' capture 'PARTE' solo (devolvería i).
        """

        for i, token in enumerate(tokens):
            # Par con el token anterior PRIMERO (ej: 'VI_PARTE', 'CSV_PARTE')
            if i > 0:
                pair = f"{tokens[i - 1]}_{token}"
                for pattern in self._compiled_patterns:
                    if pattern.fullmatch(pair):
                        return i - 1

            # Token individual (ej: 'PARTE_1', 'PARTE_II', 'PARTE' solo)
            for pattern in self._compiled_patterns:
                if pattern.fullmatch(token):
                    return i

        return None
