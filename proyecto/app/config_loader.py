"""Carga, construye y valida la configuración de la aplicación.

Soporta dos formatos:
- Formato plano (legado): un único config.json con watchers y rule_profiles inlineados.
- Formato modular: un config.json raíz que referencia watchers y perfiles por ruta de archivo/directorio.

Formato modular esperado en el config raíz:
    {
        "log_level": "INFO",
        "watchers": ["watchers/documentos_principales.json"],
        "rule_profiles": ["profiles/documentos_legales"]
    }

Estructura de un directorio de perfil:
    profiles/documentos_legales/
        profile.json          ← rub_patterns, cedula_pattern, cleanup_rules, auto_fix_policy
        document_types.json   ← dict de tipos documentales
        pattern_fixes.json    ← lista de reglas de autocorrección
        aliases.json          ← mapa de aliases documentales
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config_models import (
    AppConfig,
    AutoFixPolicy,
    CleanupRules,
    DocumentTypeRule,
    NamingTemplateRule,
    PatternFixRule,
    RubRejectRule,
    RuleProfile,
    WatchProfile,
    ZipPolicy,
)
from app.exceptions import ConfigurationError


_DEFAULT_PIPELINE = [
    {"name": "NormalizeFilenameStrategy", "params": {}},
    {"name": "ApplyPatternFixesStrategy", "params": {}},
    {"name": "ResolveAliasStrategy", "params": {}},
    {"name": "ApplyNamingTemplateStrategy", "params": {}},
    {"name": "StripParteStrategy", "params": {}},
    {"name": "ParseDocumentNameStrategy", "params": {}},
    {"name": "BuildCanonicalNameStrategy", "params": {}},
    {"name": "ValidateBusinessRulesStrategy", "params": {}},
]


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config/config.json") -> AppConfig:
    """Lee el archivo de configuración y devuelve un AppConfig tipado.

    Detecta automáticamente si el archivo usa formato plano (legado) o modular.
    """

    path = Path(config_path)

    if not path.exists():
        raise ConfigurationError(f"No existe el archivo de configuración: {config_path}")

    root = _read_json(path)
    base_dir = path.parent
    log_level = str(root.get("log_level", "INFO")).upper()

    watchers_raw = _resolve_watchers(root.get("watchers", []), base_dir)
    profiles_raw = _resolve_profiles(root.get("rule_profiles", {}), base_dir)

    return _build_app_config(
        watchers_raw=watchers_raw,
        profiles_raw=profiles_raw,
        log_level=log_level,
    )


# ---------------------------------------------------------------------------
# Resolución de formato (plano vs modular)
# ---------------------------------------------------------------------------

def _resolve_watchers(watchers_entry, base_dir: Path) -> list[dict]:
    """Resuelve la sección 'watchers' del config raíz a una lista de dicts."""

    if not isinstance(watchers_entry, list) or not watchers_entry:
        raise ConfigurationError("'watchers' debe ser una lista no vacía.")

    result = []
    for entry in watchers_entry:
        if isinstance(entry, str):
            result.append(_read_json(base_dir / entry))
        elif isinstance(entry, dict):
            result.append(entry)
        else:
            raise ConfigurationError(
                "Cada entrada de 'watchers' debe ser una ruta de archivo o un objeto JSON."
            )
    return result


def _resolve_profiles(profiles_entry, base_dir: Path) -> dict[str, dict]:
    """Resuelve la sección 'rule_profiles' del config raíz a un dict de dicts."""

    # Formato plano (legado): {"nombre_perfil": { ... }}
    if isinstance(profiles_entry, dict):
        return profiles_entry

    # Formato modular: ["profiles/documentos_legales", ...]
    if isinstance(profiles_entry, list):
        result = {}
        for entry in profiles_entry:
            if not isinstance(entry, str):
                raise ConfigurationError(
                    "En formato modular, cada entrada de 'rule_profiles' debe ser una ruta de directorio."
                )
            profile_dir = base_dir / entry
            if not profile_dir.is_dir():
                raise ConfigurationError(
                    f"No se encontró el directorio del perfil: {profile_dir}"
                )
            result[profile_dir.name] = _merge_profile_dir(profile_dir)
        return result

    raise ConfigurationError(
        "'rule_profiles' debe ser un objeto JSON (formato plano) o una lista de rutas (formato modular)."
    )


def _merge_profile_dir(profile_dir: Path) -> dict:
    """Combina los archivos de un directorio de perfil en un único dict."""

    profile_json = profile_dir / "profile.json"
    if not profile_json.exists():
        raise ConfigurationError(
            f"Falta 'profile.json' en el directorio del perfil: {profile_dir}"
        )

    merged = _read_json(profile_json)

    naming_templates_path = profile_dir / "naming_templates.json"
    if naming_templates_path.exists():
        merged["naming_templates"] = _read_json(naming_templates_path)

    doc_types_path = profile_dir / "document_types.json"
    if doc_types_path.exists():
        merged["document_types"] = _read_json(doc_types_path)

    pattern_fixes_path = profile_dir / "pattern_fixes.json"
    if pattern_fixes_path.exists():
        merged["pattern_fixes"] = _read_json(pattern_fixes_path)

    aliases_path = profile_dir / "aliases.json"
    if aliases_path.exists():
        merged["alias_map"] = _read_json(aliases_path)

    zip_policy_path = profile_dir / "zip_policy.json"
    if zip_policy_path.exists():
        merged["zip_policy"] = _read_json(zip_policy_path)

    ext_aliases_path = profile_dir / "extension_aliases.json"
    if ext_aliases_path.exists():
        merged["extension_alias_map"] = _read_json(ext_aliases_path)

    return merged


# ---------------------------------------------------------------------------
# Construcción del AppConfig
# ---------------------------------------------------------------------------

def _build_app_config(
    watchers_raw: list[dict],
    profiles_raw: dict[str, dict],
    log_level: str,
) -> AppConfig:
    """Construye el AppConfig tipado a partir de los datos ya resueltos."""

    if not isinstance(profiles_raw, dict):
        raise ConfigurationError("'rule_profiles' debe ser un objeto JSON.")

    rule_profiles = {
        name: _build_rule_profile(name, profile_data)
        for name, profile_data in profiles_raw.items()
    }

    watchers = [
        _build_watch_profile(watcher_data, index=index, rule_profiles=rule_profiles)
        for index, watcher_data in enumerate(watchers_raw, start=1)
    ]

    return AppConfig(watchers=watchers, rule_profiles=rule_profiles, log_level=log_level)


# ---------------------------------------------------------------------------
# Builders de cada sección
# ---------------------------------------------------------------------------

def _build_watch_profile(
    data: dict,
    index: int,
    rule_profiles: dict[str, RuleProfile],
) -> WatchProfile:
    if not isinstance(data, dict):
        raise ConfigurationError(f"La entrada del watcher {index} debe ser un objeto JSON.")

    name = data.get("name") or f"watcher-{index}"
    watch_path = data.get("watch_path")
    destination_path = data.get("destination_path")
    rules_profile = data.get("rules_profile")
    strategies = data.get("strategies")

    if not watch_path or not destination_path:
        raise ConfigurationError(
            f"El watcher '{name}' debe incluir 'watch_path' y 'destination_path'."
        )

    if rules_profile and rules_profile not in rule_profiles:
        raise ConfigurationError(
            f"El watcher '{name}' referencia el perfil inexistente '{rules_profile}'."
        )

    if strategies is not None and (not isinstance(strategies, list) or not strategies):
        raise ConfigurationError(
            f"El watcher '{name}' debe definir una lista válida de estrategias si la informa."
        )

    if strategies is None and rules_profile is not None:
        strategies = list(_DEFAULT_PIPELINE)

    if strategies is None:
        raise ConfigurationError(
            f"El watcher '{name}' debe definir estrategias o un 'rules_profile'."
        )

    return WatchProfile(
        name=name,
        watch_path=watch_path,
        destination_path=destination_path,
        rules_profile=rules_profile,
        strategies=strategies,
        process_existing_on_startup=bool(data.get("process_existing_on_startup", True)),
        recursive=bool(data.get("recursive", False)),
        stable_wait_seconds=int(data.get("stable_wait_seconds", 1)),
        stability_checks=int(data.get("stability_checks", 3)),
        report_path=data.get("report_path") or None,
    )


def _build_rule_profile(name: str, data: dict) -> RuleProfile:
    if not isinstance(data, dict):
        raise ConfigurationError(f"El perfil '{name}' debe ser un objeto JSON.")

    document_types_data = data.get("document_types")
    rub_patterns_data = data.get("rub_patterns")
    cedula_pattern = data.get("cedula_pattern", r"^\d{6,12}$")
    alias_map_data = data.get("alias_map", {})
    pattern_fixes_data = data.get("pattern_fixes", [])
    cleanup_rules_data = data.get("cleanup_rules", {})
    auto_fix_policy_data = data.get("auto_fix_policy", {})
    zip_policy_data = data.get("zip_policy")
    extension_alias_map_data = data.get("extension_alias_map")
    rub_reject_rules_data = data.get("rub_reject_rules", [])
    naming_templates_data = data.get("naming_templates", [])

    if not isinstance(document_types_data, dict) or not document_types_data:
        raise ConfigurationError(
            f"El perfil '{name}' debe definir al menos un tipo documental en 'document_types'."
        )

    if not isinstance(rub_patterns_data, list) or not rub_patterns_data:
        raise ConfigurationError(
            f"El perfil '{name}' debe definir una lista no vacía en 'rub_patterns'."
        )

    document_types = {
        doc_name.upper(): _build_document_type_rule(doc_name.upper(), doc_data)
        for doc_name, doc_data in document_types_data.items()
    }

    alias_map = {
        alias.upper(): value.upper()
        for alias, value in alias_map_data.items()
    }

    if not isinstance(pattern_fixes_data, list):
        raise ConfigurationError(
            f"El perfil '{name}' debe definir 'pattern_fixes' como una lista si lo informa."
        )

    pattern_fixes = tuple(
        _build_pattern_fix_rule(index=index, data=fix_data)
        for index, fix_data in enumerate(pattern_fixes_data, start=1)
    )

    cleanup_rules = CleanupRules(
        uppercase=bool(cleanup_rules_data.get("uppercase", True)),
        replace_spaces_with_underscore=bool(
            cleanup_rules_data.get("replace_spaces_with_underscore", True)
        ),
        replace_hyphen_with_underscore=bool(
            cleanup_rules_data.get("replace_hyphen_with_underscore", True)
        ),
        collapse_multiple_underscores=bool(
            cleanup_rules_data.get("collapse_multiple_underscores", True)
        ),
        remove_special_characters=bool(
            cleanup_rules_data.get("remove_special_characters", True)
        ),
        remove_prefixes=tuple(
            prefix.upper() for prefix in cleanup_rules_data.get("remove_prefixes", [])
        ),
    )

    auto_fix_policy = AutoFixPolicy(
        allow_pattern_fixes=bool(auto_fix_policy_data.get("allow_pattern_fixes", True)),
        allow_alias_fix=bool(auto_fix_policy_data.get("allow_alias_fix", True)),
        allow_separator_fix=bool(auto_fix_policy_data.get("allow_separator_fix", True)),
        allow_case_fix=bool(auto_fix_policy_data.get("allow_case_fix", True)),
        allow_special_character_fix=bool(
            auto_fix_policy_data.get("allow_special_character_fix", True)
        ),
        allow_extension_normalization=bool(
            auto_fix_policy_data.get("allow_extension_normalization", False)
        ),
        allow_rub_guessing=bool(auto_fix_policy_data.get("allow_rub_guessing", False)),
        allow_cedula_guessing=bool(auto_fix_policy_data.get("allow_cedula_guessing", False)),
    )

    if not isinstance(rub_reject_rules_data, list):
        raise ConfigurationError(
            f"El perfil '{name}' debe definir 'rub_reject_rules' como una lista si lo informa."
        )

    rub_reject_rules = tuple(
        _build_rub_reject_rule(index=index, data=rule_data)
        for index, rule_data in enumerate(rub_reject_rules_data, start=1)
    )

    if not isinstance(naming_templates_data, list):
        raise ConfigurationError(
            f"El perfil '{name}' debe definir 'naming_templates' como una lista si lo informa."
        )

    naming_templates = tuple(
        _build_naming_template_rule(index=index, data=rule_data)
        for index, rule_data in enumerate(naming_templates_data, start=1)
    )

    return RuleProfile(
        name=name,
        document_types=document_types,
        rub_patterns=tuple(rub_patterns_data),
        cedula_pattern=cedula_pattern,
        pattern_fixes=pattern_fixes,
        alias_map=alias_map,
        cleanup_rules=cleanup_rules,
        auto_fix_policy=auto_fix_policy,
        zip_policy=_build_zip_policy(zip_policy_data) if zip_policy_data else None,
        extension_alias_map=_build_extension_alias_map(extension_alias_map_data) if extension_alias_map_data else None,
        rub_reject_rules=rub_reject_rules,
        naming_templates=naming_templates,
    )


def _build_pattern_fix_rule(index: int, data: dict) -> PatternFixRule:
    if not isinstance(data, dict):
        raise ConfigurationError(f"La regla pattern_fixes #{index} debe ser un objeto JSON.")

    name = str(data.get("name") or f"pattern_fix_{index}")
    match = str(data.get("match", ""))
    replace = str(data.get("replace", ""))
    description = str(data.get("description", ""))
    enabled = bool(data.get("enabled", True))

    if not match:
        raise ConfigurationError(
            f"La regla pattern_fixes '{name}' debe incluir el campo 'match'."
        )

    try:
        re.compile(match)
    except re.error as exc:
        raise ConfigurationError(
            f"La regla pattern_fixes '{name}' tiene una expresión regular inválida."
        ) from exc

    if not replace:
        raise ConfigurationError(
            f"La regla pattern_fixes '{name}' debe incluir el campo 'replace'."
        )

    return PatternFixRule(
        name=name,
        match=match,
        replace=replace,
        description=description,
        enabled=enabled,
    )


def _build_document_type_rule(name: str, data: dict) -> DocumentTypeRule:
    if not isinstance(data, dict):
        raise ConfigurationError(f"El tipo documental '{name}' debe ser un objeto JSON.")

    default_extension = str(data.get("default_extension", "")).lower()
    allowed_extensions_data = data.get("allowed_extensions", [])

    if not default_extension.startswith("."):
        raise ConfigurationError(
            f"El tipo documental '{name}' debe incluir un 'default_extension' válido."
        )

    if not isinstance(allowed_extensions_data, list) or not allowed_extensions_data:
        raise ConfigurationError(
            f"El tipo documental '{name}' debe definir 'allowed_extensions'."
        )

    return DocumentTypeRule(
        name=name,
        requires_cedula=bool(data.get("requires_cedula", True)),
        default_extension=default_extension,
        allowed_extensions=tuple(str(ext).lower() for ext in allowed_extensions_data),
    )


def _build_rub_reject_rule(index: int, data: dict) -> RubRejectRule:
    if not isinstance(data, dict):
        raise ConfigurationError(f"La regla rub_reject_rules #{index} debe ser un objeto JSON.")

    name = str(data.get("name") or f"rub_reject_{index}")
    match = str(data.get("match", ""))
    message = str(data.get("message", ""))
    action = str(data.get("action", "reject")).lower()
    enabled = bool(data.get("enabled", True))

    if not match:
        raise ConfigurationError(
            f"La regla rub_reject_rules '{name}' debe incluir el campo 'match'."
        )

    try:
        re.compile(match)
    except re.error as exc:
        raise ConfigurationError(
            f"La regla rub_reject_rules '{name}' tiene una expresión regular inválida."
        ) from exc

    if action not in ("reject", "delete"):
        raise ConfigurationError(
            f"La regla rub_reject_rules '{name}' tiene un 'action' inválido: '{action}'. "
            "Use 'reject' o 'delete'."
        )

    return RubRejectRule(
        name=name,
        match=match,
        message=message,
        action=action,
        enabled=enabled,
    )


def _build_naming_template_rule(index: int, data: dict) -> NamingTemplateRule:
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"La regla naming_templates #{index} debe ser un objeto JSON."
        )

    name = str(data.get("name") or f"naming_template_{index}")
    match = str(data.get("match", ""))
    template = str(data.get("template", ""))
    description = str(data.get("description", ""))
    enabled = bool(data.get("enabled", True))
    date_source = str(data.get("date_source", "filename_or_execution")).lower()

    if not match:
        raise ConfigurationError(
            f"La regla naming_templates '{name}' debe incluir el campo 'match'."
        )

    try:
        re.compile(match)
    except re.error as exc:
        raise ConfigurationError(
            f"La regla naming_templates '{name}' tiene una expresión regular inválida."
        ) from exc

    if not template:
        raise ConfigurationError(
            f"La regla naming_templates '{name}' debe incluir el campo 'template'."
        )

    if date_source not in {"filename", "execution", "filename_or_execution"}:
        raise ConfigurationError(
            f"La regla naming_templates '{name}' tiene un 'date_source' inválido: '{date_source}'."
        )

    return NamingTemplateRule(
        name=name,
        match=match,
        template=template,
        description=description,
        enabled=enabled,
        date_source=date_source,
    )


# ---------------------------------------------------------------------------
# Utilidad interna
# ---------------------------------------------------------------------------

def _build_zip_policy(data: dict) -> ZipPolicy:
    """Construye la política de filtrado ZIP desde un dict deserializado."""

    parte_patterns = data.get("parte_detection_patterns", [])
    parte_keep = data.get("parte_keep_extensions", [])
    general_remove = data.get("general_remove_extensions", [])

    if not isinstance(parte_patterns, list):
        raise ConfigurationError("'zip_policy.parte_detection_patterns' debe ser una lista.")
    if not isinstance(parte_keep, list):
        raise ConfigurationError("'zip_policy.parte_keep_extensions' debe ser una lista.")
    if not isinstance(general_remove, list):
        raise ConfigurationError("'zip_policy.general_remove_extensions' debe ser una lista.")

    return ZipPolicy(
        parte_detection_patterns=tuple(parte_patterns),
        parte_keep_extensions=tuple(ext.lower() for ext in parte_keep),
        general_remove_extensions=tuple(ext.lower() for ext in general_remove),
        strip_roman_suffix_from_token=bool(data.get("strip_roman_suffix_from_token", False)),
    )


def _build_extension_alias_map(data: dict) -> dict:
    """Construye el mapa de aliases dependientes de extensión.

    Formato esperado en el JSON:
        { "EMB": { ".zip": "ASEMB", ".pdf": "CREMB" }, ... }

    Las claves y valores se normalizan a mayúsculas; las extensiones a minúsculas.
    """

    if not isinstance(data, dict):
        raise ConfigurationError("'extension_alias_map' debe ser un objeto JSON.")

    result = {}
    for alias, ext_map in data.items():
        if not isinstance(ext_map, dict):
            raise ConfigurationError(
                f"El alias '{alias}' en 'extension_alias_map' debe mapear a un objeto JSON."
            )
        result[alias.upper()] = {
            ext.lower(): target.upper()
            for ext, target in ext_map.items()
        }
    return result


def _read_json(path: Path) -> dict:
    """Lee y parsea un archivo JSON; lanza ConfigurationError si falla."""

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise ConfigurationError(f"No se encontró el archivo: {path}")
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"El archivo no es un JSON válido: {path}. Detalle: {exc}") from exc
