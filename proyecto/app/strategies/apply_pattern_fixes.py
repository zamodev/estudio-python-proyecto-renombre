"""Estrategia que aplica autocorrecciones estructurales configuradas por patrón."""

from __future__ import annotations

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ApplyPatternFixesStrategy(FileStrategy):
    """Corrige nombres mal estructurados mediante reglas regex configurables."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile
        self._compiled_rules = [
            (rule, rule.compiled_match())
            for rule in self.rule_profile.pattern_fixes
            if rule.enabled
        ]

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        if not self.rule_profile.auto_fix_policy.allow_pattern_fixes:
            return context

        if not self._compiled_rules:
            return context

        working_stem = context.stem
        for rule, compiled_match in self._compiled_rules:
            match = compiled_match.fullmatch(working_stem)
            if match is None:
                continue

            updated_stem = match.expand(rule.replace).strip("_")
            if not updated_stem or updated_stem == working_stem:
                return context

            context.update_filename(f"{updated_stem}{context.suffix}")
            context.tokens = [token for token in updated_stem.split("_") if token]

            detail = rule.description or f"Regla '{rule.name}'"
            context.add_fix(f"Se aplicó pattern_fix: {detail}.")
            return context

        return context
