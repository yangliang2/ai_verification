"""M3 Verification Agent execution-reliability tracer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.bench.m3_reliability import (
    build_summary,
    load_manifest,
    main,
    plan_lanes,
    render_markdown,
    run_lane,
    summary_to_dict,
)
from aiverify.bench.run_record_checksums import verify_manifest
from aiverify.runner.command import CommandResult, CommandRunner


_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "bench" / "goldset" / "m3-reliability-slice.yaml"


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


def test_manifest_defines_six_anr_lanes() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)

    assert manifest.slice_id == "m3-verification-agent-reliability"
    assert manifest.max_attempts_per_lane == 2
    assert len(manifest.lanes) == 6
    assert {(lane.role, lane.repetition) for lane in manifest.lanes} == {
        ("baseline", 1),
        ("baseline", 2),
        ("baseline", 3),
        ("defect", 1),
        ("defect", 2),
        ("defect", 3),
    }
    assert {lane.seed_id for lane in manifest.lanes} == {
        "wikipedia-coroutine-concurrency-03-main-thread-anr"
    }
    assert {lane.expected_oracle_level for lane in manifest.lanes} == {"L1"}
    assert {lane.expected_oracle_defect_class for lane in manifest.lanes} == {
        "crash_stability"
    }
    assert all(lane.run_spec.is_file() for lane in manifest.lanes)


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
        "operational_interventions": 0,
    }
    assert "# M3 Verification Agent Reliability Summary" in markdown
    assert "| Planned lanes | 1 |" in markdown
    assert "| First-attempt accountable | 1 |" in markdown
    assert "| Eventual accountable | 1 |" in markdown
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


def test_committed_summary_is_derived_from_committed_attempt_evidence() -> None:
    manifest = load_manifest(_MANIFEST, repo_root=_ROOT)
    summary = build_summary(manifest)
    run_record = _ROOT / "docs" / "runs" / "2026-07-13-m3-anr-reliability"

    assert json.loads((run_record / "summary.json").read_text(encoding="utf-8")) == (
        summary_to_dict(summary)
    )
    assert (run_record / "summary.md").read_text(encoding="utf-8") == render_markdown(
        summary, slice_id=manifest.slice_id
    )


def _write_fixture_manifest(tmp_path: Path, *, role: str = "baseline") -> Path:
    run_spec = tmp_path / "run-spec.yaml"
    run_spec.write_text("scenario: {}\n", encoding="utf-8")
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
    expected_oracle_level: L1
    expected_oracle_defect_class: crash_stability
""",
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
