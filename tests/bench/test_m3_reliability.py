"""M3 Verification Agent execution-reliability tracer tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import aiverify.bench.m3_audit as m3_audit
from aiverify.bench.m3_audit import (
    audited_report_to_dict,
    build_audited_report,
    render_audited_markdown,
)
from aiverify.bench.m3_reliability import (
    build_progress,
    build_summary,
    load_manifest,
    main,
    plan_lanes,
    progress_to_dict,
    render_markdown,
    run_lane,
    summary_to_dict,
)
from aiverify.bench.run_record_checksums import verify_manifest, write_manifest
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.run_spec import load_run_spec


_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "bench" / "goldset" / "m3-reliability-slice.yaml"
_REBASELINE_MANIFEST = (
    _ROOT / "bench" / "goldset" / "m3-reliability-slice-v2.yaml"
)
_FINAL_RUN = _ROOT / "docs" / "runs" / "2026-07-13-m3-final-reliability-baseline"
_V2_ANR_RUN = _ROOT / "docs" / "runs" / "2026-07-15-m3-v2-anr-reliability"
_V2_OVERSIZED_RUN = (
    _ROOT / "docs" / "runs" / "2026-07-15-m3-v2-oversized-saved-state-reliability"
)
_V2_QUERY_RUN = (
    _ROOT / "docs" / "runs" / "2026-07-15-m3-v2-query-duplication-reliability"
)


class VerdictWritingRunner(CommandRunner):
    def __init__(self, verdict: dict, *, returncode: int = 0) -> None:
        self.verdict = verdict
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        artifact_dir = Path(args[args.index("--artifact-dir") + 1])
        artifact_dir.mkdir(parents=True)
        (artifact_dir.parent / "verdict.json").write_text(
            json.dumps(self.verdict), encoding="utf-8"
        )
        return CommandResult(
            args=args,
            stdout="runner result\n",
            stderr="",
            returncode=self.returncode,
        )


def test_manifest_defines_six_lanes_per_m3_seed() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)

    assert manifest.slice_id == "m3-verification-agent-reliability"
    assert manifest.max_attempts_per_lane == 2
    assert len(manifest.lanes) == 30
    assert {
        seed_id: [
            (lane.role, lane.repetition)
            for lane in manifest.lanes
            if lane.seed_id == seed_id
        ]
        for seed_id in {lane.seed_id for lane in manifest.lanes}
    } == {
        "wikipedia-coroutine-concurrency-03-main-thread-anr": [
            ("baseline", 1),
            ("baseline", 2),
            ("baseline", 3),
            ("defect", 1),
            ("defect", 2),
            ("defect", 3),
        ],
        "wikipedia-process-death-03-oversized-saved-state": [
            ("baseline", 1),
            ("baseline", 2),
            ("baseline", 3),
            ("defect", 1),
            ("defect", 2),
            ("defect", 3),
        ],
        "wikipedia-config-change-02-query-duplication": [
            ("baseline", 1),
            ("baseline", 2),
            ("baseline", 3),
            ("defect", 1),
            ("defect", 2),
            ("defect", 3),
        ],
        "wikipedia-navigation-02-back-button-swallowed": [
            ("baseline", 1),
            ("baseline", 2),
            ("baseline", 3),
            ("defect", 1),
            ("defect", 2),
            ("defect", 3),
        ],
        "wikipedia-ui-rendering-02-search-card-copy-mismatch": [
            ("baseline", 1),
            ("baseline", 2),
            ("baseline", 3),
            ("defect", 1),
            ("defect", 2),
            ("defect", 3),
        ],
    }
    assert {lane.expected_oracle_level for lane in manifest.lanes} == {
        "L1",
        "L2",
        "L3",
    }
    assert {lane.expected_oracle_defect_class for lane in manifest.lanes} == {
        "crash_stability",
        "state_loss",
        "ui_rendering",
    }
    assert all(lane.run_spec.is_file() for lane in manifest.lanes)


def test_rebaseline_manifest_plans_thirty_fresh_isolated_lanes() -> None:
    historical = load_manifest(_MANIFEST, repo_root=_ROOT)
    rebaseline = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)

    plan = plan_lanes(rebaseline)

    assert rebaseline.schema_version == 2
    assert rebaseline.slice_id == "m3-verification-agent-reliability-v2"
    assert rebaseline.comparison_manifest == _MANIFEST
    assert len(rebaseline.lanes) == 30
    assert len({lane.lane_id for lane in rebaseline.lanes}) == 30
    assert {lane.lane_id for lane in rebaseline.lanes}.isdisjoint(
        lane.lane_id for lane in historical.lanes
    )
    assert {lane.evidence_dir for lane in rebaseline.lanes}.isdisjoint(
        lane.evidence_dir for lane in historical.lanes
    )
    assert len(plan) == 30
    assert {row["status"] for row in plan} <= {
        "pending",
        "retryable",
        "accountable_complete",
        "non_accountable_exhausted",
        "invalid_evidence",
    }
    assert all(0 <= row["attempts"] <= rebaseline.max_attempts_per_lane for row in plan)


def test_rebaseline_progress_keeps_old_and_new_denominators_isolated() -> None:
    historical = load_manifest(_MANIFEST, repo_root=_ROOT)
    rebaseline = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)

    historical_summary = build_summary(historical)
    progress = progress_to_dict(build_progress(rebaseline))

    assert historical_summary.planned_lanes == 30
    assert historical_summary.eventual_accountable == 27
    assert progress["planned_lanes"] == 30
    assert 0 <= progress["pending_lanes"] <= progress["planned_lanes"]
    assert len(progress["pending_lane_ids"]) == progress["pending_lanes"]
    assert set(progress["pending_lane_ids"]).isdisjoint(
        lane.lane_id for lane in historical.lanes
    )


def test_committed_v2_anr_progress_is_derived_from_auditable_attempts() -> None:
    manifest = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)
    progress = progress_to_dict(build_progress(manifest))
    committed_progress = json.loads(
        (_V2_ANR_RUN / "progress.json").read_text(encoding="utf-8")
    )

    assert committed_progress["planned_lanes"] == 30
    assert committed_progress["pending_lanes"] == 24
    assert committed_progress["eventual_accountable"] == 5
    assert committed_progress["control_outcomes"] == {"passed_control": 2}
    assert committed_progress["defect_outcomes"] == {"caught": 3}
    assert committed_progress["failure_classes"] == {"preflight_environment": 2}
    assert progress["planned_lanes"] == committed_progress["planned_lanes"]
    assert progress["pending_lanes"] <= committed_progress["pending_lanes"]
    assert progress["eventual_accountable"] >= committed_progress[
        "eventual_accountable"
    ]

    anr_lanes = [lane for lane in manifest.lanes if lane.lane_id.startswith("v2-anr")]
    assert len(anr_lanes) == 6
    for lane in anr_lanes:
        attempt_dirs = sorted(lane.evidence_dir.glob("attempt-*"))
        assert 1 <= len(attempt_dirs) <= manifest.max_attempts_per_lane
        assert all(verify_manifest(attempt_dir) == [] for attempt_dir in attempt_dirs)

        verdicts = [
            json.loads((attempt_dir / "verdict.json").read_text(encoding="utf-8"))
            for attempt_dir in attempt_dirs
        ]
        accountable = [
            verdict
            for verdict in verdicts
            if verdict["execution"]["accounting_eligible"]
        ]
        if accountable:
            assert len(attempt_dirs) == 1

        if lane.role == "defect":
            assert len(accountable) == 1
            verdict = accountable[0]
            assert verdict["metric_context"]["seed_outcome"] == "caught"
            assert verdict["l1"]["outcome"] == "fail"
            assert verdict["l1"]["defect_class_hypothesis"] == "crash_stability"
            assert any(
                "ANR in org.wikipedia.dev" in evidence["ref"]
                for evidence in verdict["l1"]["evidence"]
            )
            lineage = json.loads(
                next(
                    attempt_dirs[0].glob(
                        "artifacts/*/codex-journey-action-lineage.json"
                    )
                ).read_text(encoding="utf-8")
            )
            assert [row["status"] for row in lineage["results"]] == [
                "PASSED",
                "PASSED",
            ]

    baseline_3 = next(lane for lane in anr_lanes if lane.lane_id == "v2-anr-baseline-3")
    assert len(list(baseline_3.evidence_dir.glob("attempt-*"))) == 2
    assert all(
        json.loads((attempt / "verdict.json").read_text(encoding="utf-8"))[
            "execution"
        ]["reason"]
        == "live_validation_preflight_failed"
        for attempt in baseline_3.evidence_dir.glob("attempt-*")
    )

    readme = (_V2_ANR_RUN / "README.md").read_text(encoding="utf-8")
    assert "#49" in readme
    assert "#50" in readme
    assert verify_manifest(_V2_ANR_RUN) == []


def test_committed_v2_oversized_state_progress_has_matched_auditable_attempts() -> None:
    manifest = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)
    progress = progress_to_dict(build_progress(manifest))
    committed_progress = json.loads(
        (_V2_OVERSIZED_RUN / "progress.json").read_text(encoding="utf-8")
    )

    assert committed_progress["planned_lanes"] == 30
    assert committed_progress["pending_lanes"] == 18
    assert committed_progress["eventual_accountable"] == 11
    assert committed_progress["control_outcomes"] == {"passed_control": 5}
    assert committed_progress["defect_outcomes"] == {"caught": 6}
    assert committed_progress["failure_classes"] == {"preflight_environment": 2}
    assert progress["planned_lanes"] == committed_progress["planned_lanes"]
    assert progress["pending_lanes"] <= committed_progress["pending_lanes"]
    assert progress["eventual_accountable"] >= committed_progress[
        "eventual_accountable"
    ]

    lanes = [
        lane
        for lane in manifest.lanes
        if lane.lane_id.startswith("v2-oversized-state")
    ]
    assert len(lanes) == 6
    for lane in lanes:
        attempt_dirs = sorted(lane.evidence_dir.glob("attempt-*"))
        assert len(attempt_dirs) == 1
        attempt_dir = attempt_dirs[0]
        assert verify_manifest(attempt_dir) == []

        gate = json.loads(
            (attempt_dir / "live-validation-gate.json").read_text(encoding="utf-8")
        )
        verdict = json.loads(
            (attempt_dir / "verdict.json").read_text(encoding="utf-8")
        )
        assert gate["status"] == "passed"
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["injected_events"] == [
            {"event": "app_to_background", "args": {}}
        ]
        assert verdict["checkpoints"] == ["after-segment-0", "after-event-0"]
        assert [
            result["status"]
            for result in verdict["journey_results"][0]["results"]
        ] == ["PASSED", "PASSED"]

        if lane.role == "baseline":
            assert verdict["metric_context"]["failed_oracles"] == []
            assert verdict["metric_context"]["oracle_outcomes"]["L1"] == (
                "inconclusive"
            )
        else:
            assert verdict["metric_context"]["seed_outcome"] == "caught"
            assert verdict["l1"]["outcome"] == "fail"
            assert verdict["l1"]["defect_class_hypothesis"] == "crash_stability"
            assert any(
                "TransactionTooLargeException: data parcel size 2110592 bytes"
                in evidence["ref"]
                for evidence in verdict["l1"]["evidence"]
            )
            assert "TransactionTooLargeException: data parcel size 2110592 bytes" in (
                attempt_dir / "artifacts" / "after-event-0" / "logcat.txt"
            ).read_text(encoding="utf-8")

    readme = (_V2_OVERSIZED_RUN / "README.md").read_text(encoding="utf-8")
    assert "#53" in readme
    assert "app_to_background" in readme
    assert verify_manifest(_V2_OVERSIZED_RUN) == []


def test_committed_v2_query_progress_has_matched_auditable_attempts() -> None:
    manifest = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)
    progress = progress_to_dict(build_progress(manifest))
    committed_progress = json.loads(
        (_V2_QUERY_RUN / "progress.json").read_text(encoding="utf-8")
    )

    assert committed_progress["planned_lanes"] == 30
    assert committed_progress["pending_lanes"] == 12
    assert committed_progress["eventual_accountable"] == 17
    assert committed_progress["control_outcomes"] == {"passed_control": 8}
    assert committed_progress["defect_outcomes"] == {"caught": 9}
    assert committed_progress["failure_classes"] == {"preflight_environment": 2}
    assert progress["planned_lanes"] == committed_progress["planned_lanes"]
    assert progress["pending_lanes"] <= committed_progress["pending_lanes"]
    assert progress["eventual_accountable"] >= committed_progress[
        "eventual_accountable"
    ]

    lanes = [
        lane
        for lane in manifest.lanes
        if lane.lane_id.startswith("v2-query-duplication")
    ]
    assert len(lanes) == 6
    for lane in lanes:
        attempt_dirs = sorted(lane.evidence_dir.glob("attempt-*"))
        assert len(attempt_dirs) == 1
        attempt_dir = attempt_dirs[0]
        assert verify_manifest(attempt_dir) == []

        attempt = json.loads(
            (attempt_dir / "attempt.json").read_text(encoding="utf-8")
        )
        gate = json.loads(
            (attempt_dir / "live-validation-gate.json").read_text(encoding="utf-8")
        )
        verdict = json.loads(
            (attempt_dir / "verdict.json").read_text(encoding="utf-8")
        )
        before_layout = json.loads(
            (
                attempt_dir
                / "artifacts"
                / "after-segment-0"
                / "layout.json"
            ).read_text(encoding="utf-8")
        )
        after_layout = json.loads(
            (attempt_dir / "artifacts" / "after-event-0" / "layout.json").read_text(
                encoding="utf-8"
            )
        )

        def search_text(layout: list[dict]) -> str:
            return next(
                item["text"]
                for item in layout
                if item.get("resource-id") == "search_src_text"
            )

        assert gate["status"] == "passed"
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["injected_events"] == [
            {"event": "dark_mode", "args": {"night": "yes"}}
        ]
        assert verdict["checkpoints"] == ["after-segment-0", "after-event-0"]
        assert [
            result["status"]
            for result in verdict["journey_results"][0]["results"]
        ] == ["PASSED", "PASSED"]
        assert verdict["l1"]["outcome"] == "inconclusive"
        assert search_text(before_layout) == "zzsentinelqx"

        if lane.role == "baseline":
            assert attempt["runner_exit_code"] == 0
            assert verdict["l2"]["outcome"] == "pass"
            assert verdict["l2"]["defect_class_hypothesis"] is None
            assert search_text(after_layout) == "zzsentinelqx"
        else:
            assert attempt["runner_exit_code"] == 1
            assert verdict["metric_context"]["seed_outcome"] == "caught"
            assert verdict["l2"]["outcome"] == "fail"
            assert verdict["l2"]["defect_class_hypothesis"] == "state_loss"
            assert search_text(after_layout) == "zzsentinelqxzzsentinelqx"
            assert any(
                "实际='zzsentinelqxzzsentinelqx'" in evidence["ref"]
                for evidence in verdict["l2"]["evidence"]
            )

    readme = (_V2_QUERY_RUN / "README.md").read_text(encoding="utf-8")
    assert "#54" in readme
    assert "aiverify_api35" in readme
    assert verify_manifest(_V2_QUERY_RUN) == []


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "id: v2-fixture-baseline-1",
            "id: fixture-baseline-1",
            "stale lane identities",
        ),
        (
            "evidence_dir: evidence/v2-fixture-baseline-1",
            "evidence_dir: evidence/fixture-baseline-1",
            "stale evidence directories",
        ),
        (
            "expected_oracle_defect_class: crash_stability",
            "expected_oracle_defect_class: state_loss",
            "matched metadata changed",
        ),
    ],
)
def test_rebaseline_manifest_rejects_version_or_metadata_drift(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    _, rebaseline_path = _write_versioned_fixture_manifests(tmp_path)
    rebaseline_path.write_text(
        rebaseline_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_manifest(rebaseline_path, repo_root=tmp_path)


def test_rebaseline_manifest_rejects_nested_historical_evidence_namespace(
    tmp_path: Path,
) -> None:
    _, rebaseline_path = _write_versioned_fixture_manifests(tmp_path)
    rebaseline_path.write_text(
        rebaseline_path.read_text(encoding="utf-8").replace(
            "evidence/v2-fixture-baseline-1",
            "evidence/fixture-baseline-1/rebaseline",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stale evidence directories"):
        load_manifest(rebaseline_path, repo_root=tmp_path)


def test_manifest_rejects_duplicate_evidence_directories(tmp_path: Path) -> None:
    _, rebaseline_path = _write_versioned_fixture_manifests(tmp_path)
    text = rebaseline_path.read_text(encoding="utf-8")
    duplicate = text[text.index("  - id:") :].replace(
        "v2-fixture-baseline-1", "v2-fixture-baseline-2", 1
    ).replace("repetition: 1", "repetition: 2", 1)
    rebaseline_path.write_text(text + duplicate, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate evidence directories"):
        load_manifest(rebaseline_path, repo_root=tmp_path)


def test_run_lane_invokes_public_runner_and_preserves_attempt(tmp_path: Path) -> None:
    manifest_path = _write_fixture_manifest(tmp_path)
    manifest = load_manifest(manifest_path, repo_root=tmp_path)
    runner = VerdictWritingRunner(_completed_verdict())

    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=runner,
        python_executable="python-fixture",
    )

    command = runner.calls[0]
    assert command[:3] == ["python-fixture", "-m", "aiverify.runner"]
    assert command[command.index("--device") + 1] == "emulator-5554"
    assert attempt.attempt_number == 1
    assert attempt.runner_exit_code == 0
    assert attempt.verdict_path.is_file()
    assert (attempt.directory / "attempt.json").is_file()
    assert verify_manifest(attempt.directory) == []


def test_run_lane_refuses_to_retry_accountable_outcome(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    runner = VerdictWritingRunner(_completed_verdict())
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=runner,
    )

    with pytest.raises(ValueError, match="accountable outcome must not be retried"):
        run_lane(
            manifest,
            lane_id="fixture-baseline-1",
            device="emulator-5554",
            workdir=tmp_path,
            runner=runner,
        )


def test_run_lane_refuses_retry_when_previous_attempt_checksum_is_invalid(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(
            _non_accountable_verdict("live_validation_preflight_failed"),
            returncode=2,
        ),
    )
    attempt.verdict_path.write_text(
        json.dumps(_non_accountable_verdict("journey_action_failed")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact_integrity"):
        run_lane(
            manifest,
            lane_id="fixture-baseline-1",
            device="emulator-5554",
            workdir=tmp_path,
            runner=VerdictWritingRunner(_completed_verdict()),
        )


def test_summary_derives_passed_control_from_runner_evidence(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
    )

    summary = build_summary(manifest)

    assert summary.planned_lanes == 1
    assert summary.first_attempt_accountable == 1
    assert summary.eventual_accountable == 1
    assert summary.retry_count == 0
    assert summary.control_outcomes == {"passed_control": 1}
    assert summary.defect_outcomes == {}
    assert summary.failure_classes == {}
    assert summary.total_seconds == 12.5
    assert summary.judge_seconds == 0.0


def test_summary_derives_l3_judge_time_from_runner_evidence(tmp_path: Path) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_l3_verdict()),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout",
    )
    write_manifest(attempt.directory)

    assert build_summary(manifest).judge_seconds == 2.5


def test_summary_preserves_non_accountable_first_attempt_before_retry(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(
            _non_accountable_verdict("live_validation_preflight_failed"), returncode=2
        ),
    )
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
        operational_interventions=["restarted emulator after failed preflight"],
    )

    summary = build_summary(manifest)

    assert summary.first_attempt_accountable == 0
    assert summary.eventual_accountable == 1
    assert summary.retry_count == 1
    assert summary.control_outcomes == {"passed_control": 1}
    assert summary.failure_classes == {"preflight_environment": 1}
    assert summary.total_seconds == 13.5
    assert summary.operational_interventions == 1


def test_summary_derives_expected_defect_catch(tmp_path: Path) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, role="defect"), repo_root=tmp_path
    )
    run_lane(
        manifest,
        lane_id="fixture-defect-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_defect_verdict(), returncode=1),
    )

    summary = build_summary(manifest)

    assert summary.control_outcomes == {}
    assert summary.defect_outcomes == {"caught": 1}


@pytest.mark.parametrize(
    ("reason", "expected_class"),
    [
        ("live_validation_preflight_failed", "preflight_environment"),
        ("journey_backend_error", "verification_agent_journey"),
        ("system_event_error", "system_event"),
        ("checkpoint_capture_error", "evidence_capture"),
        ("oracle_execution_error", "oracle_execution"),
    ],
)
def test_summary_classifies_non_accountable_failures(
    tmp_path: Path, reason: str, expected_class: str
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_non_accountable_verdict(reason), returncode=2),
    )

    summary = build_summary(manifest)

    assert summary.eventual_accountable == 0
    assert summary.control_outcomes == {}
    assert summary.failure_classes == {expected_class: 1}


def test_summary_fails_closed_when_lane_evidence_is_missing(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)

    with pytest.raises(ValueError, match="has no attempt evidence"):
        build_summary(manifest)


def test_summary_fails_closed_on_invalid_attempt_lineage(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
    )
    attempt.directory.rename(attempt.directory.with_name("attempt-2"))

    with pytest.raises(ValueError, match="invalid attempt lineage"):
        build_summary(manifest)


def test_summary_fails_closed_when_attempt_checksum_is_invalid(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
    )
    attempt.verdict_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact_integrity.*checksum mismatch"):
        build_summary(manifest)


def test_summary_fails_closed_on_runner_exit_contradiction(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict(), returncode=2),
    )

    with pytest.raises(ValueError, match="runner exit mismatch"):
        build_summary(manifest)


def test_summary_fails_closed_on_leaked_l3_expected_behavior(tmp_path: Path) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_l3_verdict()),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout\nSECRET_EXPECTED_BEHAVIOR",
    )
    write_manifest(attempt.directory)

    with pytest.raises(ValueError, match="leaks expected_behavior"):
        build_summary(manifest)


def test_summary_fails_closed_on_mismatched_l3_call_lineage(tmp_path: Path) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_l3_verdict()),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout",
    )
    judge = attempt.directory / "artifacts" / "l3-judge"
    (judge / "l3-judge-call-1.md").rename(judge / "l3-judge-call-2.md")
    write_manifest(attempt.directory)

    with pytest.raises(ValueError, match="input/output inventory is invalid"):
        build_summary(manifest)


def test_summary_fails_closed_when_l3_judge_output_contradicts_verdict(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_l3_verdict()),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout",
    )
    contradictory = _completed_l3_verdict()["l3"]
    contradictory["outcome"] = "fail"
    contradictory["defect_class_hypothesis"] = "ui_rendering"
    (
        attempt.directory
        / "artifacts"
        / "l3-judge"
        / "l3-judge-call-1.md"
    ).write_text(json.dumps(contradictory), encoding="utf-8")
    write_manifest(attempt.directory)

    with pytest.raises(ValueError, match="contradicts runner verdict"):
        build_summary(manifest)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda verdict: verdict["execution"].update(accounting_eligible=False),
            "accountability metadata contradicts",
        ),
        (
            lambda verdict: verdict["metric_context"].update(
                seed_id="different-seed"
            ),
            "metric_context seed_id mismatch",
        ),
        (
            lambda verdict: verdict["metric_context"].update(
                seed_outcome="not_accountable"
            ),
            "accountable verdict cannot use seed_outcome=not_accountable",
        ),
    ],
)
def test_summary_fails_closed_on_accountability_metadata_contradiction(
    tmp_path: Path, mutate, message: str
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    verdict = _completed_verdict()
    mutate(verdict)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict),
    )

    with pytest.raises(ValueError, match=message):
        build_summary(manifest)


def test_summary_fails_closed_when_non_accountable_verdict_accounts_oracle(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    verdict = _non_accountable_verdict("journey_action_failed")
    verdict["l1"] = {
        "level": "L1",
        "outcome": "fail",
        "defect_class_hypothesis": "crash_stability",
    }
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict, returncode=2),
    )

    with pytest.raises(ValueError, match="non-accountable verdict contains oracle"):
        build_summary(manifest)


@pytest.mark.parametrize("total_seconds", [None, "12.5", -1, float("inf")])
def test_summary_fails_closed_on_invalid_timing(
    tmp_path: Path, total_seconds: object
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    verdict = _completed_verdict()
    if total_seconds is None:
        verdict.pop("timing")
    else:
        verdict["timing"]["total_seconds"] = total_seconds
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict),
    )

    with pytest.raises(ValueError, match="timing.total_seconds"):
        build_summary(manifest)


@pytest.mark.parametrize("seconds", [None, "2.5", -1, float("inf")])
def test_summary_fails_closed_on_invalid_l3_judge_timing(
    tmp_path: Path, seconds: object
) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    verdict = _completed_l3_verdict()
    if seconds is None:
        verdict["timing"]["phases"] = []
    else:
        verdict["timing"]["phases"][0]["seconds"] = seconds
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout",
    )
    write_manifest(attempt.directory)

    with pytest.raises(ValueError, match="L3 judge timing"):
        build_summary(manifest)


def test_summary_fails_closed_on_duplicate_l3_judge_timing(tmp_path: Path) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    verdict = _completed_l3_verdict()
    verdict["timing"]["phases"].append(dict(verdict["timing"]["phases"][0]))
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict),
    )
    _write_l3_judge_artifacts(
        attempt.directory,
        prompt="PRODUCT_L3_SPEC\nobserved-layout",
    )
    write_manifest(attempt.directory)

    with pytest.raises(ValueError, match="L3 judge timing is missing or duplicated"):
        build_summary(manifest)


def test_summary_fails_closed_when_non_accountable_attempt_has_judge_timing(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, oracle_level="L3"), repo_root=tmp_path
    )
    verdict = _non_accountable_verdict("oracle_execution_error")
    verdict["timing"]["phases"] = [
        {"phase": "l3-judge", "kind": "oracle", "seconds": 2.5}
    ]
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict, returncode=2),
    )

    with pytest.raises(ValueError, match="non-accountable.*L3 judge timing"):
        build_summary(manifest)


def test_summary_fails_closed_on_unknown_failure_reason(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(
            _non_accountable_verdict("new_unclassified_failure"), returncode=2
        ),
    )

    with pytest.raises(ValueError, match="unsupported non-accountable failure reason"):
        build_summary(manifest)


def test_summary_renders_structured_and_markdown_outputs(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
    )

    summary = build_summary(manifest)
    payload = summary_to_dict(summary)
    markdown = render_markdown(summary, slice_id=manifest.slice_id)

    assert payload == {
        "planned_lanes": 1,
        "first_attempt_accountable": 1,
        "eventual_accountable": 1,
        "retry_count": 0,
        "control_outcomes": {"passed_control": 1},
        "defect_outcomes": {},
        "failure_classes": {},
        "total_seconds": 12.5,
        "judge_seconds": 0.0,
        "operational_interventions": 0,
    }
    assert "# M3 Verification Agent Reliability Summary" in markdown
    assert "| Planned lanes | 1 |" in markdown
    assert "| First-attempt accountable | 1 |" in markdown
    assert "| Eventual accountable | 1 |" in markdown
    assert "| L3 judge time (seconds) | 0.0 |" in markdown
    assert "| `passed_control` | 1 |" in markdown
    assert "benchmark-wide detection-rate claim" in markdown


def test_plan_reports_pending_retryable_and_complete_lanes(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    assert plan_lanes(manifest) == [
        {
            "lane_id": "fixture-baseline-1",
            "role": "baseline",
            "repetition": 1,
            "attempts": 0,
            "status": "pending",
        }
    ]

    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(
            _non_accountable_verdict("journey_backend_error"), returncode=2
        ),
    )
    assert plan_lanes(manifest)[0]["status"] == "retryable"

    run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(_completed_verdict()),
    )
    assert plan_lanes(manifest)[0]["status"] == "accountable_complete"


def test_cli_plan_prints_machine_readable_schedule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = _write_fixture_manifest(tmp_path)

    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "plan",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["lane_id"] == "fixture-baseline-1"
    assert payload[0]["status"] == "pending"


def test_cli_plan_writes_durable_machine_readable_schedule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = _write_fixture_manifest(tmp_path)
    output_path = tmp_path / "plan.json"

    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "plan",
            "--json-output",
            str(output_path),
        ]
    ) == 0

    assert capsys.readouterr().out == ""
    assert json.loads(output_path.read_text(encoding="utf-8")) == [
        {
            "lane_id": "fixture-baseline-1",
            "role": "baseline",
            "repetition": 1,
            "attempts": 0,
            "status": "pending",
        }
    ]


def test_cli_plan_rejects_stale_evidence_in_rebaseline_namespace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, rebaseline_path = _write_versioned_fixture_manifests(tmp_path)
    stale_dir = tmp_path / "evidence" / "v2-fixture-baseline-1"
    stale_dir.mkdir(parents=True)
    (stale_dir / "foreign-attempt.json").write_text("{}", encoding="utf-8")

    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--manifest",
            str(rebaseline_path),
            "plan",
        ]
    ) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "invalid_evidence"


def test_cli_progress_writes_partial_rebaseline_aggregate(tmp_path: Path) -> None:
    output_path = tmp_path / "progress.json"

    assert main(
        [
            "--repo-root",
            str(_ROOT),
            "--manifest",
            str(_REBASELINE_MANIFEST),
            "progress",
            "--json-output",
            str(output_path),
        ]
    ) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    manifest = load_manifest(_REBASELINE_MANIFEST, repo_root=_ROOT)
    assert payload == progress_to_dict(build_progress(manifest))


def test_partial_progress_keeps_outcomes_and_execution_failures_separate(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(
        _write_progress_fixture_manifest(tmp_path), repo_root=tmp_path
    )
    verdicts = {
        "progress-baseline-1": (_completed_verdict(), 0),
        "progress-baseline-2": (
            _completed_verdict_with_failure("l1", "crash_stability"),
            1,
        ),
        "progress-defect-1": (_completed_verdict(), 0),
        "progress-defect-2": (
            _completed_verdict_with_failure("l2", "state_loss"),
            1,
        ),
        "progress-defect-3": (
            _completed_verdict_with_failure("l1", "state_loss"),
            1,
        ),
        "progress-defect-4": (
            _non_accountable_verdict("journey_action_failed"),
            2,
        ),
    }
    for lane_id, (verdict, exit_code) in verdicts.items():
        run_lane(
            manifest,
            lane_id=lane_id,
            device="emulator-5554",
            workdir=tmp_path,
            runner=VerdictWritingRunner(verdict, returncode=exit_code),
        )

    payload = progress_to_dict(build_progress(manifest))

    assert payload["planned_lanes"] == 7
    assert payload["pending_lanes"] == 1
    assert payload["pending_lane_ids"] == ["progress-defect-5"]
    assert payload["eventual_accountable"] == 5
    assert payload["control_outcomes"] == {
        "false_positive": 1,
        "passed_control": 1,
    }
    assert payload["defect_outcomes"] == {
        "missed": 1,
        "wrong_defect_class": 1,
        "wrong_oracle": 1,
    }
    assert payload["failure_classes"] == {"verification_agent_journey": 1}


def test_committed_summary_is_derived_from_committed_attempt_evidence() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    summary = build_summary(manifest)
    run_record = (
        _ROOT
        / "docs"
        / "runs"
        / "2026-07-13-m3-search-card-l3-reliability"
    )

    assert json.loads((run_record / "summary.json").read_text(encoding="utf-8")) == (
        summary_to_dict(summary)
    )
    assert (run_record / "summary.md").read_text(encoding="utf-8") == render_markdown(
        summary, slice_id=manifest.slice_id
    )
    assert summary.planned_lanes == 30
    assert summary.first_attempt_accountable == 24
    assert summary.eventual_accountable == 27
    assert summary.retry_count == 6
    assert summary.control_outcomes == {"passed_control": 15}
    assert summary.defect_outcomes == {"caught": 12}


def test_final_audit_derives_thresholds_oracle_breakdown_and_lane_results() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)

    report = build_audited_report(
        manifest,
        environment_path=_FINAL_RUN / "environment.json",
    )

    assert report.inventory == {
        "selected_seeds": 5,
        "lane_roles": 2,
        "repetitions_per_role": 3,
        "planned_lanes": 30,
        "formal_attempts": 36,
        "evidence_packages": 5,
    }
    assert report.criteria == {
        "eventual_accountability": {
            "status": "failed",
            "actual": 27,
            "required_minimum": 29,
        },
        "zero_accountable_baseline_false_positives": {
            "status": "passed",
            "actual": 0,
            "required_maximum": 0,
        },
        "accountable_defect_consistency": {
            "status": "passed",
            "actual": 12,
            "required": 12,
        },
        "m3_overall": {"status": "failed"},
    }
    assert report.oracle_breakdown == {
        "L1": {
            "planned": 12,
            "eventual_accountable": 10,
            "passed_controls": 6,
            "caught_defects": 4,
            "non_accountable": 2,
        },
        "L2": {
            "planned": 12,
            "eventual_accountable": 12,
            "passed_controls": 6,
            "caught_defects": 6,
            "non_accountable": 0,
        },
        "L3": {
            "planned": 6,
            "eventual_accountable": 5,
            "passed_controls": 3,
            "caught_defects": 2,
            "non_accountable": 1,
        },
    }
    assert len(report.lane_results) == 30
    assert {row["lane_id"] for row in report.lane_results} == {
        lane.lane_id for lane in manifest.lanes
    }
    assert report.execution_identity["devices"] == ["emulator-5554"]
    assert report.execution_identity["preflight_statuses"] == {
        "failed": 2,
        "passed": 34,
    }
    assert len(report.evidence_packages) == 5
    assert all(row["checksum_status"] == "verified" for row in report.evidence_packages)


def test_committed_final_audit_documents_are_generated_from_one_model() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    report = build_audited_report(
        manifest,
        environment_path=_FINAL_RUN / "environment.json",
    )

    assert json.loads((_FINAL_RUN / "summary.json").read_text(encoding="utf-8")) == (
        audited_report_to_dict(report)
    )
    assert (_FINAL_RUN / "report.md").read_text(encoding="utf-8") == (
        render_audited_markdown(report)
    )
    markdown = render_audited_markdown(report)
    assert "M3 overall | **FAILED**" in markdown
    assert "27 / 30" in markdown
    assert "Wikipedia" in markdown
    assert "five-seed, 30-lane" in markdown
    assert "fully unattended" in markdown
    assert "benchmark-wide" in markdown


def test_final_audit_fails_closed_on_environment_device_mismatch(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    environment = json.loads(
        (_FINAL_RUN / "environment.json").read_text(encoding="utf-8")
    )
    environment["device"]["serial"] = "different-device"
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps(environment), encoding="utf-8")

    with pytest.raises(ValueError, match="device does not match"):
        build_audited_report(manifest, environment_path=environment_path)


def test_final_audit_fails_closed_on_root_evidence_checksum_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    verified = verify_manifest

    def fail_anr_package(path: Path) -> list[str]:
        if Path(path).name == "2026-07-13-m3-anr-reliability":
            return ["checksum mismatch: retained evidence"]
        return verified(path)

    monkeypatch.setattr(m3_audit, "verify_manifest", fail_anr_package)

    with pytest.raises(ValueError, match="artifact_integrity for evidence package"):
        build_audited_report(
            manifest,
            environment_path=_FINAL_RUN / "environment.json",
        )


def test_final_report_renders_passed_decision_from_model() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    failed = build_audited_report(
        manifest,
        environment_path=_FINAL_RUN / "environment.json",
    )
    passed_summary = replace(
        failed.summary,
        first_attempt_accountable=30,
        eventual_accountable=30,
    )
    passed = replace(
        failed,
        summary=passed_summary,
        criteria={
            **failed.criteria,
            "eventual_accountability": {
                "status": "passed",
                "actual": 30,
                "required_minimum": 29,
            },
            "m3_overall": {"status": "passed"},
        },
    )

    markdown = render_audited_markdown(passed)

    assert "M3 overall | **PASSED**" in markdown
    assert "All required M3 criteria passed" in markdown
    assert "criterion is unmet" not in markdown


@pytest.mark.parametrize(
    ("gate_status", "reason", "message"),
    [
        ("failed", None, "failed gate cannot have accountable verdict"),
        ("passed", "live_validation_preflight_failed", "preflight reason mismatch"),
    ],
)
def test_final_audit_fails_closed_on_gate_verdict_contradiction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_status: str,
    reason: str | None,
    message: str,
) -> None:
    manifest = load_manifest(_write_fixture_manifest(tmp_path), repo_root=tmp_path)
    verdict = (
        _completed_verdict()
        if reason is None
        else _non_accountable_verdict(reason)
    )
    verdict["preflight"] = {"live_validation_gate": {"status": gate_status}}
    attempt = run_lane(
        manifest,
        lane_id="fixture-baseline-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict, returncode=0 if reason is None else 2),
    )
    (attempt.directory / "live-validation-gate.json").write_text(
        json.dumps({"device": "emulator-5554", "status": gate_status}),
        encoding="utf-8",
    )
    write_manifest(attempt.directory)
    environment = json.loads(
        (_FINAL_RUN / "environment.json").read_text(encoding="utf-8")
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps(environment), encoding="utf-8")
    monkeypatch.setattr(m3_audit, "_validate_final_inventory", lambda _: None)
    monkeypatch.setattr(
        m3_audit,
        "_verified_evidence_packages",
        lambda _: [{"path": "fixture", "checksum_entries": 1, "checksum_status": "verified"}],
    )

    with pytest.raises(ValueError, match=message):
        build_audited_report(manifest, environment_path=environment_path)


@pytest.mark.parametrize(
    ("oracle_verdicts", "runner_exit", "expected_outcome"),
    [
        ({}, 0, "missed"),
        ({"l2": {"outcome": "fail", "defect_class_hypothesis": "state_loss"}}, 1, "wrong_oracle"),
        (
            {"l1": {"outcome": "fail", "defect_class_hypothesis": "state_loss"}},
            1,
            "wrong_defect_class",
        ),
    ],
)
def test_final_audit_keeps_accountable_defect_mismatch_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    oracle_verdicts: dict,
    runner_exit: int,
    expected_outcome: str,
) -> None:
    manifest = load_manifest(
        _write_fixture_manifest(tmp_path, role="defect"), repo_root=tmp_path
    )
    verdict = _completed_verdict()
    verdict.update(oracle_verdicts)
    verdict["preflight"] = {"live_validation_gate": {"status": "passed"}}
    attempt = run_lane(
        manifest,
        lane_id="fixture-defect-1",
        device="emulator-5554",
        workdir=tmp_path,
        runner=VerdictWritingRunner(verdict, returncode=runner_exit),
    )
    (attempt.directory / "live-validation-gate.json").write_text(
        json.dumps({"device": "emulator-5554", "status": "passed"}),
        encoding="utf-8",
    )
    write_manifest(attempt.directory)
    environment = json.loads(
        (_FINAL_RUN / "environment.json").read_text(encoding="utf-8")
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps(environment), encoding="utf-8")
    monkeypatch.setattr(m3_audit, "_validate_final_inventory", lambda _: None)
    monkeypatch.setattr(
        m3_audit,
        "_verified_evidence_packages",
        lambda _: [{"path": "fixture", "checksum_entries": 1, "checksum_status": "verified"}],
    )

    report = build_audited_report(manifest, environment_path=environment_path)

    assert report.lane_results[0]["outcome"] == expected_outcome
    assert report.criteria["accountable_defect_consistency"] == {
        "status": "failed",
        "actual": 0,
        "required": 1,
    }
    isolated_defect_failure = replace(
        report,
        criteria={
            **report.criteria,
            "eventual_accountability": {
                "status": "passed",
                "actual": 1,
                "required_minimum": 1,
            },
            "m3_overall": {"status": "failed"},
        },
    )
    markdown = render_audited_markdown(isolated_defect_failure)
    assert "accountable defect consistency (0 / 1)" in markdown
    assert "because eventual accountability" not in markdown


def test_committed_oversized_state_defects_contain_expected_l1_signal() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    defect_lanes = [
        lane
        for lane in manifest.lanes
        if lane.seed_id == "wikipedia-process-death-03-oversized-saved-state"
        and lane.role == "defect"
    ]

    assert len(defect_lanes) == 3
    for lane in defect_lanes:
        final_attempt = sorted(lane.evidence_dir.glob("attempt-*"))[-1]
        verdict = json.loads(
            (final_attempt / "verdict.json").read_text(encoding="utf-8")
        )
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["l1"]["outcome"] == "fail"
        assert verdict["l1"]["defect_class_hypothesis"] == "crash_stability"
        assert any(
            "TransactionTooLargeException" in evidence["ref"]
            for evidence in verdict["l1"]["evidence"]
        )


def test_committed_query_duplication_lanes_match_the_l2_contract() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    lanes = [
        lane
        for lane in manifest.lanes
        if lane.seed_id == "wikipedia-config-change-02-query-duplication"
    ]

    assert len(lanes) == 6
    assert {lane.run_spec for lane in lanes} == {
        _ROOT
        / "bench"
        / "goldset"
        / "run-specs"
        / "wikipedia-config-change-02-query-duplication.yaml"
    }
    for lane in lanes:
        final_attempt = sorted(lane.evidence_dir.glob("attempt-*"))[-1]
        verdict = json.loads(
            (final_attempt / "verdict.json").read_text(encoding="utf-8")
        )
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["l1"]["outcome"] == "inconclusive"
        if lane.role == "baseline":
            assert verdict["l2"]["outcome"] == "pass"
        else:
            assert verdict["l2"]["outcome"] == "fail"
            assert verdict["l2"]["defect_class_hypothesis"] == "state_loss"
            assert "zzsentinelqxzzsentinelqx" in verdict["l2"]["evidence"][0][
                "ref"
            ]


def test_committed_swallowed_back_lanes_match_the_l2_contract() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    run_spec = load_run_spec(
        _ROOT
        / "bench"
        / "goldset"
        / "run-specs"
        / "wikipedia-navigation-02-back-button-swallowed.yaml"
    )
    expected_action = run_spec.scenario.user_actions[1]
    lanes = [
        lane
        for lane in manifest.lanes
        if lane.seed_id == "wikipedia-navigation-02-back-button-swallowed"
    ]

    assert len(lanes) == 6
    assert {lane.run_spec for lane in lanes} == {
        _ROOT
        / "bench"
        / "goldset"
        / "run-specs"
        / "wikipedia-navigation-02-back-button-swallowed.yaml"
    }
    for lane in lanes:
        final_attempt = sorted(lane.evidence_dir.glob("attempt-*"))[-1]
        verdict = json.loads(
            (final_attempt / "verdict.json").read_text(encoding="utf-8")
        )
        journey = json.loads(
            next(
                final_attempt.glob(
                    "artifacts/*/codex-journey-result.json"
                )
            ).read_text(encoding="utf-8")
        )
        layout = json.loads(
            (
                final_attempt / "artifacts" / "after-event-0" / "layout.json"
            ).read_text(encoding="utf-8")
        )
        nodes_by_resource_id = {
            node["resource-id"]: node
            for node in layout
            if isinstance(node, dict) and node.get("resource-id")
        }
        terminal_action = journey["results"][-1]
        assert terminal_action["action"] == expected_action
        assert terminal_action["commands"][-1].endswith(
            "shell input keyevent KEYCODE_BACK"
        )
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["l1"]["outcome"] == "inconclusive"
        if lane.role == "baseline":
            assert verdict["l2"]["outcome"] == "pass"
            assert "search_card" in nodes_by_resource_id
        else:
            assert verdict["l2"]["outcome"] == "fail"
            assert verdict["l2"]["defect_class_hypothesis"] == "state_loss"
            assert "search_card" not in nodes_by_resource_id
            assert nodes_by_resource_id["search_src_text"]["text"] == "zznavbackqx"


def test_committed_search_card_lanes_match_the_live_l3_contract() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    run_spec = load_run_spec(
        _ROOT
        / "bench"
        / "goldset"
        / "run-specs"
        / "wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml"
    )
    lanes = [
        lane
        for lane in manifest.lanes
        if lane.seed_id == "wikipedia-ui-rendering-02-search-card-copy-mismatch"
    ]

    assert len(lanes) == 6
    assert {lane.expected_oracle_level for lane in lanes} == {"L3"}
    assert {lane.expected_oracle_defect_class for lane in lanes} == {"ui_rendering"}
    assert all("l3-repeatability" not in str(lane.evidence_dir) for lane in lanes)
    for lane in lanes:
        attempts = sorted(lane.evidence_dir.glob("attempt-*"))
        final_attempt = attempts[-1]
        verdict = json.loads(
            (final_attempt / "verdict.json").read_text(encoding="utf-8")
        )
        if lane.lane_id == "search-card-defect-3":
            assert len(attempts) == 2
            assert verdict["execution"]["accounting_eligible"] is False
            assert verdict["execution"]["reason"] == "journey_action_incomplete"
            assert verdict["l3"] is None
            continue

        layout_path = final_attempt / "artifacts" / "after-segment-0" / "layout.json"
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        nodes = {
            node["resource-id"]: node
            for node in layout
            if isinstance(node, dict) and node.get("resource-id")
        }
        prompt = (
            final_attempt
            / "artifacts"
            / "l3-judge"
            / "l3-judge-call-1.prompt.md"
        ).read_text(encoding="utf-8")
        journey = json.loads(
            next(
                final_attempt.glob("artifacts/*/codex-journey-result.json")
            ).read_text(encoding="utf-8")
        )
        assert verdict["execution"]["accounting_eligible"] is True
        assert verdict["l1"]["outcome"] == "inconclusive"
        assert verdict["l2"]["outcome"] == "inconclusive"
        assert any(
            phase["phase"] == "l3-judge" and phase["seconds"] > 0
            for phase in verdict["timing"]["phases"]
        )
        assert "search_card" in nodes
        assert run_spec.scenario.l3_spec in prompt
        assert layout_path.read_text(encoding="utf-8") in prompt
        assert run_spec.scenario.expected_behavior not in prompt
        assert run_spec.diff is not None
        assert run_spec.diff.read_text(encoding="utf-8") not in prompt
        assert journey["results"][-1]["action"] == run_spec.scenario.user_actions[0]
        if lane.role == "baseline":
            assert verdict["l3"]["outcome"] == "pass"
            assert verdict["l3"]["defect_class_hypothesis"] is None
            assert nodes["search_text_view"]["text"].startswith("Search")
        else:
            assert verdict["l3"]["outcome"] == "fail"
            assert verdict["l3"]["defect_class_hypothesis"] == "ui_rendering"
            assert nodes["search_text_view"]["text"] == (
                "Track what you've been reading here."
            )


def _write_fixture_manifest(
    tmp_path: Path, *, role: str = "baseline", oracle_level: str = "L1"
) -> Path:
    run_spec = tmp_path / "run-spec.yaml"
    run_spec.write_text(
        """\
