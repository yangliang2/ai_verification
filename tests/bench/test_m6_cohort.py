"""Contract tests for the preregistered M6 qualification cohort."""

from __future__ import annotations

import json
import tomllib
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from aiverify.bench.m6_cohort import (
    CohortValidationError,
    load_cohort_manifest,
    main,
    self_validate_schema,
)


_REPOSITORY_URL = "https://github.com/example/android-app"
_FROZEN_AT = "2026-08-02T20:00:00Z"


def _write_artifact(root: Path, name: str) -> dict[str, str]:
    path = Path("evidence") / f"{name}.json"
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"artifact": name}, sort_keys=True).encode("utf-8")
    target.write_bytes(content)
    return {"path": path.as_posix(), "sha256": sha256(content).hexdigest()}


def _source(task_id: str, revision: str) -> dict[str, str]:
    return {
        "repository_url": _REPOSITORY_URL,
        "task_url": f"https://issues.example.test/{task_id}",
        "base_revision": revision,
    }


def _device() -> dict:
    return {
        "api_level": 35,
        "avd": "aiverify_api35",
        "form_factor": "phone",
        "locale": "en-US",
        "orientation": "portrait",
    }


def _common_slot(
    root: Path,
    *,
    slot_id: str,
    track: str,
    task_id: str,
    revision: str,
    risk_family: str,
) -> dict:
    slug = slot_id.lower()
    return {
        "id": slot_id,
        "track": track,
        "source": _source(task_id, revision),
        "risk_family": risk_family,
        "primary_behavior": f"bounded behavior for {slot_id}",
        "fixture": {
            "id": f"fixture-{slug}",
            "contract": _write_artifact(root, f"{slug}-fixture"),
            "status": "qualified",
        },
        "run_spec": _write_artifact(root, f"{slug}-run-spec"),
        "oracle": {
            "contract": _write_artifact(root, f"{slug}-oracle"),
            "expected_class": "bounded_behavior",
        },
        "device_configuration": _device(),
        "repetitions": {"baseline": 3, "candidate": 3},
        "retry_policy_ref": "policy.retry",
        "evidence_root": f"docs/runs/m6/{slug}",
        "replacement_eligibility": {
            "eligible": True,
            "cutoff": "before_first_formal_invocation",
        },
        "admission": {
            "status": "qualified",
            "evidence": _write_artifact(root, f"{slug}-admission"),
            "admitted_at": "2026-08-02T18:00:00Z",
        },
    }


def _historical_slot(
    root: Path,
    *,
    slot_id: str,
    task_id: str,
    pre_fix: str,
    fixed: str,
    risk_family: str,
) -> dict:
    slot = _common_slot(
        root,
        slot_id=slot_id,
        track="historical",
        task_id=task_id,
        revision=pre_fix,
        risk_family=risk_family,
    )
    slot["historical"] = {
        "upstream_task_id": task_id,
        "pair_kind": "exact_revision",
        "pre_fix_revision": pre_fix,
        "fixed_revision": fixed,
        "matched_fail_pass": True,
        "reverse_applied": False,
        "synthetic": False,
        "pre_fix_expected": "locally_rejected",
        "fixed_expected": "locally_supported",
    }
    return slot


def _prospective_slot(
    root: Path,
    *,
    slot_id: str,
    task_id: str,
    revision: str,
    risk_family: str,
) -> dict:
    slot = _common_slot(
        root,
        slot_id=slot_id,
        track="prospective",
        task_id=task_id,
        revision=revision,
        risk_family=risk_family,
    )
    slug = slot_id.lower()
    slot["prospective"] = {
        "upstream_task_id": task_id,
        "upstream_state": "open",
        "assignee": None,
        "competing_implementation": False,
        "eligibility_snapshot": _write_artifact(root, f"{slug}-eligibility"),
        "development_input": _write_artifact(root, f"{slug}-development-input"),
        "separate_sessions_required": True,
        "candidate_freeze_required": True,
        "withhold_task_identity": True,
        "withhold_fix_history": True,
        "verifier_network_policy": "disabled",
        "no_upstream_interaction": True,
    }
    return slot


