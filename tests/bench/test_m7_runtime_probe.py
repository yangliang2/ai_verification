from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.bench.m7_runtime_probe import (
    RuntimeProbeError,
    admit_runtime_probe,
    evaluate_temporal_oracle,
    load_runtime_manifest,
    self_validate_project_schema,
    self_validate_schema,
)

_ROOT = Path(__file__).parents[2]
_MANIFEST = _ROOT / "bench/runtime-probes/synchronous-weather/runtime-probe.json"
_PROJECT_MANIFEST = _ROOT / "bench/runtime-probes/synchronous-weather-project/runtime-probe.json"


def test_runtime_manifest_schema_freezes_six_lane_change_pair() -> None:
    self_validate_schema()
    manifest = load_runtime_manifest(_MANIFEST)

    assert manifest.probe_id == "m7-r1-synchronous-weather-v1"
    assert manifest.document["status"] == "frozen"
    assert manifest.document["policy"]["planned_lanes"] == 6
    assert manifest.document["policy"]["repetitions_per_cell"] == 3
    assert [cell["cell_id"] for cell in manifest.cells] == [
        "change-defect",
        "change-control",
    ]
    assert manifest.document["claim_boundary"]["local_only"] is True


def test_runtime_admission_rejects_before_device_side_effect_when_build_missing(
    tmp_path: Path,
) -> None:
    admission = admit_runtime_probe(_MANIFEST, repo_root=tmp_path, run_build=False)

    assert admission.admitted is False
    assert admission.side_effects is False
    assert admission.formal_denominator is False
    assert "host_project_missing" in admission.reason_codes
    assert "build_not_run" in admission.reason_codes


def test_runtime_admission_accepts_frozen_local_inputs_after_offline_build() -> None:
    admission = admit_runtime_probe(_MANIFEST, repo_root=_ROOT, run_build=True)

    assert admission.admitted is True
    assert admission.side_effects is False
    assert admission.formal_denominator is True
    assert len(admission.lanes) == 6
    assert all(lane["attempts"] == 1 for lane in admission.lanes)
    assert {lane["cell_id"] for lane in admission.lanes} == {
        "change-defect",
        "change-control",
    }
    assert all(len(lane["apk"]["sha256"]) == 64 for lane in admission.lanes)


def test_temporal_oracle_distinguishes_delay_from_control() -> None:
    control = evaluate_temporal_oracle(
        "I/TemporalProbe: TEMPORAL_RESULT delay_ms=0 latency_ms=3 thread=main summary=fixture-data"
    )
    defect = evaluate_temporal_oracle(
        "I/TemporalProbe: TEMPORAL_RESULT delay_ms=250 latency_ms=253 thread=main summary=fixture-data"
    )

    assert control.conclusion == "locally_rejected"
    assert defect.conclusion == "locally_supported"
    assert control.observation["caller_thread"] == "main"
    assert defect.observation["latency_ms"] == 253


def test_runtime_manifest_rejects_tampered_lane_policy(tmp_path: Path) -> None:
    document = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    document["policy"]["planned_lanes"] = 5
    path = tmp_path / "runtime-probe.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RuntimeProbeError, match="planned_lanes"):
        load_runtime_manifest(path)


def test_project_runtime_manifest_freezes_no_diff_project_target() -> None:
    self_validate_project_schema()
    manifest = load_runtime_manifest(_PROJECT_MANIFEST)
    target = json.loads(
        (_ROOT / "bench/runtime-probes/synchronous-weather-project/project-target.json")
        .read_text(encoding="utf-8")
    )

    assert manifest.probe_id == "m7-r2-synchronous-weather-project-v1"
    assert manifest.document["target_mode"] == "project"
    assert manifest.document["policy"]["planned_lanes"] == 6
    assert [cell["cell_id"] for cell in manifest.cells] == [
        "project-defect",
        "project-control",
    ]
    assert "change_input" not in manifest.document["source_identity"]
    assert not any(key in target for key in ("diff", "diff_ref", "diff_sha256", "verdict"))


def test_project_admission_replays_campaign_without_outcome_leakage() -> None:
    admission = admit_runtime_probe(_PROJECT_MANIFEST, repo_root=_ROOT, run_build=False)

    assert admission.admitted is False
    assert admission.formal_denominator is False
    assert admission.reason_codes == ("build_not_run",)
    assert len(admission.campaign_receipts) == 2
    assert all(item["status"] == "admitted" for item in admission.campaign_receipts)
    assert all(item["diff"] is None for item in admission.campaign_receipts)
    assert all(item["no_outcome_labels"] is True for item in admission.campaign_receipts)
    assert all(
        check["status"] == "pass"
        for check in admission.checks
        if check["name"].startswith(("project_target_packet", "campaign:"))
    )
