from __future__ import annotations

from pathlib import Path

from aiverify.bench.m2_beta_summary import build_summary, render_markdown


_ROOT = Path(__file__).resolve().parents[2]
_SUMMARY_DOC = _ROOT / "docs" / "M2-beta-aggregate-summary.md"


def test_m2_beta_summary_counts_seed_accounting() -> None:
    summary = build_summary(_ROOT)

    assert summary.state_counts == {"included": 10}
    assert summary.candidate_count == 0
    assert summary.defect_outcomes == {"caught": 10}
    assert summary.control_outcomes == {"passed_control": 10}


def test_m2_beta_summary_separates_oracle_and_taxonomy_counts() -> None:
    summary = build_summary(_ROOT)

    assert summary.expected_oracle_levels == {"L1": 4, "L2": 4, "L3": 2}
    assert summary.oracle_defect_classes == {
        "crash_stability": 4,
        "state_loss": 4,
        "ui_rendering": 2,
    }
    assert summary.taxonomy_categories == {
        "config-change": 2,
        "coroutine-concurrency": 1,
        "lifecycle": 1,
        "navigation": 2,
        "process-death": 2,
        "ui-rendering": 2,
    }


def test_m2_beta_summary_includes_resolved_oversized_saved_state() -> None:
    summary = build_summary(_ROOT)
    seed = next(
        seed for seed in summary.seeds
        if seed.seed_id == "wikipedia-process-death-03-oversized-saved-state"
    )

    assert seed.accounting_state == "included"
    assert seed.candidate is False
    assert seed.defect_outcome == "caught"
    assert seed.control_outcome == "passed_control"
    assert seed.reason is None


def test_m2_beta_summary_reports_repeatability_separately() -> None:
    summary = build_summary(_ROOT)

    assert summary.repeatability_totals == {
        "packages": 2,
        "total_calls": 20,
        "baseline_passes": 10,
        "defect_fails": 10,
        "errors": 0,
    }


def test_m2_beta_summary_doc_matches_renderer() -> None:
    summary = build_summary(_ROOT)
    rendered = render_markdown(summary)

    assert _SUMMARY_DOC.read_text(encoding="utf-8") == rendered
    assert "Blocked And Candidate Seeds" in rendered
    assert "| None | - | - | - |" in rendered
    assert "Fixed-Evidence L3 Repeatability" in rendered
    assert "It does not add extra caught, missed, or control outcomes." in rendered
