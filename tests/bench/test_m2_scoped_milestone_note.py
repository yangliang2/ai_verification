from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_NOTE = _ROOT / "docs" / "M2-scoped-milestone-note.md"


def test_m2_scoped_milestone_note_links_source_evidence() -> None:
    text = _NOTE.read_text(encoding="utf-8")

    for issue in ("#9", "#10", "#12", "#14", "#15", "#16", "#17", "#18", "#19", "#21"):
        assert issue in text

    for evidence_path in (
        "docs/M1-goldset-report.md",
        "docs/M2-l3-text-layout-summary.md",
        "docs/M2-metric-schema.md",
        "docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/",
        "docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/",
        "docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/",
        "docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/",
    ):
        assert evidence_path in text

    for proven_claim in (
        "M1 has five category seeds and all five injected defects were caught",
        "baseline L2 pass, defect L2 fail",
        "baseline L3 pass, defect L3 fail",
        "20 total L3 judge calls",
        "20 valid",
        "0 errors",
        "10/10 pass",
        "10/10 fail",
        "0.96-0.98",
    ):
        assert proven_claim in text


def test_m2_scoped_milestone_note_preserves_scope_boundaries() -> None:
    text = _NOTE.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    for limitation in (
        "benchmark-wide detection rate",
        "benchmark-wide false-positive rate",
        "visual-only or multimodal L3 reliability",
        "fully unattended Journey reliability",
        "100+ AI-generated defects",
        "cross-host or non-Wikipedia generality",
        "ColorOS migration readiness",
        "public throughput or cost metrics",
    ):
        assert limitation in text

    for boundary in (
        "`scenario.l3_spec` plus observed evidence only",
        "does not receive `expected_behavior`",
        "the injected patch",
        "issue text",
        "frozen verdict fixtures",
    ):
        assert boundary in normalized_text

    for next_decision in (
        "Add another M2 seed deliberately",
        "Use the metric context contract",
        "Harden automation",
        "M2-beta milestone",
    ):
        assert next_decision in text
