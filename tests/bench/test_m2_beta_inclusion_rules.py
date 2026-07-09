from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_RULES = _ROOT / "docs" / "M2-beta-inclusion-rules.md"


def test_m2_beta_inclusion_rules_define_counting_states() -> None:
    text = _RULES.read_text(encoding="utf-8")

    for state in (
        "`included`",
        "`control`",
        "`repeatability-only`",
        "`candidate`",
        "`blocked`",
        "`excluded`",
    ):
        assert state in text

    assert "Only `included` injected-defect seeds can contribute to caught/missed counts" in text
    assert "Every other state must be reported outside the numerator and denominator" in text


def test_m2_beta_inclusion_rules_require_matched_pair_for_counts() -> None:
    text = _RULES.read_text(encoding="utf-8")

    assert "A seed without a valid baseline/defect matched pair cannot count as caught or" in text
    assert "missed. It must be marked `candidate`, `blocked`, or `excluded`." in text
    assert "`caught` means at least one oracle returns `fail` on the defect path" in text
    assert "`missed` means no oracle returns `fail` on the defect path" in text
    assert "`passed_control` means no oracle returns `fail`" in text
    assert "`false_positive` means any oracle returns `fail`" in text


def test_m2_beta_inclusion_rules_keep_repeatability_separate() -> None:
    text = _RULES.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "Fixed-evidence repeatability can support an L3 stability claim" in text
    assert "must not add extra seeds, caught outcomes, missed outcomes, or control outcomes" in normalized_text
    assert "Text-layout L3 repeatability packages | `repeatability-only`" in text


def test_m2_beta_inclusion_rules_include_resolved_oversized_saved_state_seed() -> None:
    text = _RULES.read_text(encoding="utf-8")

    assert "#23" in text
    assert "Oversized saved-state process-death seed (#23) | `included`" in text
    assert "defect_outcome=caught" in text
    assert "control_outcome=passed_control" in text
    assert "Therefore #23 is now an M2-beta `included` seed." in text
