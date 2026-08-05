"""Contract tests for the frozen M8 dual-mode qualification boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aiverify.bench.m8_qualification import (
    CELL_IDS,
    M8QualificationError,
    admit_qualification,
    load_manifest,
    run_preflight,
    self_validate_schema,
)

_ROOT = Path(__file__).parents[2]
_MANIFEST = _ROOT / "bench/m8/m8-state-evolution-qualification-v1.json"


def test_frozen_manifest_has_ordered_four_cells_and_twelve_members() -> None:
    self_validate_schema()
    manifest = load_manifest(_MANIFEST)

    assert manifest.qualification_id == "m8-state-evolution-qualification-v1"
    assert [cell["cell_id"] for cell in manifest.cells] == list(CELL_IDS)
    assert all(cell["repetitions"] == 3 for cell in manifest.cells)
    assert len(manifest.lanes) == 12
    assert [lane["lane_id"] for lane in manifest.lanes] == [
        f"lane-{n:02d}" for n in range(1, 13)
    ]
    assert (
        manifest.document["source_identity"]["source_commit"]
        == "1dd4b080f61437d8019958ea01954deb025f36c7"
    )
    assert manifest.document["policy"]["retry"] == {
        "max_attempts_per_lane": 1,
        "no_retry_after_accountable": True,
        "replacement_allowed": False,
    }
    assert manifest.document["environment"]["android_execution"] is False
    assert manifest.document["oracle"]["no_variant_input"] is True
    assert manifest.document["claim_boundary"]["local_only"] is True


def test_preflight_runs_both_modes_through_admission_and_compilation() -> None:
    preflight = admit_qualification(_MANIFEST, repo_root=_ROOT)

    assert preflight.admitted is True
    assert preflight.side_effects is False
    assert preflight.formal_execution_started is False
    assert len(preflight.lanes) == 12
    assert preflight.leakage_audit["status"] == "pass"
    assert preflight.leakage_audit["packet_count"] == 12
    assert preflight.contradiction_audit["status"] == "pass"
    reduction = next(
        item
        for item in preflight.checks
        if item["name"] == "attempt_evidence_reduction"
    )
    assert reduction["status"] == "pass"
    assert preflight.contradiction_audit["formal_denominator"] is False
    assert all(item["plan_status"] == "admitted" for item in preflight.lanes)
    assert all(item["hypothesis_status"] == "frozen" for item in preflight.lanes)
    assert all(
        item["campaign_status_after_compile"] == "executing" for item in preflight.lanes
    )
    assert all(item["formal_execution_started"] is False for item in preflight.lanes)

    change = [item for item in preflight.lanes if item["target_mode"] == "change"]
    project = [item for item in preflight.lanes if item["target_mode"] == "project"]
    assert len(change) == len(project) == 6
    assert all(item["behavior_delta_bound"] for item in change)
    assert all(item["contract_drift_bound"] for item in change)
    assert all(not item["project_diff_absent"] for item in change)
    assert all(item["project_diff_absent"] for item in project)
    assert all("diff" in item["run_spec"] for item in change)
    assert all("diff" not in item["run_spec"] for item in project)


def test_leakage_audit_covers_all_neutral_artifacts() -> None:
    preflight = run_preflight(_MANIFEST)
    assert all(item["status"] == "pass" for item in preflight.leakage_audit["checks"])
    assert preflight.leakage_audit["mapping_released"] is False
    serialized = json.dumps(preflight.lanes, ensure_ascii=False, sort_keys=True).lower()
    for term in (
        "defect",
        "control",
        "variant",
        "expected_outcome",
        "expected_evidence",
        "verdict",
        "locally_supported",
        "locally_rejected",
        "journey",
    ):
        assert term not in serialized


def test_preflight_regeneration_is_deterministic() -> None:
    first = run_preflight(_MANIFEST).to_dict()
    second = run_preflight(_MANIFEST).to_dict()
    assert first == second
    assert [item["input_digest"] for item in first["lanes"]] == [
        item["input_digest"] for item in second["lanes"]
    ]


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda document: document["policy"].__setitem__("max_attempts_per_lane", 2),
            "max_attempts_per_lane",
        ),
        (
            lambda document: document["policy"]["retry"].__setitem__(
                "replacement_allowed", True
            ),
            "retry",
        ),
        (lambda document: document["cells"].reverse(), "cells"),
        (
            lambda document: document["claim_boundary"].__setitem__(
                "local_only", False
            ),
            "local_only",
        ),
        (
            lambda document: document["lanes"].__setitem__(0, document["lanes"][1]),
            "lane",
        ),
        (
            lambda document: document["source_identity"].__setitem__(
                "source_commit", "0" * 40
            ),
            "source_commit",
        ),
        (
            lambda document: document["target_profiles"]["change"].__setitem__(
                "requires_behavior_delta", False
            ),
            "behavior_delta",
        ),
        (
            lambda document: document["target_profiles"]["change"].__setitem__(
                "requires_contract_drift", False
            ),
            "contract_drift",
        ),
    ],
)
def test_manifest_contradictions_fail_closed(
    tmp_path: Path, mutation, expected: str
) -> None:
    document = copy.deepcopy(json.loads(_MANIFEST.read_text(encoding="utf-8")))
    mutation(document)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(M8QualificationError, match=expected):
        load_manifest(path)


def test_verifier_packet_audit_is_explicitly_blinded() -> None:
    preflight = run_preflight(_MANIFEST)
    for check in preflight.leakage_audit["checks"]:
        assert check["variant_withheld"] is True
        assert check["expected_evidence_withheld"] is True
        assert check["oracle_conclusion_withheld"] is True
        assert check["verdict_withheld"] is True
        assert check["status"] == "pass"
