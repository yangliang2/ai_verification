from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.bench import opencalc_discovery as discovery
from aiverify.bench import runtime_calibration, runtime_mapping

ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
SOURCE = Path("/Users/peter/hosts/opencalc-calibration")


pytestmark = pytest.mark.skipif(
    not SOURCE.is_dir(),
    reason="the pinned OpenCalc checkout is not available at the documented path",
)


def test_release_runtime_mapping_binds_the_four_frozen_lanes(
    tmp_path: Path,
) -> None:
    change = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    project = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )

    release = runtime_mapping.release_runtime_mapping(
        change,
        project,
        candidate_root=CANDIDATE,
    )

    assert release.status == "mapping_released"
    assert release.previous_status == "sealed_blind"
    assert release.lane_ids == runtime_mapping.RUNTIME_LANE_IDS
    assert [lane.lane_id for lane in release.lanes] == list(
        runtime_mapping.RUNTIME_LANE_IDS
    )
    assert [(lane.target_kind, lane.variant) for lane in release.lanes] == [
        ("ChangeTarget", "control"),
        ("ChangeTarget", "defect"),
        ("ProjectTarget", "control"),
        ("ProjectTarget", "defect"),
    ]


def _release(tmp_path: Path) -> runtime_mapping.RuntimeMappingRelease:
    change = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    project = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )
    return runtime_mapping.release_runtime_mapping(
        change,
        project,
        candidate_root=CANDIDATE,
    )


class _RecordingSourceAuthority(runtime_mapping.SourceAuthority):
    def resolve_host(self, spec: object, options: object, runner: object) -> object:
        raise AssertionError("mapping verification must not resolve a runtime host")


def test_release_round_trips_and_grants_only_authorized_views(tmp_path: Path) -> None:
    release = _release(tmp_path)

    restored = runtime_mapping.RuntimeMappingRelease.from_dict(release.to_dict())
    assert restored == release
    assert runtime_mapping.verify_runtime_mapping_release(
        release,
        candidate_root=CANDIDATE,
    ) is True
    assert release.to_driver_visible() == {
        "projection_ids": [f"{lane}-projection" for lane in runtime_mapping.RUNTIME_LANE_IDS],
        "shape": ["projection", "driver_plan", "recipe", "run_spec"],
        "serialization_sha256": release.driver_visible_serialization_sha256,
    }

    source_view = release.consume(_RecordingSourceAuthority())
    assert isinstance(source_view, runtime_mapping.SourceAuthorityMapping)
    assert source_view.lane_ids == runtime_mapping.RUNTIME_LANE_IDS
    assert [request.target_kind for request in source_view.source_requests] == [
        "ChangeTarget",
        "ChangeTarget",
        "ProjectTarget",
        "ProjectTarget",
    ]
    assert source_view.source_requests[0].result_diff_sha256 is None
    assert source_view.source_requests[2].result_diff_sha256 is not None
    assert runtime_mapping.verify_released_source_requests(
        source_view,
        _RecordingSourceAuthority(),
    ) is True

    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as unauthorized:
        release.consume(object())
    assert unauthorized.value.code == "mapping_unauthorized_consumer"

    reducer = runtime_mapping.RuntimeReducerAuthority()
    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as premature:
        release.consume(reducer)
    assert premature.value.code == "mapping_terminal_evidence_required"

    reduced = release.consume(
        reducer,
        terminal_evidence=runtime_mapping.TerminalExecutionEvidence(
            lane_ids=runtime_mapping.RUNTIME_LANE_IDS,
            terminal_identity_sha256="0" * 64,
        ),
    )
    assert isinstance(reduced, runtime_mapping.ReducerMapping)
    assert reduced.lane_ids == runtime_mapping.RUNTIME_LANE_IDS


def test_release_is_exclusive_and_reordered_or_tampered_forms_fail_closed(
    tmp_path: Path,
) -> None:
    release = _release(tmp_path)
    output = tmp_path / runtime_mapping.RUNTIME_MAPPING_RELEASE_FILENAME

    first_digest = runtime_mapping.write_runtime_mapping_release(release, output)
    first_bytes = output.read_bytes()
    assert first_digest == hashlib.sha256(first_bytes).hexdigest()
    assert json.loads(first_bytes)["status"] == "mapping_released"

    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as duplicate:
        runtime_mapping.write_runtime_mapping_release(release, output)
    assert duplicate.value.code == "mapping_release_already_exists"
    assert output.read_bytes() == first_bytes

    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as reordered:
        replace(release, lanes=tuple(reversed(release.lanes)))
    assert reordered.value.code == "mapping_lane_order_mismatch"

    document = release.to_dict()
    document["status"] = "sealed_blind"
    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as status:
        runtime_mapping.RuntimeMappingRelease.from_dict(document)
    assert status.value.code == "mapping_status_transition_mismatch"

    document = release.to_dict()
    document["lanes"][0]["variant"] = "defect"
    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as meaning:
        runtime_mapping.RuntimeMappingRelease.from_dict(document)
    assert meaning.value.code == "mapping_lane_meaning_mismatch"


def test_release_reverification_rejects_candidate_input_drift(tmp_path: Path) -> None:
    release = _release(tmp_path)
    candidate = tmp_path / "candidate"

    shutil.copytree(CANDIDATE, candidate)
    path = candidate / "runtime/lanes/lane-01/recipe.json"
    path.write_text(path.read_text().replace('"timeout_seconds": 900', '"timeout_seconds": 901'))

    with pytest.raises(runtime_mapping.RuntimeMappingVerificationError) as error:
        runtime_mapping.verify_runtime_mapping_release(
            release,
            candidate_root=candidate,
        )
    assert error.value.code == "mapping_candidate_input_mismatch"


def test_admit_family_stage_requires_terminal_candidate_and_writes_one_release(
    tmp_path: Path,
) -> None:
    predecessor = tmp_path / "candidate-stage"
    candidate_receipt = runtime_calibration.verify_candidate(CANDIDATE, predecessor)
    assert candidate_receipt.accepted is True

    output = tmp_path / "family-stage"
    materializations = tmp_path / "project-materializations"
    release = runtime_mapping.admit_family(
        candidate_root=CANDIDATE,
        source_root=SOURCE,
        predecessor_root=predecessor,
        output_root=output,
        materialization_root=materializations,
    )

    assert release.status == "mapping_released"
    assert runtime_mapping.stage_status(output) == "accepted"
    assert (output / "stage-start.json").is_file()
    assert (output / "mapping-release.json").is_file()
    assert (output / "stage-terminal.json").is_file()
    terminal = json.loads((output / "stage-terminal.json").read_text())
    assert terminal["status"] == "accepted"
    assert terminal["mapping_release_identity_sha256"] == release.identity_sha256
    assert runtime_mapping.RuntimeMappingRelease.from_dict(
        json.loads((output / "mapping-release.json").read_text())
    ) == release


def test_admit_family_stage_rejects_missing_predecessor_without_output_receipts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "family-stage"
    with pytest.raises(runtime_mapping.RuntimeMappingReleaseError) as error:
        runtime_mapping.admit_family(
            candidate_root=CANDIDATE,
            source_root=SOURCE,
            predecessor_root=tmp_path / "missing-candidate-stage",
            output_root=output,
        )
    assert error.value.code == "mapping_predecessor_not_accepted"
    assert runtime_mapping.stage_status(output) == "absent"