def _replacement_pool(root: Path) -> list[dict]:
    historical_fixture = _write_artifact(root, "h-alt-preliminary-fixture")["path"]
    prospective_fixture = _write_artifact(root, "p-alt-preliminary-fixture")["path"]
    return [
        {
            "candidate_id": "H-ALT-01",
            "track": "historical",
            "rank": 1,
            "source": _source("T7001", "7" * 40),
            "risk_family": "G-05",
            "primary_behavior": "historical replacement behavior",
            "preliminary_fixture": historical_fixture,
            "admission_required": True,
            "historical": {
                "pre_fix_revision": "7" * 40,
                "fixed_revision": "8" * 40,
                "pair_kind": "exact_revision",
            },
        },
        {
            "candidate_id": "P-ALT-01",
            "track": "prospective",
            "rank": 1,
            "source": _source("T8001", "f" * 40),
            "risk_family": "G-07",
            "primary_behavior": "prospective replacement behavior",
            "preliminary_fixture": prospective_fixture,
            "admission_required": True,
            "prospective": {
                "upstream_state": "open",
                "assignee": None,
                "competing_implementation": False,
                "eligibility_snapshot": _write_artifact(
                    root, "p-alt-eligibility"
                ),
                "no_upstream_interaction": True,
            },
        },
    ]


def _manifest(root: Path) -> dict:
    shared_prospective_base = "f" * 40
    return {
        "schema_version": 1,
        "cohort_id": "m6-qualification-v1",
        "status": "frozen",
        "frozen_at": _FROZEN_AT,
        "maintainer_approval": {
            "issue_url": "https://github.com/example/project/issues/84",
            "comment_url": "https://github.com/example/project/issues/84#issuecomment-1",
            "approved_by": "maintainer",
            "approved_at": "2026-08-02T19:00:00Z",
        },
        "environment": {
            "execution_base": "android_cli_first",
            "adb_fallback": "bounded_recorded",
            "verification_backend": "codex_cli",
            "public_runner": "python -m aiverify.runner",
            "default_device": _device(),
        },
        "policy": {
            "formal_lanes": {
                "planned_cases": 6,
                "baseline_repetitions_per_case": 3,
                "candidate_repetitions_per_case": 3,
                "planned_lanes": 36,
            },
            "retry": {
                "max_attempts_per_lane": 2,
                "retryable_failure_classes": [
                    "preflight_environment",
                    "execution_infrastructure",
                ],
                "no_retry_after_accountable": True,
            },
            "replacement": {
                "before_first_formal_invocation_only": True,
                "preserve_exclusions_outside_denominator": True,
                "same_track_only": True,
            },
            "blinding": {
                "separate_development_and_verification_sessions": True,
                "candidate_frozen_before_verification": True,
                "withhold_task_identity": True,
                "withhold_fix_history": True,
                "verifier_network_policy": "disabled",
            },
            "claims": {
                "track_denominators_separate": True,
                "historical_allowed": [
                    "matched_fail_pass_observations",
                    "local_conclusions",
                    "accountability",
                    "operational_metrics",
                ],
                "prospective_allowed": [
                    "blinded_case_observations",
                    "local_conclusions",
                    "adjudication_agreement",
                    "accountability",
                    "operational_metrics",
                ],
                "forbidden": [
                    "combined_track_denominator",
                    "detection_rate",
                    "false_positive_rate",
                    "confidence_claim",
                    "prospective_goldset",
                    "general_android_coverage",
                    "upstream_acceptance",
                ],
            },
            "qualification_thresholds": {
                "eventually_accountable_lanes": 36,
                "historical_fixed_controls_pass": 9,
                "historical_prefix_revisions_fail_expected_oracle": 9,
                "prospective_conclusions_independently_adjudicated": 3,
                "unexplained_contradictions": 0,
                "independent_final_auditors": 1,
            },
            "failure_routes": {
                "fixture": "exclude before formal invocation",
                "execution": "classify and apply bounded retry",
                "oracle": "mark non-accountable and adjudicate",
                "adjudication": "route contradiction to final auditor",
            },
        },
        "slots": [
            _historical_slot(
                root,
                slot_id="H-01",
                task_id="T1001",
                pre_fix="1" * 40,
                fixed="2" * 40,
                risk_family="G-03",
            ),
            _historical_slot(
                root,
                slot_id="H-02",
                task_id="T1002",
                pre_fix="2" * 40,
                fixed="3" * 40,
                risk_family="G-04",
            ),
            _historical_slot(
                root,
                slot_id="H-03",
                task_id="T1003",
                pre_fix="3" * 40,
                fixed="4" * 40,
                risk_family="G-06",
            ),
            _prospective_slot(
                root,
                slot_id="P-01",
                task_id="T2001",
                revision=shared_prospective_base,
                risk_family="G-04",
            ),
            _prospective_slot(
                root,
                slot_id="P-02",
                task_id="T2002",
                revision=shared_prospective_base,
                risk_family="G-06",
            ),
            _prospective_slot(
                root,
                slot_id="P-03",
                task_id="T2003",
                revision=shared_prospective_base,
                risk_family="G-08",
            ),
        ],
        "replacement_pool": _replacement_pool(root),
        "exclusions": [],
        "replacement_events": [],
        "execution_state": {"formal_invocations_started": []},
    }


