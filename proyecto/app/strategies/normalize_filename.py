"""Estrategia que normaliza mecánicamente el nombre del archivo."""

from __future__ import annotations

import re

from app.config_models import RuleProfile
from app.models import FileContext, ProcessingStatus
from app.strategies.base import FileStrategy


class NormalizeFilenameStrategy(FileStrategy):
    """Aplica reglas de limpieza básicas antes del análisis documental."""

    def __init__(self, rule_profile: RuleProfile):
        self.rule_profile = rule_profile

    def apply(self, context: FileContext) -> FileContext:
        if context.status == ProcessingStatus.REJECTED:
            return context

        rules = self.rule_profile.cleanup_rules
        working_stem = context.stem.strip()
        original_stem = working_stem

        if rules.uppercase:
            working_stem = working_stem.upper()

        for prefix in rules.remove_prefixes:
            normalized_prefix = prefix.strip().upper()
            if normalized_prefix and working_stem.startswith(normalized_prefix):
                working_stem = working_stem[len(normalized_prefix):].lstrip(" _-")
                context.add_fix(f"Se eliminó el prefijo de ruido '{normalized_prefix}'.")
                break

        if rules.replace_hyphen_with_underscore:
            working_stem = working_stem.replace("-", "_")

        if rules.replace_spaces_with_underscore:
            working_stem = re.sub(r"\s+", "_", working_stem)

        if rules.remove_special_characters:
            working_stem = re.sub(r"[^A-Z0-9_]", "", working_stem)

        if rules.collapse_multiple_underscores:
            working_stem = re.sub(r"_+", "_", working_stem)

        working_stem = working_stem.strip("_")

        if working_stem != original_stem:
            context.add_fix("Se aplicó normalización básica al nombre del archivo.")

        context.update_filename(f"{working_stem}{context.suffix}")
        context.tokens = [token for token in working_stem.split("_") if token]
        return context
