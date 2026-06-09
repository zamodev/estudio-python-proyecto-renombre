"""Estrategia que aplica plantillas de renombrado documental por casuística."""

from __future__ import annotations

import re
from datetime import date

from app.config_models import RuleProfile
from app.exceptions import FileProcessingError
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class ApplyNamingTemplateStrategy(FileStrategy):
    """Reconstruye nombres documentales a partir de reglas configurables."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile
        self._compiled_rules = [
            (rule, rule.compiled_match())
            for rule in self.rule_profile.naming_templates
            if rule.enabled
        ]

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        if context.naming_template_applied:
            return context

        if context.suffix != ".pdf" or not self._compiled_rules:
            return context

        working_stem = context.stem.strip().upper()

        for rule, compiled_match in self._compiled_rules:
            match = compiled_match.fullmatch(working_stem)
            if match is None:
                continue

            render_values = self._build_render_values(rule.date_source, match)

            try:
                rendered_stem = rule.template.format(**render_values).strip("_")
            except KeyError as exc:
                raise FileProcessingError(
                    f"La regla naming_templates '{rule.name}' referencia un campo inexistente: {exc.args[0]}."
                ) from exc

            if not rendered_stem:
                return context

            final_filename = f"{rendered_stem}{context.suffix}"

            context.naming_template_applied = True
            context.naming_template_rule = rule.name
            context.canonical_filename = final_filename
            context.tokens = [token for token in rendered_stem.split("_") if token]

            if final_filename != context.filename:
                context.update_filename(final_filename)
                context.add_fix(
                    f"Se aplicó la plantilla documental '{rule.name}' al nombre del archivo."
                )

            context.mark_valid()
            return context

        return context

    def _build_render_values(self, date_source: str, match: re.Match[str]) -> dict[str, str]:
        groups = {key: value for key, value in match.groupdict().items() if value is not None}
        execution_date = date.today().strftime("%d%m%Y")

        render_values = dict(groups)
        render_values["execution_date"] = execution_date
        render_values["date_compact"] = self._resolve_date_compact(groups, date_source, execution_date)
        render_values["suffix_block"] = f"_{groups['suffix']}" if groups.get("suffix") else ""

        if groups.get("prefix"):
            render_values["prefix"] = groups["prefix"]

        return render_values

    def _resolve_date_compact(
        self,
        groups: dict[str, str],
        date_source: str,
        execution_date: str,
    ) -> str:
        if date_source == "execution":
            return execution_date

        if all(groups.get(key) for key in ("day", "month", "year")):
            return f"{groups['day']}{groups['month']}{groups['year']}"

        compact_candidate = groups.get("date") or groups.get("dma") or groups.get("fecha")
        if compact_candidate:
            digits = re.sub(r"\D", "", compact_candidate)
            if len(digits) == 8:
                return digits

        return execution_date
