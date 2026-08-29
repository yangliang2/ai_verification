from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.bench import opencalc_discovery as discovery
from aiverify.bench import runtime_calibration
from aiverify.bench.state_evolution import verify_change_target_diff

ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
SOURCE = Path("/Users/peter/hosts/opencalc-calibration")


def _source_available() -> bool:
    return SOURCE.is_dir() and (SOURCE / ".git").exists()


pytestmark = pytest.mark.skipif(
    not _source_available(),
    reason="the pinned OpenCalc checkout is not available at the documented path",
)


def _copy_candidate(tmp_path: Path) -> Path:
    destination = tmp_path / "candidate"
    shutil.copytree(CANDIDATE, destination)
    return destination


def _copy_source(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    destination = tmp_path / "source"
    shutil.copytree(
        SOURCE,
        destination,
        ignore=shutil.ignore_patterns("build", ".gradle"),
    )
    return destination


def _rebind_manifest(candidate: Path) -> None:
    path = candidate / "candidate-manifest.json"
    manifest = json.loads(path.read_text())
    for artifact in manifest["artifacts"]:
        artifact_path = candidate / artifact["path"]
        raw = artifact_path.read_bytes()
        artifact["sha256"] = hashlib.sha256(raw).hexdigest()
        artifact["canonical_sha256"] = runtime_calibration.canonical_sha256(
            json.loads(raw)
        )
    manifest["identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in manifest.items() if key != "identity_sha256"}
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def _source_file(source_root: Path) -> Path:
    return source_root / discovery.TARGET_SOURCE_PATH


def test_admits_both_change_campaigns_from_the_pristine_source() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)

    assert result.admitted is True
    assert [package.variant.variant_id for package in result.packages] == [
        "control",
        "defect",
    ]
    assert [package.campaign.campaign.status for package in result.packages] == [
        "plan-admitted",
        "plan-admitted",
    ]
    assert [projection.opaque_lane_id for projection in result.projections] == [
        discovery.CONTROL_LANE_ID,
        discovery.DEFECT_LANE_ID,
    ]

    for package in result.packages:
        assert package.target.kind == "change"
        assert package.context_acquisition.target.kind == "project"
        assert package.context_acquisition.materialized_patch_applied is False
        assert package.context_acquisition.result.receipt.no_diff is True
        assert package.context_acquisition.result.receipt.discovery_budget == 9
        assert package.context_acquisition.result.receipt.budget_used == 9
        assert package.context_acquisition.result.receipt.skipped_scope == ()
        assert package.context_acquisition.result.receipt.inspected_scope == tuple(
            sorted(discovery.REQUIRED_CONTEXT_PATHS)
        )
        assert package.behavior_delta.subject == "binding.input.isSaveEnabled"
        assert package.behavior_delta.after.endswith(
            {"control": "true", "defect": "false"}[package.variant.variant_id]
        )
        assert package.campaign.campaign.target == package.target
        assert package.campaign.campaign.attack_plans[0].status == "admitted"
        assert package.context_acquisition.unknown_fact_ids
        assert all(
            package.context_acquisition.result.graph.fact(fact_id).status == "unknown"
            for fact_id in package.context_acquisition.unknown_fact_ids
        )

    assert result.build_calls == 0
    assert result.device_calls == 0
    assert result.model_calls == 0


def test_admits_both_project_campaigns_from_separate_synthetic_commits(
    tmp_path: Path,
) -> None:
    result = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )

    assert result.admitted is True
    assert [package.variant.variant_id for package in result.packages] == [
        "control",
        "defect",
    ]
    assert [package.target.kind for package in result.packages] == [
        "project",
        "project",
    ]
    assert [projection.opaque_lane_id for projection in result.projections] == [
        "ocrc-v1-lane-03",
        "ocrc-v1-lane-04",
    ]
    assert len({package.target.source_commit for package in result.packages}) == 2
    assert len({package.target.worktree for package in result.packages}) == 2
    assert result.build_calls == 0
    assert result.device_calls == 0
    assert result.model_calls == 0


