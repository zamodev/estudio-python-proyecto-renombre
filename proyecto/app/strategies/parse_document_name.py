"""Estrategia que interpreta las partes del nombre documental."""

from __future__ import annotations

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ParseDocumentNameStrategy(FileStrategy):
    """Extrae tipo documental, RUB y cédula desde el nombre actual."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        tokens = context.tokens or [token for token in context.stem.split("_") if token]
        context.tokens = tokens

        if not tokens:
            return context

        context.document_type = tokens[0]
        context.rub = tokens[1] if len(tokens) >= 2 else None
        context.cedula = tokens[2] if len(tokens) >= 3 else None
        return context
