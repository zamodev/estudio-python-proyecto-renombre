"""Estrategia que corrige aliases conocidos del tipo documental."""

from __future__ import annotations

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ResolveAliasStrategy(FileStrategy):
    """Corrige prefijos documentales inválidos cuando existe una regla explícita.

    Soporta dos tipos de alias:
    - alias_map: alias simples sin discriminador de extensión (ej. 'AS_EMB' → 'ASEMB').
    - extension_alias_map: alias cuyo destino depende de la extensión del archivo
      (ej. 'EMB' → 'ASEMB' para .zip, 'CREMB' para .pdf).

    El alias_map se evalúa primero. El extension_alias_map actúa como fallback.
    """

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

        # Fallback: alias dependiente de extensión
        if replacement is None and self.rule_profile.extension_alias_map:
            ext_map = self.rule_profile.extension_alias_map.get(alias_candidate)
            if ext_map:
                replacement = ext_map.get(context.suffix)
                alias_length = 1

        if replacement is None:
            return context

        updated_tokens = [replacement, *tokens[alias_length:]]
        context.update_tokens(updated_tokens)
        context.add_fix(f"Se corrigió el alias documental '{alias_candidate}' a '{replacement}'.")
        return context


        updated_tokens = [replacement, *tokens[alias_length:]]
        context.update_tokens(updated_tokens)
        context.add_fix(f"Se corrigió el alias documental '{alias_candidate}' a '{replacement}'.")
        return context