def _write_manifest(root: Path, document: dict, name: str = "cohort.json") -> Path:
    path = root / name
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _load(root: Path, document: dict):
    return load_cohort_manifest(_write_manifest(root, document), repo_root=root)


def _assert_invalid(root: Path, document: dict, match: str) -> None:
    with pytest.raises(CohortValidationError, match=match):
        _load(root, document)


def test_packaged_schema_and_valid_frozen_manifest(tmp_path: Path) -> None:
    self_validate_schema()
    path = _write_manifest(tmp_path, _manifest(tmp_path))

    manifest = load_cohort_manifest(path, repo_root=tmp_path)

    assert manifest.source_sha256 == sha256(path.read_bytes()).hexdigest()
    assert manifest.summary() == {
        "schema_version": 1,
        "cohort_id": "m6-qualification-v1",
        "status": "frozen",
        "source_path": path.resolve().as_posix(),
        "source_sha256": manifest.source_sha256,
        "canonical_sha256": manifest.canonical_sha256,
        "slots": 6,
        "historical_slots": 3,
        "prospective_slots": 3,
        "risk_families": ["G-03", "G-04", "G-06", "G-08"],
        "planned_lanes": 36,
        "replacement_candidates": 2,
        "replacement_events": 0,
        "formal_invocations_started": 0,
    }


def test_build_configuration_packages_the_schema() -> None:
    configuration = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert configuration["tool"]["setuptools"]["package-data"]["aiverify.bench"] == [
        "m6_cohort_schema.json",
        "m6_case_package_schema.json",
        "m7_qualification_schema.json",
        "m7_runtime_probe_schema.json",
        "m7_project_runtime_probe_schema.json",
    ]


def test_draft_is_valid_only_when_explicitly_allowed(tmp_path: Path) -> None:
    document = _manifest(tmp_path)
    document.update(
        {"status": "draft", "frozen_at": None, "maintainer_approval": None}
    )
    path = _write_manifest(tmp_path, document)

    with pytest.raises(CohortValidationError, match="formal consumption"):
        load_cohort_manifest(path, repo_root=tmp_path)
    assert (
        load_cohort_manifest(
            path,
            repo_root=tmp_path,
            require_frozen=False,
        ).status
        == "draft"
    )


