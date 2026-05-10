
"""Registro de estrategias usado para construir canales desde la configuración."""

from app.config_models import RuleProfile
from typing import Optional
from app.strategies.remove_spaces import RemoveSpacesStrategy
from app.strategies.uppercase_name import UppercaseNameStrategy
from app.strategies.validate_extension import ValidateExtensionStrategy
from app.strategies.validate_filename_pattern import ValidateFilenamePatternStrategy
from app.strategies.normalize_filename import NormalizeFilenameStrategy
from app.strategies.apply_pattern_fixes import ApplyPatternFixesStrategy
from app.strategies.resolve_alias import ResolveAliasStrategy
from app.strategies.strip_parte import StripParteStrategy
from app.strategies.parse_document_name import ParseDocumentNameStrategy
from app.strategies.build_canonical_name import BuildCanonicalNameStrategy
from app.strategies.validate_business_rules import ValidateBusinessRulesStrategy
from app.exceptions import StrategyBuildError


STRATEGY_REGISTRY = {
    "ValidateExtensionStrategy": ValidateExtensionStrategy,
    "RemoveSpacesStrategy": RemoveSpacesStrategy,
    "UppercaseNameStrategy": UppercaseNameStrategy,
    "ValidateFilenamePatternStrategy": ValidateFilenamePatternStrategy,
    "NormalizeFilenameStrategy": NormalizeFilenameStrategy,
    "ApplyPatternFixesStrategy": ApplyPatternFixesStrategy,
    "ResolveAliasStrategy": ResolveAliasStrategy,
    "StripParteStrategy": StripParteStrategy,
    "ParseDocumentNameStrategy": ParseDocumentNameStrategy,
    "BuildCanonicalNameStrategy": BuildCanonicalNameStrategy,
    "ValidateBusinessRulesStrategy": ValidateBusinessRulesStrategy,
}


PROFILE_AWARE_STRATEGIES = {
    "NormalizeFilenameStrategy",
    "ApplyPatternFixesStrategy",
    "ResolveAliasStrategy",
    "StripParteStrategy",
    "ParseDocumentNameStrategy",
    "BuildCanonicalNameStrategy",
    "ValidateBusinessRulesStrategy",
}


def build_strategy(strategy_config: dict, rule_profile: Optional[RuleProfile] = None):
    """Crea una instancia de estrategia a partir de su configuración JSON."""

    if not isinstance(strategy_config, dict):
        raise StrategyBuildError("Cada estrategia debe definirse como un objeto JSON.")

    strategy_name = strategy_config.get("name")
    params = strategy_config.get("params", {})

    if not strategy_name:
        raise StrategyBuildError("Cada estrategia debe incluir el campo 'name'.")

    if not isinstance(params, dict):
        raise StrategyBuildError(
            f"Los parámetros de la estrategia '{strategy_name}' deben ser un objeto JSON."
        )

    strategy_class = STRATEGY_REGISTRY.get(strategy_name)
    if strategy_class is None:
        raise StrategyBuildError(f"Estrategia no registrada: {strategy_name}")

    if strategy_name in PROFILE_AWARE_STRATEGIES:
        if rule_profile is None:
            raise StrategyBuildError(
                f"La estrategia '{strategy_name}' requiere un perfil de reglas configurado."
            )
        params = {**params, "rule_profile": rule_profile}

    try:
        return strategy_class(**params)
    except TypeError as exc:
        raise StrategyBuildError(
            f"No se pudieron aplicar los parámetros a la estrategia '{strategy_name}'."
        ) from exc
