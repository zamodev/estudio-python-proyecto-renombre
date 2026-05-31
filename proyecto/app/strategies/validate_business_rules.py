"""Estrategia que valida las reglas de negocio del nombre documental."""

from __future__ import annotations

import re

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ValidateBusinessRulesStrategy(FileStrategy):
    """Confirma si el nombre del archivo cumple el estándar documental configurado."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile
        self._rub_patterns = self.rule_profile.compiled_rub_patterns()
        self._cedula_pattern = self.rule_profile.compiled_cedula_pattern()

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        context.clear_errors()

        document_type = context.document_type
        if not document_type:
            context.mark_rejected("No se pudo identificar el tipo documental.")
            return context

        document_rule = self.rule_profile.document_types.get(document_type)
        if document_rule is None:
            context.mark_rejected(f"El tipo documental '{document_type}' no está configurado.")
            return context

        expected_tokens = 3 if document_rule.requires_cedula else 2
        if len(context.tokens) != expected_tokens:
            context.add_error(
                f"El tipo documental '{document_type}' requiere {expected_tokens} segmento(s)."
            )

        if context.suffix not in document_rule.allowed_extensions:
            context.add_error(
                f"La extensión '{context.suffix}' no es válida para '{document_type}'."
            )

        if not context.rub:
            context.add_error("No se encontró el RUB en el nombre del archivo.")
        else:
            for rule in self.rule_profile.rub_reject_rules:
                if rule.enabled and re.fullmatch(rule.match, context.rub):
                    if rule.action == "delete":
                        context.mark_deleted(rule.message)
                    else:
                        context.mark_rejected(rule.message)
                    return context
            if not any(pattern.fullmatch(context.rub) for pattern in self._rub_patterns):
                context.add_error(f"El RUB '{context.rub}' no cumple los formatos permitidos.")

        if document_rule.requires_cedula:
            if not context.cedula:
                context.add_error(f"El tipo documental '{document_type}' requiere cédula.")
            elif not self._cedula_pattern.fullmatch(context.cedula):
                context.add_error(f"La cédula '{context.cedula}' no cumple el formato permitido.")
        elif context.cedula:
            context.add_error(f"El tipo documental '{document_type}' no debe incluir cédula.")

        if context.validation_errors:
            context.mark_rejected()
            return context

        context.mark_valid()
        return context