host_project: .
apk_glob: "*.apk"
package: fixture.package
scenario:
  id: fixture-seed
  user_actions:
    - observe fixture
  system_events: []
  assertions: []
  l3_spec: PRODUCT_L3_SPEC
  expected_behavior: SECRET_EXPECTED_BEHAVIOR
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"""\
schema_version: 1
slice_id: fixture-reliability
max_attempts_per_lane: 2
lanes:
  - id: fixture-{role}-1
    seed_id: fixture-seed
    role: {role}
    repetition: 1
    run_spec: run-spec.yaml
    evidence_dir: evidence/fixture-{role}-1
    expected_oracle_level: {oracle_level}
    expected_oracle_defect_class: {"ui_rendering" if oracle_level == "L3" else "crash_stability"}
""",
        encoding="utf-8",
    )
    return manifest


def _write_versioned_fixture_manifests(tmp_path: Path) -> tuple[Path, Path]:
    historical = _write_fixture_manifest(tmp_path)
    rebaseline = tmp_path / "manifest-v2.yaml"
    rebaseline.write_text(
        """\
schema_version: 2
slice_id: fixture-reliability-v2
comparison_manifest: manifest.yaml
max_attempts_per_lane: 2
lanes:
  - id: v2-fixture-baseline-1
    seed_id: fixture-seed
    role: baseline
    repetition: 1
    run_spec: run-spec.yaml
    evidence_dir: evidence/v2-fixture-baseline-1
    expected_oracle_level: L1
    expected_oracle_defect_class: crash_stability
""",
        encoding="utf-8",
    )
    return historical, rebaseline