def test_project_receipts_bind_deterministic_commits_and_clean_materializations(
    tmp_path: Path,
) -> None:
    first = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "first-materializations",
    )
    second = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "second-materializations",
    )

    assert first.identity_sha256 == second.identity_sha256
    assert [receipt.identity_sha256 for receipt in first.synthetic_commits] == [
        receipt.identity_sha256 for receipt in second.synthetic_commits
    ]
    assert [receipt.synthetic_commit for receipt in first.synthetic_commits] == [
        receipt.synthetic_commit for receipt in second.synthetic_commits
    ]
    assert [package.identity_sha256 for package in first.packages] == [
        package.identity_sha256 for package in second.packages
    ]
    assert [projection.identity_sha256 for projection in first.projections] == [
        projection.identity_sha256 for projection in second.projections
    ]
    candidate_identity_drift = replace(
        first,
        candidate_identity_sha256="0" * 64,
    )
    assert candidate_identity_drift.identity_sha256 != first.identity_sha256

    for package, receipt in zip(first.packages, first.synthetic_commits):
        worktree = Path(receipt.worktree_path)
        assert package.target.source_commit == receipt.synthetic_commit
        assert package.target.worktree == receipt.worktree_path
        assert receipt.parent_commit == discovery.UPSTREAM_COMMIT
        assert receipt.parent_tree_sha256 == discovery.UPSTREAM_TREE_SHA256
        assert receipt.patch_sha256 == package.variant.patch_sha256
        assert receipt.patch_applied is True
        assert receipt.author_name == discovery.SYNTHETIC_AUTHOR_NAME
        assert receipt.author_email == discovery.SYNTHETIC_AUTHOR_EMAIL
        assert receipt.author_timestamp == discovery.SYNTHETIC_COMMIT_TIMESTAMP
        assert receipt.committer_name == discovery.SYNTHETIC_AUTHOR_NAME
        assert receipt.committer_email == discovery.SYNTHETIC_AUTHOR_EMAIL
        assert receipt.committer_timestamp == discovery.SYNTHETIC_COMMIT_TIMESTAMP
        assert receipt.message == discovery.SYNTHETIC_COMMIT_MESSAGE
        serialized_receipt = receipt.to_dict()
        assert serialized_receipt["result_identity_sha256"] == receipt.identity_sha256
        assert discovery.SyntheticProjectCommit.from_dict(serialized_receipt) == receipt
        assert (
            subprocess.run(
                ["git", "rev-parse", "HEAD^"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            == receipt.parent_commit
        )
        assert (
            subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            == receipt.synthetic_tree_sha256
        )
        assert (
            subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            == ""
        )
        assert (worktree / discovery.TARGET_SOURCE_PATH).read_bytes() != _source_file(
            SOURCE
        ).read_bytes()


def test_project_packages_preserve_source_meaning_and_share_neutral_contracts(
    tmp_path: Path,
) -> None:
    change = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    project = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )

    for change_package, project_package in zip(change.packages, project.packages):
        assert project_package.target.kind == "project"
        assert project_package.target.scope == discovery.REQUIRED_CONTEXT_PATHS
        assert project_package.target.discovery_budget == discovery.REQUIRED_CONTEXT_BUDGET
        assert project_package.behavior_delta is None
        assert project_package.contract_drift is None
        assert project_package.quality_contract == change_package.quality_contract
        assert project_package.risk_prior == change_package.risk_prior
        assert project_package.attack_operator == change_package.attack_operator
        assert project_package.risk_priority == change_package.risk_priority
        assert project_package.risk_hypothesis.quality_property == (
            change_package.risk_hypothesis.quality_property
        )
        assert project_package.risk_hypothesis.assumptions == (
            change_package.risk_hypothesis.assumptions
        )
        assert project_package.risk_hypothesis.required_evidence == (
            change_package.risk_hypothesis.required_evidence
        )
        change_hypothesis = change_package.risk_hypothesis.to_dict()
        change_hypothesis.pop("behavior_delta_id")
        change_hypothesis.pop("contract_drift_id")
        assert project_package.risk_hypothesis.to_dict() == change_hypothesis
        assert project_package.campaign.campaign.failure_chains == (
            change_package.campaign.campaign.failure_chains
        )
        change_request = change_package.campaign.context_request
        project_request = project_package.campaign.context_request
        assert change_request is not None
        assert project_request is not None
        assert project_request.request_id == change_request.request_id
        assert project_request.campaign_id == change_request.campaign_id
        assert project_request.target_id == change_request.target_id
        assert project_request.required_predicates == change_request.required_predicates
        assert project_request.probe_refs == change_request.probe_refs
        assert project_request.budget == change_request.budget
        assert project_package.context_acquisition.required_paths == (
            change_package.context_acquisition.required_paths
        )
        assert project_package.context_acquisition.adapters == (
            change_package.context_acquisition.adapters
        )
        assert project_package.context_acquisition.engine_adapters == (
            change_package.context_acquisition.engine_adapters
        )
        assert project_package.exploration_policy_id == (
            change_package.exploration_policy_id
        )
        assert project_package.attack_plan.to_dict() | {
            "target_id": change_package.attack_plan.target_id
        } == change_package.attack_plan.to_dict()
        serialized = project_package.to_dict()
        assert "patch" not in serialized
        assert serialized["source_injection"]["sha256"] == change_package.variant.patch_sha256
        assert serialized["source_provenance"]["baseline_commit"] == discovery.UPSTREAM_COMMIT
        assert serialized["source_provenance"]["commit"] == project_package.target.source_commit
        assert serialized["synthetic_project_commit"]["identity_sha256"] == (
            project_package.synthetic_commit.identity_sha256
        )
        assert discovery.SourceRichDiscoveryPackage.from_dict(serialized) == project_package

    documents = project.driver_visible_serializations()
    assert documents[0].keys() == documents[1].keys()
    for document in documents:
        serialized = json.dumps(document, sort_keys=True).lower()
        assert document["diff"] is None
        assert document["model_policy"] == {"model_calls": False}
        assert all(term not in serialized for term in discovery.PROJECTION_LEAKAGE_TERMS)
    assert discovery.audit_driver_serializations(documents) == project.leakage_audit


def test_project_admission_only_runs_git_and_leaves_pristine_source_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _source_file(SOURCE)
    before_bytes = target.read_bytes()
    before_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=SOURCE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    calls: list[tuple[str, ...]] = []
    real_run = discovery.subprocess.run

    def record_run(*args: object, **kwargs: object) -> object:
        command = args[0]
        if isinstance(command, (list, tuple)):
            calls.append(tuple(str(item) for item in command))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(discovery.subprocess, "run", record_run)
    discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )

    assert calls
    assert all(command and command[0] == "git" for command in calls)
    assert all(
        not any(token in {"gradle", "gradlew", "adb", "android"} for token in command)
        for command in calls
    )
    assert target.read_bytes() == before_bytes
    after_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=SOURCE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert after_status == before_status == ""


