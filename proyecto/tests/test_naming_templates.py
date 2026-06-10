from pathlib import Path

from app.config_loader import load_config
from app.strategies.normalize_filename import NormalizeFilenameStrategy
from app.strategies.apply_naming_template import ApplyNamingTemplateStrategy
from app.models import FileContext


def load_profile():
    config = load_config("config/config.json")
    return config.rule_profiles["documentos_legales"]


def test_desembargos_variant_1():
    profile = load_profile()
    norm = NormalizeFilenameStrategy(profile)
    applier = ApplyNamingTemplateStrategy(profile)

    ctx = FileContext.from_path(Path("1-Desembargos-RTA_RL00908723_11-08-2023_1456075.pdf"))
    ctx = norm.apply(ctx)
    ctx = applier.apply(ctx)

    assert ctx.filename == "1DESEMBARGOSRTA_RL00908723_11082023_1456075.pdf"
    assert ctx.naming_template_applied


def test_desembargos_variant_2():
    profile = load_profile()
    norm = NormalizeFilenameStrategy(profile)
    applier = ApplyNamingTemplateStrategy(profile)

    ctx = FileContext.from_path(Path("12-Desembargos-RTA_106108521_18-04-2023_1301245.pdf"))
    ctx = norm.apply(ctx)
    ctx = applier.apply(ctx)

    assert ctx.filename == "12DESEMBARGOSRTA_106108521_18042023_1301245.pdf"
    assert ctx.naming_template_applied
