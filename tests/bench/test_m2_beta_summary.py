from __future__ import annotations

from pathlib import Path

from aiverify.bench.m2_beta_summary import build_summary, render_markdown


_ROOT = Path(__file__).resolve().parents[2]
_SUMMARY_DOC = _ROOT / "docs" / "M2-beta-aggregate-summary.md"


def test_m2_beta_summary_counts_seed_accounting() -> None:
    summary = build_summary(_ROOT)

    assert summary.state_counts == {"blocked": 1, "included": 9}
    assert summary.candidate_count == 1
    assert summary.defect_outcomes == {"caught": 9}
    assert summary.control_outcomes == {"passed_control": 9}


def test_m2_beta_summary_separates_oracle_and_taxonomy_counts() -> None:
    summary = build_summary(_ROOT)

    assert summary.expected_oracle_levels == {"L1": 3, "L2": 4, "L3": 2}
    assert summary.oracle_defect_classes == {
        "crash_stability": 3,
        "state_loss": 4,
        "ui_rendering": 2,
    }
    assert summary.taxonomy_categories == {
        "config-change": 2,
        "coroutine-concurrency": 1,
        "lifecycle": 1,
        "navigation": 2,
        "process-death": 1,
        "ui-rendering": 2,
    }


def test_m2_beta_summary_keeps_blocked_candidate_out_of_counts() -> None:
    summary = build_summary(_ROOT)
    blocked = [seed for seed in summary.seeds if seed.accounting_state == "blocked"]

    assert len(blocked) == 1
    assert blocked[0].seed_id == "wikipedia-process-death-03-oversized-saved-state"
    assert blocked[0].candidate is True
    assert blocked[0].defect_outcome is None
    assert blocked[0].control_outcome is None
    assert "No valid baseline/defect matched pair" in (blocked[0].reason or "")


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
    assert "Fixed-Evidence L3 Repeatability" in rendered
    assert "It does not add extra caught, missed, or control outcomes." in rendered
