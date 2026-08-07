"""Static contracts for repository secret-scanner configuration."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

GITLEAKS_CONFIG = Path(__file__).resolve().parents[1] / ".gitleaks.toml"


def _rule(rule_id: str) -> dict[str, object]:
    config = tomllib.loads(GITLEAKS_CONFIG.read_text(encoding="utf-8"))
    matches = [rule for rule in config["rules"] if rule["id"] == rule_id]
    assert len(matches) == 1, f"expected exactly one {rule_id} scanner rule"
    return matches[0]


def test_openrouter_key_signature_has_an_explicit_scanner_rule():
    rule = _rule("openrouter-api-key")
    synthetic_key = "sk-or-v1-" + ("a" * 64)
    match = re.search(str(rule["regex"]), f"OPENROUTER_API_KEY={synthetic_key}")

    assert match is not None
    assert match.group(int(rule["secretGroup"])) == synthetic_key
    assert rule["keywords"] == ["sk-or-v1-"]


def test_openrouter_scanner_rule_ignores_names_and_incomplete_signatures():
    pattern = str(_rule("openrouter-api-key")["regex"])
    canonical_name = "_".join(("OPENROUTER", "API", "KEY"))  # noqa: FLY002
    legacy_name = "_".join(("OPENROUTER", "KEY"))  # noqa: FLY002
    variable_reference = f"{legacy_name}=${{{legacy_name}}}"

    assert re.search(pattern, f"{canonical_name}=") is None
    assert re.search(pattern, variable_reference) is None
    assert re.search(pattern, "sk-or-v1-" + ("a" * 31)) is None
