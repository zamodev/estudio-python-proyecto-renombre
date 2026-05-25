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
        self._cedula_re = re.compile(rule_profile.cedula_pattern)

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

        # Rescata la cédula si quedó en los tokens descartados (después del corte PARTE)
        # Ej: ['PARTE', 'II', '79350147'] → rescata '79350147'
        discarded = tokens[cut_index:]
        rescued = self._find_cedula_in_tokens(discarded)
        if rescued:
            clean_tokens = [*clean_tokens, rescued]

        clean_stem = "_".join(clean_tokens)
        context.is_parte = True
        context.parte_index = self._extract_parte_index(tokens[cut_index:])
        context.update_filename(f"{clean_stem}{context.suffix}")
        context.tokens = clean_tokens
        context.add_fix(
            f"Se eliminó la referencia PARTE del nombre: '{working_stem}' → '{clean_stem}'."
        )
        return context

    def _find_cedula_in_tokens(self, tokens: list[str]) -> Optional[str]:
        """Devuelve el primer token de la lista que coincide con el patrón de cédula."""

        for token in tokens:
            if self._cedula_re.fullmatch(token):
                return token
        return None

    _ROMAN_CEDULA_RE = re.compile(r"^(\d{6,12})[IVX]+$")

    _PARTE_DIGIT_RE = re.compile(r"PARTE[_]?(\d+)")
    _PARTE_ROMAN_AFTER_RE = re.compile(r"PARTE[_]?([IVX]+)")
    _PARTE_ROMAN_BEFORE_RE = re.compile(r"([IVX]+)[_]?PARTE")

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

    def _extract_parte_index(self, discarded_tokens: list[str]) -> Optional[int]:
        """Extrae el número ordinal de la referencia PARTE (ej: PARTE_2 → 2, PARTE_II → 2).

        Evalúa los tokens descartados en este orden:
        1. Dígito explícito: PARTE_1, PARTE1
        2. Romano después de PARTE: PARTE_II, PARTE_VI
        3. Romano antes de PARTE: VI_PARTE, I_PARTE
        Devuelve None si no se puede determinar el número (PARTE solo, CSV_PARTE).
        """

        joined = "_".join(discarded_tokens)

        m = self._PARTE_DIGIT_RE.search(joined)
        if m:
            return int(m.group(1))

        m = self._PARTE_ROMAN_AFTER_RE.search(joined)
        if m:
            return self._roman_to_int(m.group(1))

        m = self._PARTE_ROMAN_BEFORE_RE.search(joined)
        if m:
            return self._roman_to_int(m.group(1))

        return None

    @staticmethod
    def _roman_to_int(s: str) -> Optional[int]:
        """Convierte un número romano a entero. Devuelve None si la cadena es inválida."""

        _VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
        result = 0
        prev = 0
        for char in reversed(s.upper()):
            val = _VALUES.get(char)
            if val is None:
                return None
            result += val if val >= prev else -val
            prev = val
        return result if result > 0 else None

    def _find_parte_cut_index(self, tokens: list[str]) -> Optional[int]:        """Devuelve el índice del primer token donde empieza una referencia PARTE.

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
