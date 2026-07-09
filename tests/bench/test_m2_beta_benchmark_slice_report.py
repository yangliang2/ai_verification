from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_REPORT = _ROOT / "docs" / "M2-beta-benchmark-slice-report.md"
_README = _ROOT / "README.md"


def test_m2_beta_report_links_child_issues_and_artifacts() -> None:
    text = _REPORT.read_text(encoding="utf-8")

    for issue in ("#24", "#25", "#26", "#27", "#28", "#29"):
        assert issue in text

    for artifact in (
        "docs/M2-beta-inclusion-rules.md",
        "docs/M2-metric-schema.md",
        "bench/goldset/m2-beta-slice.yaml",
        "src/aiverify/bench/m2_beta_summary.py",
        "docs/M2-beta-aggregate-summary.md",
        "docs/M2-beta-oversized-saved-state-quarantine.md",
        "docs/M1-goldset-report.md",
        "docs/M2-l3-text-layout-summary.md",
    ):
        assert artifact in text


def test_m2_beta_report_summarizes_accounting_counts() -> None:
    text = _REPORT.read_text(encoding="utf-8")

    for expected in (
        "included injected-defect seeds: 9",
        "blocked seeds: 1",
        "candidate seeds: 1",
        "repeatability-only packages: 2",
        "included defect outcomes: `caught: 9`",
        "baseline-control outcomes: `passed_control: 9`",
        "`L1`: 3",
        "`L2`: 4",
        "`L3`: 2",
    ):
        assert expected in text


def test_m2_beta_report_preserves_oversized_saved_state_boundary() -> None:
    text = _REPORT.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "#23" in text
    assert "remains implemented but is not included in M2-beta counts" in normalized_text
    assert "accounting state: `candidate` and `blocked`" in text
    assert "denominator impact: 0" in text
    assert "caught/missed outcome: none" in text
    assert "no defect lane was run" in text


def test_m2_beta_report_states_supported_and_out_of_scope_claims() -> None:
    text = _REPORT.read_text(encoding="utf-8")

    for supported in (
        "the MVP verification chain is live and audited",
        "M1 caught five of five seeded defects",
        "M2-beta has a reproducible aggregate summary",
        "#23 is quarantined from M2-beta counts",
    ):
        assert supported in text

    for out_of_scope in (
        "benchmark-wide detection rate",
        "benchmark-wide false-positive rate",
        "100+ AI-generated defect coverage",
        "fully unattended Journey reliability",
        "visual-only or multimodal L3 reliability",
        "ColorOS migration readiness",
    ):
        assert out_of_scope in text


def test_readme_points_to_m2_beta_report() -> None:
    text = _README.read_text(encoding="utf-8")

    assert "截至 2026-07-09" in text
    assert "docs/M2-beta-benchmark-slice-report.md" in text
    assert "docs/M2-beta-aggregate-summary.md" in text
    assert "9 included injected-defect seeds, 1 blocked/candidate seed" in text
    assert "#23 oversized saved-state seed 已 quarantine 出 M2-beta denominator" in text
