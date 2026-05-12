"""Modelos tipados de configuración para la aplicación.

Este módulo define exclusivamente los dataclasses que representan la configuración.
Toda la lógica de construcción y deserialización vive en config_loader.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PatternFixRule:
    """Regla de autocorrección estructural basada en expresiones regulares."""

    name: str
    match: str
    replace: str
    description: str = ""
    enabled: bool = True

    def compiled_match(self) -> re.Pattern[str]:
        """Compila y devuelve el patrón de búsqueda de la regla."""

        return re.compile(self.match)


@dataclass(frozen=True)
class CleanupRules:
    """Reglas de limpieza mecánica aplicadas al nombre del archivo."""

    uppercase: bool = True
    replace_spaces_with_underscore: bool = True
    replace_hyphen_with_underscore: bool = True
    collapse_multiple_underscores: bool = True
    remove_special_characters: bool = True
    remove_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutoFixPolicy:
    """Políticas de autocorrección permitidas para el perfil."""

    allow_pattern_fixes: bool = True
    allow_alias_fix: bool = True
    allow_separator_fix: bool = True
    allow_case_fix: bool = True
    allow_special_character_fix: bool = True
    allow_extension_normalization: bool = False
    allow_rub_guessing: bool = False
    allow_cedula_guessing: bool = False


@dataclass(frozen=True)
class DocumentTypeRule:
    """Reglas de negocio para un tipo documental."""

    name: str
    requires_cedula: bool
    default_extension: str
    allowed_extensions: tuple[str, ...]


@dataclass(frozen=True)
class ZipPolicy:
    """Política de filtrado del contenido interno de archivos ZIP."""

    parte_detection_patterns: tuple[str, ...]
    parte_keep_extensions: tuple[str, ...]
    general_remove_extensions: tuple[str, ...]
    strip_roman_suffix_from_token: bool = False


@dataclass(frozen=True)
class RuleProfile:
    """Perfil reutilizable con reglas documentales y autocorrecciones."""

    name: str
    document_types: dict[str, DocumentTypeRule]
    rub_patterns: tuple[str, ...]
    cedula_pattern: str
    pattern_fixes: tuple[PatternFixRule, ...]
    alias_map: dict[str, str]
    cleanup_rules: CleanupRules
    auto_fix_policy: AutoFixPolicy
    zip_policy: Optional[ZipPolicy] = None
    extension_alias_map: Optional[dict[str, dict[str, str]]] = None

    def compiled_rub_patterns(self) -> tuple[re.Pattern[str], ...]:
        """Compila y devuelve las expresiones regulares válidas para RUB."""

        return tuple(re.compile(pattern) for pattern in self.rub_patterns)

    def compiled_cedula_pattern(self) -> re.Pattern[str]:
        """Compila y devuelve la expresión regular de cédula."""

        return re.compile(self.cedula_pattern)


@dataclass(frozen=True)
class WatchProfile:
    """Configuración de una sola carpeta vigilada."""

    name: str
    watch_path: str
    destination_path: str
    rules_profile: Optional[str] = None
    strategies: Optional[list[dict]] = None
    process_existing_on_startup: bool = True
    recursive: bool = False
    stable_wait_seconds: int = 1
    stability_checks: int = 3
    report_path: Optional[str] = None


@dataclass(frozen=True)
class AppConfig:
    """Configuración principal de la aplicación."""

    watchers: list[WatchProfile]
    rule_profiles: dict[str, RuleProfile]
    log_level: str = "INFO"