def _write_progress_fixture_manifest(tmp_path: Path) -> Path:
    _write_fixture_manifest(tmp_path)
    lanes = []
    for role, repetition in (
        ("baseline", 1),
        ("baseline", 2),
        ("defect", 1),
        ("defect", 2),
        ("defect", 3),
        ("defect", 4),
        ("defect", 5),
    ):
        lane_id = f"progress-{role}-{repetition}"
        lanes.append(
            f"""\
  - id: {lane_id}
    seed_id: fixture-seed
    role: {role}
    repetition: {repetition}
    run_spec: run-spec.yaml
    evidence_dir: evidence/{lane_id}
    expected_oracle_level: L1
    expected_oracle_defect_class: crash_stability"""
        )
    manifest = tmp_path / "progress-manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "slice_id: progress-fixture",
                "max_attempts_per_lane: 2",
                "lanes:",
                *lanes,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return manifest


def _completed_verdict() -> dict:
    return {
        "scenario": "fixture-seed",
        "execution": {
            "status": "completed",
            "accounting_eligible": True,
            "reason": None,
        },
        "metric_context": {
            "seed_id": "fixture-seed",
            "seed_outcome": "missed",
        },
        "l1": {
            "level": "L1",
            "outcome": "inconclusive",
            "defect_class_hypothesis": None,
        },
        "l2": None,
        "l3": None,
        "timing": {"total_seconds": 12.5, "phases": []},
    }