def test_missing_case_and_duplicate_slot_ids_fail_closed(tmp_path: Path) -> None:
    missing = _manifest(tmp_path)
    missing["slots"].pop()
    _assert_invalid(tmp_path, missing, "is too short")

    duplicate = _manifest(tmp_path)
    duplicate["slots"][-1]["id"] = "P-02"
    _assert_invalid(tmp_path, duplicate, "slot ids must be unique")


def test_track_mixing_and_insufficient_risk_coverage_are_rejected(
    tmp_path: Path,
) -> None:
    mixed = _manifest(tmp_path)
    mixed["slots"][0]["track"] = "prospective"
    _assert_invalid(tmp_path, mixed, "prospective.*required")

    narrow = _manifest(tmp_path)
    for index, slot in enumerate(narrow["slots"]):
        slot["risk_family"] = ("G-03", "G-04", "G-06")[index % 3]
    _assert_invalid(tmp_path, narrow, "at least four risk families")


def test_historical_pairs_require_exact_distinct_revisions(tmp_path: Path) -> None:
    base_mismatch = _manifest(tmp_path)
    base_mismatch["slots"][0]["source"]["base_revision"] = "9" * 40
    _assert_invalid(tmp_path, base_mismatch, "base revision must equal")

    same_revision = _manifest(tmp_path)
    same_revision["slots"][0]["historical"]["fixed_revision"] = "1" * 40
    _assert_invalid(tmp_path, same_revision, "revisions must differ")

    synthetic = _manifest(tmp_path)
    synthetic["slots"][0]["historical"]["synthetic"] = True
    _assert_invalid(tmp_path, synthetic, "False was expected")


def test_prospective_policy_and_claim_leakage_are_rejected(tmp_path: Path) -> None:
    network_mismatch = _manifest(tmp_path)
    network_mismatch["slots"][3]["prospective"][
        "verifier_network_policy"
    ] = "recorded"
    _assert_invalid(tmp_path, network_mismatch, "network policy contradicts")

    leaked = _manifest(tmp_path)
    leaked["policy"]["claims"]["historical_allowed"].append("detection_rate")
    _assert_invalid(tmp_path, leaked, "leak forbidden claims")

    missing_forbidden = _manifest(tmp_path)
    missing_forbidden["policy"]["claims"]["forbidden"].remove("confidence_claim")
    _assert_invalid(tmp_path, missing_forbidden, "confidence_claim")


def test_duplicate_and_overlapping_source_identities_are_rejected(
    tmp_path: Path,
) -> None:
    duplicate = _manifest(tmp_path)
    duplicate["slots"][1]["source"] = deepcopy(duplicate["slots"][0]["source"])
    duplicate["slots"][1]["historical"]["upstream_task_id"] = "T1001"
    _assert_invalid(tmp_path, duplicate, "duplicate admitted task identity")

    overlap = _manifest(tmp_path)
    overlap["replacement_pool"][0]["source"] = deepcopy(
        overlap["slots"][0]["source"]
    )
    overlap["replacement_pool"][0]["historical"]["pre_fix_revision"] = "1" * 40
    _assert_invalid(tmp_path, overlap, "overlaps admitted task identity")


def test_reference_paths_and_checksums_fail_closed(tmp_path: Path) -> None:
    escaped = _manifest(tmp_path)
    escaped["slots"][0]["run_spec"]["path"] = "../outside.json"
    _assert_invalid(tmp_path, escaped, "normalized repository-relative path")

    missing = _manifest(tmp_path)
    missing["slots"][0]["run_spec"]["path"] = "evidence/not-there.json"
    _assert_invalid(tmp_path, missing, "artifact does not exist")

    tampered = _manifest(tmp_path)
    target = tmp_path / tampered["slots"][0]["run_spec"]["path"]
    target.write_text("tampered", encoding="utf-8")
    _assert_invalid(tmp_path, tampered, "checksum mismatch")


