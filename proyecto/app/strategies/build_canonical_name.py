"""Estrategia que reconstruye el nombre documental canónico."""

from __future__ import annotations

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class BuildCanonicalNameStrategy(FileStrategy):
    """Reconstruye el nombre final esperado si la información mínima está presente."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        document_type = context.document_type
        if not document_type:
            return context

        document_rule = self.rule_profile.document_types.get(document_type)
        if document_rule is None or not context.rub:
            return context

        parts = [document_type, context.rub]
        if document_rule.requires_cedula:
            if not context.cedula:
                return context
            parts.append(context.cedula)

        canonical_filename = f"{'_'.join(parts)}{context.suffix}"
        context.canonical_filename = canonical_filename

        if canonical_filename != context.filename:
            context.update_filename(canonical_filename)
            context.add_fix("Se reconstruyó el nombre al formato canónico.")

        return context