def test_project_admission_rejects_materialized_source_drift_before_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "project-materializations"
    original_acquire = discovery._acquire_project_context_for_admission

    def acquire_and_mutate(target: discovery.ProjectTarget) -> object:
        acquired = original_acquire(target)
        if target.target_id.endswith("-control"):
            Path(target.worktree, "untracked-after-context.txt").write_text(
                "drift\n",
                encoding="utf-8",
            )
        return acquired

    monkeypatch.setattr(
        discovery,
        "_acquire_project_context_for_admission",
        acquire_and_mutate,
    )
    with pytest.raises(discovery.ProjectTargetAdmissionError) as error:
        discovery.admit_project_target_pair(CANDIDATE, SOURCE, output)

    assert error.value.code == "project_materialization_dirty"
    assert output.is_dir()
    assert not any(output.iterdir())


def test_project_admission_rejects_a_nonempty_materialization_root_before_clone(
    tmp_path: Path,
) -> None:
    output = tmp_path / "project-materializations"
    output.mkdir()
    (output / "caller-owned.txt").write_text("keep me\n")

    with pytest.raises(discovery.ProjectTargetAdmissionError) as error:
        discovery.admit_project_target_pair(CANDIDATE, SOURCE, output)

    assert error.value.code == "project_materialization_root_not_empty"
    assert (output / "caller-owned.txt").read_text() == "keep me\n"


def test_project_admission_rejects_pristine_source_identity_drift(
    tmp_path: Path,
) -> None:
    source = _copy_source(tmp_path)
    (source / "untracked-project-admission-test.txt").write_text("untracked\n")

    with pytest.raises(discovery.ProjectTargetAdmissionError) as error:
        discovery.admit_project_target_pair(
            CANDIDATE,
            source,
            tmp_path / "project-materializations",
        )

    assert error.value.code == "source_worktree_dirty"
    assert not (tmp_path / "project-materializations").exists()


def test_project_package_rejects_an_invented_diff_field(
    tmp_path: Path,
) -> None:
    result = discovery.admit_project_target_pair(
        CANDIDATE,
        SOURCE,
        tmp_path / "project-materializations",
    )
    serialized = result.packages[0].to_dict()
    serialized["patch"] = {"diff": "invented"}

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery.SourceRichDiscoveryPackage.from_dict(serialized)

    assert error.value.code == "package_project_diff_present"

    forged_policy = result.packages[0].to_dict()
    forged_policy["exploration_policy_id"] = "forged-policy"
    with pytest.raises(discovery.ChangeTargetAdmissionError) as policy_error:
        discovery.SourceRichDiscoveryPackage.from_dict(forged_policy)

    assert policy_error.value.code == "package_schema_mismatch"