def _apply_valid_historical_replacement(root: Path, document: dict) -> None:
    slot = document["slots"][0]
    original_source = deepcopy(slot["source"])
    candidate = document["replacement_pool"][0]
    slot["source"] = deepcopy(candidate["source"])
    slot["historical"]["upstream_task_id"] = "T7001"
    slot["historical"]["pre_fix_revision"] = "7" * 40
    slot["historical"]["fixed_revision"] = "8" * 40
    exclusion_evidence = _write_artifact(root, "h-01-replacement-exclusion")
    document["exclusions"].append(
        {
            "candidate_id": "H-01",
            "track": "historical",
            "source": original_source,
            "reason": "exact-revision preflight did not reproduce",
            "evidence": exclusion_evidence,
            "excluded_at": "2026-08-02T18:30:00Z",
        }
    )
    document["replacement_events"].append(
        {
            "slot_id": "H-01",
            "candidate_id": "H-ALT-01",
            "replaced_candidate_id": "H-01",
            "occurred_at": "2026-08-02T19:00:00Z",
            "before_first_formal_invocation": True,
            "exclusion_evidence": exclusion_evidence,
        }
    )


def test_registered_same_track_replacement_before_start_is_valid(
    tmp_path: Path,
) -> None:
    document = _manifest(tmp_path)
    _apply_valid_historical_replacement(tmp_path, document)

    manifest = _load(tmp_path, document)

    assert manifest.summary()["replacement_events"] == 1


def test_cross_track_and_post_start_replacements_are_rejected(
    tmp_path: Path,
) -> None:
    cross_track = _manifest(tmp_path)
    _apply_valid_historical_replacement(tmp_path, cross_track)
    cross_track["replacement_events"][0]["candidate_id"] = "P-ALT-01"
    _assert_invalid(tmp_path, cross_track, "cannot cross tracks")

    post_start = _manifest(tmp_path)
    _apply_valid_historical_replacement(tmp_path, post_start)
    post_start["replacement_events"][0]["occurred_at"] = "2026-08-02T21:30:00Z"
    post_start["execution_state"]["formal_invocations_started"].append(
        {
            "slot_id": "H-01",
            "lane_id": "H-01-baseline-1",
            "started_at": "2026-08-02T21:00:00Z",
        }
    )
    _assert_invalid(tmp_path, post_start, "at or after its first formal invocation")


def test_frozen_manifest_requires_prior_maintainer_approval(tmp_path: Path) -> None:
    missing = _manifest(tmp_path)
    missing["maintainer_approval"] = None
    _assert_invalid(tmp_path, missing, "requires maintainer_approval")

    late = _manifest(tmp_path)
    late["maintainer_approval"]["approved_at"] = "2026-08-02T21:00:00Z"
    _assert_invalid(tmp_path, late, "cannot occur after frozen_at")

    late_admission = _manifest(tmp_path)
    late_admission["slots"][0]["admission"][
        "admitted_at"
    ] = "2026-08-02T21:00:00Z"
    _assert_invalid(tmp_path, late_admission, "admission cannot occur after")


def test_replacement_ledger_binds_exclusion_and_frozen_rank_order(
    tmp_path: Path,
) -> None:
    mismatched_evidence = _manifest(tmp_path)
    _apply_valid_historical_replacement(tmp_path, mismatched_evidence)
    mismatched_evidence["replacement_events"][0][
        "exclusion_evidence"
    ] = _write_artifact(tmp_path, "different-exclusion")
    _assert_invalid(tmp_path, mismatched_evidence, "exclusion ledger checksum")

    skipped = _manifest(tmp_path)
    first = skipped["replacement_pool"][0]
    second = deepcopy(first)
    second["candidate_id"] = "H-ALT-02"
    second["rank"] = 2
    second["source"] = _source("T7002", "9" * 40)
    second["historical"]["pre_fix_revision"] = "9" * 40
    second["historical"]["fixed_revision"] = "a" * 40
    skipped["replacement_pool"].append(second)
    _apply_valid_historical_replacement(tmp_path, skipped)
    skipped["slots"][0]["source"] = deepcopy(second["source"])
    skipped["slots"][0]["historical"]["upstream_task_id"] = "T7002"
    skipped["slots"][0]["historical"]["pre_fix_revision"] = "9" * 40
    skipped["slots"][0]["historical"]["fixed_revision"] = "a" * 40
    skipped["replacement_events"][0]["candidate_id"] = "H-ALT-02"
    _assert_invalid(tmp_path, skipped, "skips unexcluded earlier candidates")