def _completed_verdict_with_failure(level: str, defect_class: str) -> dict:
    verdict = _completed_verdict()
    verdict[level] = {
        "level": level.upper(),
        "outcome": "fail",
        "defect_class_hypothesis": defect_class,
    }
    return verdict


def _completed_l3_verdict() -> dict:
    verdict = _completed_verdict()
    verdict["metric_context"]["seed_outcome"] = "passed_control"
    verdict["l2"] = {
        "level": "L2",
        "outcome": "inconclusive",
        "defect_class_hypothesis": None,
    }
    verdict["l3"] = {
        "verdict_id": "L3-deadbeef",
        "level": "L3",
        "outcome": "pass",
        "defect_class_hypothesis": None,
        "trigger_steps": ["observe fixture"],
        "evidence": [
            {
                "type": "llm_reasoning",
                "ref": "observed-layout",
                "note": "fixture matches product spec",
            }
        ],
        "confidence": 0.9,
    }
    verdict["checkpoints"] = ["after-segment-0"]
    verdict["timing"]["phases"] = [
        {"phase": "l3-judge", "kind": "oracle", "seconds": 2.5}
    ]
    return verdict


def _write_l3_judge_artifacts(attempt_dir: Path, *, prompt: str) -> None:
    checkpoint = attempt_dir / "artifacts" / "after-segment-0"
    checkpoint.mkdir(parents=True)
    (checkpoint / "layout.json").write_text("observed-layout", encoding="utf-8")
    judge = attempt_dir / "artifacts" / "l3-judge"
    judge.mkdir()
    (judge / "l3-judge-call-1.prompt.md").write_text(prompt, encoding="utf-8")
    (judge / "l3-judge-call-1.md").write_text(
        json.dumps(_completed_l3_verdict()["l3"]), encoding="utf-8"
    )
    (judge / "l3-judge-call-1.events.jsonl").write_text(
        '{"type":"turn.completed"}\n', encoding="utf-8"
    )


def _non_accountable_verdict(reason: str) -> dict:
    return {
        "scenario": "fixture-seed",
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": reason,
        },
        "metric_context": {"seed_id": "fixture-seed", "seed_outcome": "not_accountable"},
        "l1": None,
        "l2": None,
        "l3": None,
        "timing": {"total_seconds": 1.0, "phases": []},
    }


def _defect_verdict() -> dict:
    verdict = _completed_verdict()
    verdict["metric_context"]["seed_outcome"] = "caught"
    verdict["l1"] = {
        "level": "L1",
        "outcome": "fail",
        "defect_class_hypothesis": "crash_stability",
    }
    return verdict
