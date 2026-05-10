"""Estrategia que corrige aliases conocidos del tipo documental."""

from __future__ import annotations

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ResolveAliasStrategy(FileStrategy):
    """Corrige prefijos documentales inválidos cuando existe una regla explícita."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        if not self.rule_profile.auto_fix_policy.allow_alias_fix:
            return context

        tokens = context.tokens or [token for token in context.stem.split("_") if token]
        if not tokens:
            return context

        alias_map = self.rule_profile.alias_map
        alias_candidate = tokens[0]
        alias_length = 1

        if len(tokens) >= 2:
            joined = f"{tokens[0]}_{tokens[1]}"
            if joined in alias_map:
                alias_candidate = joined
                alias_length = 2

        replacement = alias_map.get(alias_candidate)
        if replacement is None:
            return context

        updated_tokens = [replacement, *tokens[alias_length:]]
        context.update_tokens(updated_tokens)
        context.add_fix(f"Se corrigió el alias documental '{alias_candidate}' a '{replacement}'.")
        return context