def test_ordered_replacements_can_fill_multiple_slots(tmp_path: Path) -> None:
    document = _manifest(tmp_path)
    _apply_valid_historical_replacement(tmp_path, document)

    second = deepcopy(document["replacement_pool"][0])
    second["candidate_id"] = "H-ALT-02"
    second["rank"] = 2
    second["source"] = _source("T7002", "9" * 40)
    second["historical"]["pre_fix_revision"] = "9" * 40
    second["historical"]["fixed_revision"] = "a" * 40
    document["replacement_pool"].append(second)

    slot = document["slots"][1]
    original_source = deepcopy(slot["source"])
    slot["source"] = deepcopy(second["source"])
    slot["historical"]["upstream_task_id"] = "T7002"
    slot["historical"]["pre_fix_revision"] = "9" * 40
    slot["historical"]["fixed_revision"] = "a" * 40
    exclusion_evidence = _write_artifact(tmp_path, "h-02-replacement-exclusion")
    document["exclusions"].append(
        {
            "candidate_id": "H-02",
            "track": "historical",
            "source": original_source,
            "reason": "exact-revision preflight did not reproduce",
            "evidence": exclusion_evidence,
            "excluded_at": "2026-08-02T19:10:00Z",
        }
    )
    document["replacement_events"].append(
        {
            "slot_id": "H-02",
            "candidate_id": "H-ALT-02",
            "replaced_candidate_id": "H-02",
            "occurred_at": "2026-08-02T19:20:00Z",
            "before_first_formal_invocation": True,
            "exclusion_evidence": exclusion_evidence,
        }
    )

    manifest = _load(tmp_path, document)

    assert manifest.summary()["replacement_events"] == 2


def test_excluded_source_cannot_remain_in_admitted_denominator(
    tmp_path: Path,
) -> None:
    document = _manifest(tmp_path)
    document["exclusions"].append(
        {
            "candidate_id": "H-EXCLUDED-01",
            "track": "historical",
            "source": deepcopy(document["slots"][0]["source"]),
            "reason": "preflight exclusion",
            "evidence": _write_artifact(tmp_path, "excluded-overlap"),
            "excluded_at": "2026-08-02T18:30:00Z",
        }
    )
    _assert_invalid(tmp_path, document, "overlaps admitted slot H-01")


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("schema_version: 1\nschema_version: 1\n", encoding="utf-8")

    with pytest.raises(CohortValidationError, match="duplicate key"):
        load_cohort_manifest(path, repo_root=tmp_path)


def test_cli_emits_machine_readable_valid_and_invalid_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_manifest(tmp_path, _manifest(tmp_path))
    assert main([str(path), "--repo-root", str(tmp_path)]) == 0
    valid = json.loads(capsys.readouterr().out)
    assert valid["status"] == "valid"
    assert valid["planned_lanes"] == 36

    document = _manifest(tmp_path)
    document["slots"].pop()
    invalid_path = _write_manifest(tmp_path, document, "invalid.json")
    assert main([str(invalid_path), "--repo-root", str(tmp_path)]) == 2
    invalid = json.loads(capsys.readouterr().err)
    assert invalid["status"] == "invalid"
    assert any("too short" in error for error in invalid["errors"])