def test_admission_is_deterministic_and_packages_round_trip() -> None:
    first = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    second = discovery.admit_opencalc_change_pair(CANDIDATE, SOURCE)

    assert first.to_dict() == second.to_dict()
    assert first.identity_sha256 == second.identity_sha256
    assert first.pair.identity_sha256 == second.pair.identity_sha256
    assert [item.identity_sha256 for item in first.packages] == [
        item.identity_sha256 for item in second.packages
    ]
    for package in first.packages:
        restored = discovery.SourceRichDiscoveryPackage.from_dict(package.to_dict())
        assert restored == package
        assert restored.identity_sha256 == package.identity_sha256
    for projection in first.projections:
        restored = discovery.BlindRuntimeProjection.from_dict(projection.to_dict())
        assert restored == projection


def test_driver_projections_are_symmetric_and_outcome_blind() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    documents = result.driver_visible_serializations()

    assert documents[0].keys() == documents[1].keys()
    for document in documents:
        serialized = json.dumps(document, sort_keys=True).lower()
        assert "target_kind" not in document
        assert "source_provenance" not in document
        assert "oracle" not in serialized
        assert "expected" not in serialized
        assert "control" not in serialized
        assert "defect" not in serialized
        assert "variant" not in serialized
        assert document["diff"] is None
        assert document["model_policy"] == {"model_calls": False}

    audit = discovery.audit_driver_serializations(documents)
    assert audit == result.leakage_audit
    assert audit.status == "passed"


def test_auditor_package_retains_the_real_delta_and_source_meaning() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    control, defect = result.packages

    assert control.variant.right_hand_side == "true"
    assert defect.variant.right_hand_side == "false"
    assert control.behavior_delta.after != defect.behavior_delta.after
    assert control.target.diff_sha256 != defect.target.diff_sha256
    assert control.target.source_commit == discovery.UPSTREAM_COMMIT
    assert control.pair.anchor.path == discovery.TARGET_SOURCE_PATH
    assert control.pair.anchor.required_occurrences == 1
    assert control.pair.baseline.tree_sha256 == discovery.UPSTREAM_TREE_SHA256
    assert control.pair.baseline.archive_sha256 == discovery.UPSTREAM_ARCHIVE_SHA256
    assert control.campaign.campaign.quality_contracts == (
        defect.campaign.campaign.quality_contracts[0],
    )
    assert control.risk_prior == defect.risk_prior
    assert control.attack_operator == defect.attack_operator
    assert control.risk_hypothesis.quality_property == defect.risk_hypothesis.quality_property
    assert control.attack_plan.plan_id == defect.attack_plan.plan_id


def test_change_targets_bind_real_repository_patch_artifacts() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)

    for package in result.packages:
        assert package.target.diff_ref == (
            f"{discovery.PATCH_ARTIFACT_DIRECTORY}/{package.variant.variant_id}.patch"
        )
        verification = verify_change_target_diff(package.target, repo_root=ROOT)
        assert verification.valid is True
        assert verification.checks[0]["actual_sha256"] == package.variant.patch_sha256


