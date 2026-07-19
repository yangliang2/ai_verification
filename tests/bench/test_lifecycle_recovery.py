from __future__ import annotations

import json
from pathlib import Path

from aiverify.bench.lifecycle_recovery import (
    LifecycleRecoveryContract,
    judge_lifecycle_recovery,
    judge_lifecycle_recovery_run,
    load_lifecycle_recovery_contract,
)
from aiverify.runner.run_spec import load_run_spec


CONTRACT = LifecycleRecoveryContract(
    sentinel="AIVERIFY-ISSUE-71-SENTINEL",
    pre_restore_schema="1",
    restored_schema="2",
    pre_restore_revision="41",
    restored_revision="42",
    pre_restore_migration="PENDING_V1_TO_V2",
    restored_migration="MIGRATED_V1_TO_V2",
    reset_sentinel="UNINITIALIZED",
)

_SLICE = (
    Path(__file__).resolve().parents[2]
    / "bench"
    / "capability-slices"
    / "lifecycle-recovery"
)


def _layout(
    *,
    sentinel: str,
    schema: str,
    revision: str,
    migration: str,
) -> str:
    return json.dumps(
        [
            {"resource-id": "fixture_sentinel", "text": sentinel},
            {"resource-id": "fixture_schema_version", "text": schema},
            {"resource-id": "fixture_revision", "text": revision},
            {"resource-id": "fixture_migration_status", "text": migration},
        ]
    )


PRE_RESTORE = _layout(
    sentinel=CONTRACT.sentinel,
    schema="1",
    revision="41",
    migration="PENDING_V1_TO_V2",
)


def test_oracle_supports_exact_restoration_after_all_lifecycle_boundaries() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=_layout(
            sentinel=CONTRACT.sentinel,
            schema="2",
            revision="42",
            migration="MIGRATED_V1_TO_V2",
        ),
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["classification"] == "correct_restoration"
    assert verdict["accountable"] is True
    assert verdict["observations"]["backup_restore"] == {
        "sentinel": "AIVERIFY-ISSUE-71-SENTINEL",
        "schema_version": "2",
        "revision": "42",
        "migration_status": "MIGRATED_V1_TO_V2",
    }


def test_oracle_rejects_a_crash_even_when_restored_ui_looks_correct() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=_layout(
            sentinel=CONTRACT.sentinel,
            schema="2",
            revision="42",
            migration="MIGRATED_V1_TO_V2",
        ),
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=True,
    )

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["classification"] == "crash"
    assert verdict["accountable"] is True


def test_oracle_rejects_state_loss_at_rotation_boundary() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout="[]",
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=_layout(
            sentinel=CONTRACT.sentinel,
            schema="2",
            revision="42",
            migration="MIGRATED_V1_TO_V2",
        ),
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["classification"] == "state_loss"
    assert verdict["accountable"] is True


def test_oracle_rejects_silent_reset_after_successful_restore_transport() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=_layout(
            sentinel="UNINITIALIZED",
            schema="2",
            revision="0",
            migration="RESET_DEFAULTS",
        ),
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["classification"] == "silent_reset"
    assert verdict["accountable"] is True


def test_oracle_rejects_restored_but_unmigrated_stale_state() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=PRE_RESTORE,
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["classification"] == "stale_state"
    assert verdict["accountable"] is True


def test_oracle_fails_closed_when_process_identity_did_not_change() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout=_layout(
            sentinel=CONTRACT.sentinel,
            schema="2",
            revision="42",
            migration="MIGRATED_V1_TO_V2",
        ),
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["111"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["classification"] == "non_accountable"
    assert verdict["reason"] == "process_identity_missing_or_unchanged"
    assert verdict["accountable"] is False


def test_oracle_fails_closed_when_restore_layout_is_invalid() -> None:
    verdict = judge_lifecycle_recovery(
        contract=CONTRACT,
        initial_layout=PRE_RESTORE,
        rotated_layout=PRE_RESTORE,
        process_restored_layout=PRE_RESTORE,
        backup_restored_layout="not-json",
        process_event={
            "status": "passed",
            "evidence": {"before_pids": ["111"], "after_pids": ["222"]},
        },
        backup_event={
            "status": "passed",
            "evidence": {
                "transport": "com.android.localtransport/.LocalTransport",
                "backup_status": "success",
                "restore_status": "success",
                "restore_token": "1",
            },
        },
        crash_detected=False,
    )

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["classification"] == "non_accountable"
    assert verdict["reason"] == "layout_evidence_missing_or_invalid"
    assert verdict["accountable"] is False


def test_baseline_and_candidate_run_specs_share_one_lifecycle_journey() -> None:
    baseline = load_run_spec(_SLICE / "run-specs/baseline.yaml")
    candidate = load_run_spec(_SLICE / "run-specs/candidate.yaml")

    assert baseline.host_project.resolve() == Path(__file__).resolve().parents[2]
    assert baseline.scenario.id == candidate.scenario.id
    assert baseline.scenario.user_actions == candidate.scenario.user_actions
    assert baseline.scenario.system_events == candidate.scenario.system_events
    assert baseline.scenario.assertions == candidate.scenario.assertions
    assert [event.event for event in baseline.scenario.system_events] == [
        "rotate",
        "process_death",
        "backup_restore",
    ]
    assert baseline.scenario.l2_boundary_index == 2
    assert baseline.diff is None
    assert candidate.diff.resolve() == _SLICE / "patches/stale-migration-guard.patch"
    assert [assertion.expected for assertion in baseline.scenario.assertions] == [
        "AIVERIFY-ISSUE-71-SENTINEL",
        "2",
        "42",
        "MIGRATED_V1_TO_V2",
    ]


def test_committed_contract_loads_stable_fixture_literals() -> None:
    contract = load_lifecycle_recovery_contract(_SLICE / "contract.json")

    assert contract == CONTRACT


def test_run_oracle_fails_closed_when_authoritative_record_is_missing(
    tmp_path: Path,
) -> None:
    verdict = judge_lifecycle_recovery_run(
        run_dir=tmp_path,
        contract_path=_SLICE / "contract.json",
    )

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["classification"] == "non_accountable"
    assert verdict["reason"] == "run_evidence_missing_or_invalid"
    assert verdict["accountable"] is False
    assert "execution-record.json" in verdict["evidence_error"]


def test_run_oracle_fails_closed_when_provenance_binding_is_missing(
    tmp_path: Path,
) -> None:
    started_at = "2026-07-19T12:00:00+00:00"
    timing = {
        "started_at": started_at,
        "finished_at": "2026-07-19T12:00:01+00:00",
        "total_seconds": 1.0,
        "phases": [],
    }
    execution = {
        "status": "completed",
        "accounting_eligible": True,
        "reason": None,
        "message": None,
    }
    (tmp_path / "execution-record.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "attempt_id": "test-attempt",
                "scenario": "lifecycle-recovery-matched-journey",
                "lifecycle_state": "completed",
                "started_at": started_at,
                "finished_at": timing["finished_at"],
                "execution": execution,
                "process_outcome": {"exit_code": 0},
                "timing": timing,
                "phase_errors": [],
                "evidence_refs": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "verdict.json").write_text(
        json.dumps(
            {
                "scenario": "lifecycle-recovery-matched-journey",
                "execution": execution,
                "execution_provenance": None,
            }
        ),
        encoding="utf-8",
    )

    verdict = judge_lifecycle_recovery_run(
        run_dir=tmp_path,
        contract_path=_SLICE / "contract.json",
    )

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["reason"] == "run_evidence_missing_or_invalid"
    assert "provenance binding" in verdict["evidence_error"]
