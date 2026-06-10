from pathlib import Path
from app.config_loader import _merge_profile_dir, _build_rule_profile
from app.strategies.normalize_filename import NormalizeFilenameStrategy
from app.strategies.apply_naming_template import ApplyNamingTemplateStrategy
from app.models import FileContext
import sys


def build_profile():
    profile_dir = Path("config/profiles/documentos_legales")
    data = _merge_profile_dir(profile_dir)
    return _build_rule_profile("documentos_legales", data)


def run_case(path_str: str, expected: str) -> bool:
    profile = build_profile()
    norm = NormalizeFilenameStrategy(profile)
    applier = ApplyNamingTemplateStrategy(profile)

    ctx = FileContext.from_path(Path(path_str))
    ctx = norm.apply(ctx)
    ctx = applier.apply(ctx)

    ok = ctx.filename == expected and ctx.naming_template_applied
    print(f"{path_str} -> {ctx.filename} | expected: {expected} | OK: {ok}")
    if not ok:
        print("Fixes:", ctx.fixes_applied)
        print("Errors:", ctx.validation_errors)
    return ok


def main() -> int:
    cases = [
        ("1-Desembargos-RTA_RL00908723_11-08-2023_1456075.pdf", "1DESEMBARGOSRTA_RL00908723_11082023_1456075.pdf"),
        ("12-Desembargos-RTA_106108521_18-04-2023_1301245.pdf", "12DESEMBARGOSRTA_106108521_18042023_1301245.pdf"),
    ]

    all_ok = True
    for src, expected in cases:
        if not run_case(src, expected):
            all_ok = False

    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