def test_admission_only_runs_git_and_leaves_pristine_source_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _source_file(SOURCE)
    before_bytes = target.read_bytes()
    before_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=SOURCE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    calls: list[tuple[str, ...]] = []
    real_run = discovery.subprocess.run

    def record_run(*args: object, **kwargs: object) -> object:
        command = args[0]
        if isinstance(command, (list, tuple)):
            calls.append(tuple(str(item) for item in command))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(discovery.subprocess, "run", record_run)
    discovery.admit_change_target_pair(CANDIDATE, SOURCE)

    assert calls
    assert all(command and command[0] == "git" for command in calls)
    assert all(
        not any(token in {"gradle", "gradlew", "adb", "android"} for token in command)
        for command in calls
    )
    assert target.read_bytes() == before_bytes
    after_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=SOURCE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert after_status == before_status == ""


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("dirty", "source_worktree_dirty"),
        ("origin", "source_origin_mismatch"),
        ("commit", "source_commit_mismatch"),
    ),
)
def test_pristine_source_admission_rejects_identity_drift(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    source = _copy_source(tmp_path)
    if mutation == "dirty":
        (source / "untracked-admission-test.txt").write_text("untracked\n")
    elif mutation == "origin":
        subprocess.run(
            ["git", "remote", "set-url", "origin", "https://example.invalid/wrong.git"],
            cwd=source,
            check=True,
        )
    else:
        subprocess.run(["git", "checkout", "--detach", "HEAD^"], cwd=source, check=True)

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery.admit_change_target_pair(CANDIDATE, source)
    assert error.value.code == code


def test_pristine_source_admission_rejects_tree_identity_drift(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    baseline = replace(
        discovery.admit_change_target_pair(CANDIDATE, SOURCE).pair.baseline,
        tree_sha256="0" * 40,
    )

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery._verify_pristine_source(source, baseline)
    assert error.value.code == "source_tree_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("missing", "anchor_context_missing"),
        ("ambiguous", "anchor_ambiguous"),
        ("digest", "anchor_target_digest_mismatch"),
    ),
)
def test_anchor_admission_rejects_missing_ambiguous_or_drifted_context(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    source = _copy_source(tmp_path)
    path = _source_file(source)
    text = path.read_text()
    anchor = discovery.admit_change_target_pair(CANDIDATE, SOURCE).pair
    if mutation == "missing":
        text = text.replace(anchor.anchor.context, "anchor context removed", 1)
    elif mutation == "ambiguous":
        text += "\n" + anchor.anchor.context + "\n"
    else:
        text = text.replace("package ", "package altered.", 1)
    path.write_text(text)

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery._validate_anchor_against_source(source, anchor)
    assert error.value.code == code


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("taxonomy", "pair_taxonomy_mismatch"),
        ("operator", "pair_operator_mismatch"),
        ("extra_hunk", "extra_source_hunk"),
    ),
)
def test_candidate_pair_admission_rejects_pair_contract_drift(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "source-pair.json"
    document = json.loads(path.read_text())
    if mutation == "taxonomy":
        document["taxonomy_id"] = "wrong-taxonomy"
    elif mutation == "operator":
        document["mutation_operator_id"] = "wrong-operator"
    else:
        for variant in document["variants"]:
            variant["patch_text"] += "diff --git a/extra b/extra\n"
            variant["patch_sha256"] = hashlib.sha256(
                variant["patch_text"].encode()
            ).hexdigest()
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery.admit_change_target_pair(candidate, SOURCE)
    assert error.value.code == code


def test_required_context_rejects_missing_unreadable_and_budget_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _copy_source(tmp_path)
    required = source / discovery.REQUIRED_CONTEXT_PATHS[1]
    required.unlink()
    with pytest.raises(discovery.ChangeTargetAdmissionError) as missing:
        discovery._validate_required_context(source)
    assert missing.value.code == "context_required_path_missing"

    source = _copy_source(tmp_path / "unreadable")
    invalid = source / discovery.REQUIRED_CONTEXT_PATHS[1]
    invalid.write_bytes(b"\xff\xfe\xfd")
    with pytest.raises(discovery.ChangeTargetAdmissionError) as unreadable:
        discovery._validate_required_context(source)
    assert unreadable.value.code == "context_required_path_unreadable"

    monkeypatch.setattr(discovery, "REQUIRED_CONTEXT_BUDGET", 8)
    source = _copy_source(tmp_path / "budget")
    with pytest.raises(discovery.ChangeTargetAdmissionError) as exhausted:
        discovery._validate_required_context(source)
    assert exhausted.value.code == "context_budget_exhausted"


def test_projection_leakage_rejects_hidden_material_without_mutating_auditor_package() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    original_package = result.packages[0].to_dict()
    leaked = result.projections[0].to_dict()
    leaked["hidden_variant"] = "defect"

    with pytest.raises(discovery.ChangeTargetAdmissionError) as error:
        discovery.audit_projection_leakage((leaked, result.projections[1].to_dict()))
    assert error.value.code == "projection_leakage"
    assert result.packages[0].to_dict() == original_package


def test_projection_diff_and_model_policy_are_fail_closed() -> None:
    result = discovery.admit_change_target_pair(CANDIDATE, SOURCE)
    leaked = result.projections[0].to_dict()
    leaked["diff"] = "hidden patch"
    with pytest.raises(discovery.ChangeTargetAdmissionError) as diff_error:
        discovery.BlindRuntimeProjection.from_dict(leaked)
    assert diff_error.value.code in {"projection_diff_present", "projection_leakage"}

    leaked = result.projections[0].to_dict()
    leaked["model_policy"] = {"model_calls": True}
    with pytest.raises(discovery.ChangeTargetAdmissionError) as model_error:
        discovery.BlindRuntimeProjection.from_dict(leaked)
    assert model_error.value.code in {"projection_model_policy_mismatch", "projection_leakage"}

    leaked = result.projections[0].to_dict()
    leaked["quality_contract_id"] = "secret-contract"
    with pytest.raises(discovery.ChangeTargetAdmissionError) as contract_error:
        discovery.BlindRuntimeProjection.from_dict(leaked)
    assert contract_error.value.code in {
        "projection_contract_mismatch",
        "projection_leakage",
    }
