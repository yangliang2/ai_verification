from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.bench.m2_beta_summary import build_summary, render_markdown


_ROOT = Path(__file__).resolve().parents[2]
_SUMMARY_DOC = _ROOT / "docs" / "M2-beta-aggregate-summary.md"


def _write_run_spec(repo: Path, seed_id: str) -> None:
    spec_dir = repo / "bench" / "goldset" / "run-specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / f"{seed_id}.yaml").write_text(
        f"""
host_project: /hosts/wiki
apk_glob: app/build/**/*.apk
package: org.wikipedia.dev
scenario:
  id: {seed_id}
  metric_context:
    seed_kind: injected_defect
    taxonomy_category: config-change
    taxonomy_pattern_id: config-change-01
    expected_oracle_level: L2
    expected_oracle_defect_class: state_loss
  assertions: []
""",
        encoding="utf-8",
    )


def _oracle(level: str, outcome: str, defect_class: str | None = None) -> dict:
    return {
        "verdict_id": f"{level}-{outcome}",
        "level": level,
        "outcome": outcome,
        "defect_class_hypothesis": defect_class,
        "trigger_steps": [],
        "evidence": [],
        "confidence": 0.9,
    }


def _write_verdict(
    repo: Path,
    path: str,
    *,
    seed_id: str,
    l1: dict | None = None,
    l2: dict | None = None,
    l3: dict | None = None,
    execution_status: str | None = "completed",
    metric_seed_id: str | None = None,
) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario": seed_id,
        "l1": l1 or _oracle("L1", "inconclusive"),
        "l2": l2 or _oracle("L2", "inconclusive"),
        "l3": l3,
        "metric_context": {
            "seed_id": metric_seed_id or seed_id,
            "seed_kind": "injected_defect",
            "seed_outcome": "caught",
            "taxonomy_category": "config-change",
            "taxonomy_pattern_id": "config-change-01",
            "expected_oracle_level": "L2",
            "expected_oracle_defect_class": "state_loss",
        },
    }
    if execution_status is not None:
        payload["execution"] = {
            "status": execution_status,
            "accounting_eligible": execution_status == "completed",
        }
    target.write_text(json.dumps(payload), encoding="utf-8")


def _write_manifest(repo: Path, seed_id: str, seed_extra: str = "") -> None:
    manifest = repo / "bench" / "goldset" / "m2-beta-slice.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        f"""
version: 1
seeds:
  - id: {seed_id}
    run_spec: run-specs/{seed_id}.yaml
    accounting_state: included
    candidate: false
    evidence_type: live_matched_pair
    source_issues: ["#test"]
    evidence:
      control:
        verdict: docs/runs/{seed_id}/baseline/verdict.json
      defect:
        verdict: docs/runs/{seed_id}/defect/verdict.json
{seed_extra}
repeatability_packages: []
""",
        encoding="utf-8",
    )


def _fixture_repo(
    tmp_path: Path,
    seed_id: str = "fixture-seed",
    seed_extra: str = "",
) -> Path:
    repo = tmp_path / "repo"
    _write_run_spec(repo, seed_id)
    _write_manifest(repo, seed_id, seed_extra=seed_extra)
    _write_verdict(
        repo,
        f"docs/runs/{seed_id}/baseline/verdict.json",
        seed_id=seed_id,
        l2=_oracle("L2", "pass"),
    )
    _write_verdict(
        repo,
        f"docs/runs/{seed_id}/defect/verdict.json",
        seed_id=seed_id,
        l2=_oracle("L2", "fail", "state_loss"),
    )
    return repo


def test_m2_beta_summary_counts_seed_accounting() -> None:
    summary = build_summary(_ROOT)

    assert summary.state_counts == {"included": 10}
    assert summary.candidate_count == 0
    assert summary.defect_outcomes == {"caught": 10}
    assert summary.control_outcomes == {"passed_control": 10}
    assert summary.evidence_contracts == {"legacy_control_document": 3, "verdict": 7}


def test_m2_beta_summary_derives_outcomes_from_committed_verdicts(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)

    summary = build_summary(repo)

    assert summary.defect_outcomes == {"caught": 1}
    assert summary.control_outcomes == {"passed_control": 1}


def test_m2_beta_summary_rejects_manual_outcome_fields(tmp_path: Path) -> None:
    repo = _fixture_repo(
        tmp_path,
        seed_extra="    defect_outcome: missed\n    control_outcome: false_positive\n",
    )

    with pytest.raises(ValueError, match="manual outcome fields"):
        build_summary(repo)


def test_m2_beta_summary_rejects_nested_evidence_outcome_fields(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    manifest = repo / "bench/goldset/m2-beta-slice.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "      defect:\n        verdict:",
            "      defect:\n        outcome: caught\n        verdict:",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manual outcome"):
        build_summary(repo)


def test_m2_beta_summary_fails_closed_on_missing_evidence(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    (repo / "docs/runs/fixture-seed/defect/verdict.json").unlink()

    with pytest.raises(ValueError, match="missing defect verdict"):
        build_summary(repo)


def test_m2_beta_summary_fails_closed_on_non_accountable_lane(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _write_verdict(
        repo,
        "docs/runs/fixture-seed/defect/verdict.json",
        seed_id="fixture-seed",
        l2=_oracle("L2", "fail", "state_loss"),
        execution_status="non_accountable",
    )

    with pytest.raises(ValueError, match="non-accountable"):
        build_summary(repo)


def test_m2_beta_summary_fails_closed_on_metric_context_mismatch(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _write_verdict(
        repo,
        "docs/runs/fixture-seed/defect/verdict.json",
        seed_id="fixture-seed",
        l2=_oracle("L2", "fail", "state_loss"),
        metric_seed_id="other-seed",
    )

    with pytest.raises(ValueError, match="metric_context.seed_id"):
        build_summary(repo)


def test_m2_beta_summary_fails_closed_on_expected_class_contradiction(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    _write_verdict(
        repo,
        "docs/runs/fixture-seed/defect/verdict.json",
        seed_id="fixture-seed",
        l2=_oracle("L2", "fail", "ui_rendering"),
    )

    with pytest.raises(ValueError, match="expected class mismatch"):
        build_summary(repo)


def test_m2_beta_summary_derives_repeatability_from_committed_summary(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    run_record = repo / "docs/runs/repeatability"
    run_record.mkdir(parents=True)
    (run_record / "summary.json").write_text(
        json.dumps(
            {
                "total_iterations": 4,
                "total_errors": 1,
                "by_half": {
                    "baseline": {"outcomes": {"pass": 2}},
                    "defect": {"outcomes": {"fail": 1}},
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = repo / "bench/goldset/m2-beta-slice.yaml"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace(
            "repeatability_packages: []",
            """
repeatability_packages:
  - id: fixture-repeatability
    seed_id: fixture-seed
    evidence_type: fixed_evidence_repeatability
    source_issues: ["#test"]
    run_record: docs/runs/repeatability/
    total_calls: 999
    baseline_passes: 999
    defect_fails: 999
    errors: 999
""",
        ),
        encoding="utf-8",
    )

    summary = build_summary(repo)

    assert summary.repeatability_totals == {
        "packages": 1,
        "total_calls": 4,
        "baseline_passes": 2,
        "defect_fails": 1,
        "errors": 1,
    }


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
    assert "Evidence Contracts" in rendered
    assert "`legacy_control_document` | 3" in rendered
    assert "derive caught/missed and control outcomes from" in rendered
    assert "| None | - | - | - |" in rendered
    assert "Fixed-Evidence L3 Repeatability" in rendered
    assert "It does not add extra caught, missed, or control outcomes." in rendered
