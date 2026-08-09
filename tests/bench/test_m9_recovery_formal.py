from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from aiverify.bench import m9_recovery_formal as formal
from aiverify.bench.m9_recovery_qualification import (
    CONTRADICTION_REQUIRED_FIELDS,
    DEFECT_COMMIT,
    LANE_IDS,
    PROJECT_TARGET_COMMIT,
    PROBE_TOKENS,
    sha256_file,
)


def test_static_preflight_preserves_zero_formal_counters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "formal-attempt"
    monkeypatch.setattr(formal, "FORMAL_ROOT", root)

    result = formal.static_preflight()

    assert result["status"] == "passed"
    assert result["side_effects"] is False
    assert result["device_calls"] == 0
    assert result["model_calls"] == 0
    assert result["formal_lane_attempts"] == 0
    assert result["r3_ledger"]["entries"] == 57
    assert not root.exists()


def test_formal_root_claim_is_create_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "formal-attempt"
    monkeypatch.setattr(formal, "FORMAL_ROOT", root)

    formal._claim_formal_root(
        {"status": "passed"},
        {"head": "a" * 40},
    )

    start = json.loads((root / "formal-start.json").read_text(encoding="utf-8"))
    assert start["lane_attempt_count_at_start"] == 0
    assert start["retry_count"] == 0
    with pytest.raises(formal.M9RecoveryFormalError, match="already exists"):
        formal._claim_formal_root({"status": "passed"}, {"head": "a" * 40})


def test_formal_root_claim_binds_target_specific_preclaim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "formal-attempt"
    monkeypatch.setattr(formal, "FORMAL_ROOT", root)
    payload = {
        "schema_version": 1,
        "status": "passed",
        "side_effects": False,
    }
    payload["receipt_sha256"] = formal.sha256_bytes(
        formal.canonical_json_bytes(payload)
    )
    preclaim = SimpleNamespace(to_dict=lambda: payload)

    formal._claim_formal_root(
        {"status": "passed"},
        {"head": "a" * 40},
        preclaim=preclaim,
    )

    receipt_path = root / "target-specific-preclaim.json"
    start = json.loads((root / "formal-start.json").read_text(encoding="utf-8"))
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == payload
    assert start["target_specific_preclaim"]["path"] == str(receipt_path)
    assert start["target_specific_preclaim"]["sha256"] == sha256_file(receipt_path)
    assert formal._verify_target_specific_preclaim(preclaim) == payload

    receipt_path.write_text(
        json.dumps({**payload, "status": "tampered"}),
        encoding="utf-8",
    )
    with pytest.raises(formal.M9RecoveryFormalError, match="drifted"):
        formal._verify_target_specific_preclaim(preclaim)


def test_target_specific_preclaim_is_side_effect_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-attempt"
    monkeypatch.setattr(formal, "FORMAL_ROOT", formal_root)
    target = SimpleNamespace(
        target_id="target",
        source_origin="origin",
        source_commit="a" * 40,
        worktree=str(tmp_path),
    )
    context = SimpleNamespace(
        receipt=SimpleNamespace(graph_sha256="b" * 64),
        to_dict=lambda: {"status": "partial"},
    )
    portfolio = SimpleNamespace(to_dict=lambda: {"selected": []})
    selected = SimpleNamespace(
        hypothesis=SimpleNamespace(hypothesis_id="hypothesis")
    )
    request = SimpleNamespace(to_dict=lambda: {"kind": "hypothesis"})
    response = SimpleNamespace(to_dict=lambda: {"kind": "response"})
    metadata = {
        "context_seconds": 0.01,
        "graph_sha256": "b" * 64,
        "portfolio_sha256": "c" * 64,
        "selected": selected,
        "request": request,
        "response": response,
    }
    generation = SimpleNamespace(
        authoritative_output_sha256="d" * 64,
        to_dict=lambda: {"kind": "generation"},
    )
    compiled = SimpleNamespace(
        semantics_sha256="e" * 64,
        to_dict=lambda: {"kind": "compiled"},
    )
    attack_request = SimpleNamespace(to_dict=lambda: {"kind": "attack"})
    monkeypatch.setattr(
        formal,
        "_discover_context_and_portfolio",
        lambda *_args, **_kwargs: (target, context, portfolio, metadata),
    )
    monkeypatch.setattr(
        formal,
        "_build_attack_plan",
        lambda *_args, **_kwargs: (generation, compiled, attack_request),
    )

    result = formal.validate_target_specific_preclaim(tmp_path)

    assert result.receipt["status"] == "passed"
    assert result.receipt["side_effects"] is False
    assert result.receipt["formal_namespace_claimed"] is False
    assert result.receipt["mapping_released"] is False
    assert all(
        count == 0 for count in result.receipt["side_effect_counters"].values()
    )
    assert result.receipt["receipt_sha256"] == formal.sha256_bytes(
        formal.canonical_json_bytes(
            {
                key: value
                for key, value in result.receipt.items()
                if key != "receipt_sha256"
            }
        )
    )
    assert not formal_root.exists()


def test_target_specific_mismatch_is_rejected_before_namespace_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = False
    monkeypatch.setattr(formal, "static_preflight", lambda **_kwargs: {})
    monkeypatch.setattr(formal, "_repository_identity", lambda _commit: {})
    monkeypatch.setattr(formal, "_source_bindings", lambda _inputs: {})
    monkeypatch.setattr(
        formal,
        "_validate_formal_inputs",
        lambda _inputs, _bindings: {"status": "passed"},
    )

    def reject(_project: Path) -> object:
        raise formal.M9RecoveryFormalError(
            "target-specific Attack Plan was rejected: evidence expectations do not cover hypothesis requirements"
        )

    def claim(*_args: object, **_kwargs: object) -> None:
        nonlocal claimed
        claimed = True

    monkeypatch.setattr(formal, "validate_target_specific_preclaim", reject)
    monkeypatch.setattr(formal, "_claim_formal_root", claim)

    with pytest.raises(formal.M9RecoveryFormalError, match="evidence expectations"):
        formal.execute_formal(
            formal.FormalInputs(expected_consumer_commit="a" * 40)
        )
    assert claimed is False


@pytest.mark.skipif(
    not formal.DEFAULT_PROJECT_TARGET.is_dir(),
    reason="the frozen R3 target snapshot is unavailable",
)
def test_frozen_target_specific_mismatch_is_side_effect_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-attempt"
    monkeypatch.setattr(formal, "FORMAL_ROOT", formal_root)

    with pytest.raises(
        formal.M9RecoveryFormalError,
        match="evidence expectations do not cover hypothesis requirements",
    ):
        formal.validate_target_specific_preclaim(formal.DEFAULT_PROJECT_TARGET)
    assert not formal_root.exists()


def test_state_rejects_mapping_release_reordering_and_lane_retry() -> None:
    state = formal.FormalState()
    with pytest.raises(formal.M9RecoveryFormalError, match="transition"):
        state.advance(formal.FormalStage.CREATED, formal.FormalStage.CONTEXT_ACQUIRED)
    with pytest.raises(formal.M9RecoveryFormalError, match="preceded mapping"):
        state.admit(LANE_IDS[0])

    transitions = (
        (formal.FormalStage.CREATED, formal.FormalStage.CONTRADICTION_REJECTED),
        (formal.FormalStage.CONTRADICTION_REJECTED, formal.FormalStage.CONTEXT_ACQUIRED),
        (formal.FormalStage.CONTEXT_ACQUIRED, formal.FormalStage.PORTFOLIO_FROZEN),
        (formal.FormalStage.PORTFOLIO_FROZEN, formal.FormalStage.PLAN_ADMITTED),
        (formal.FormalStage.PLAN_ADMITTED, formal.FormalStage.LEAKAGE_AUDITED),
        (formal.FormalStage.LEAKAGE_AUDITED, formal.FormalStage.MAPPING_RELEASED),
    )
    for expected, target in transitions:
        state.advance(expected, target)
    for lane_id in LANE_IDS:
        state.admit(lane_id)
    assert state.stage is formal.FormalStage.ADMISSIONS_COMPLETE

    state.start_lane(LANE_IDS[0])
    state.finish_lane(LANE_IDS[0])
    with pytest.raises(formal.M9RecoveryFormalError, match="order/retry"):
        state.start_lane(LANE_IDS[0])
    for lane_id in LANE_IDS[1:]:
        state.start_lane(lane_id)
        state.finish_lane(lane_id)
    assert state.stage is formal.FormalStage.TERMINAL
    assert tuple(state.terminal_lanes) == LANE_IDS


def test_contradiction_is_rejected_without_command_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(formal, "FORMAL_ROOT", tmp_path)
    manifest = formal.load_manifest(formal.MANIFEST_PATH, require_frozen=True).document

    audit = formal._reject_contradiction(manifest)

    assert audit["status"] == "pass"
    assert audit["command_calls"] == []
    assert tuple(audit["missing_fields"]) == CONTRADICTION_REQUIRED_FIELDS
    receipt = json.loads(
        (tmp_path / "contradiction-rejection.json").read_text(encoding="utf-8")
    )
    assert receipt["rejected_before_build_device_agent_runtime"] is True
    assert receipt["formal_denominator"] is False


def test_resolved_spec_changes_only_the_released_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "formal-artifacts"
    monkeypatch.setattr(formal, "FORMAL_ARTIFACT_ROOT", artifact_root)
    lane_id = LANE_IDS[1]
    frozen = (
        formal.REPO_ROOT
        / "bench/m9/recovery-v2/run-specs"
        / f"{lane_id}.yaml"
    )
    before = frozen.read_bytes()
    workdir = tmp_path / "fresh-source"
    workdir.mkdir()

    path, spec = formal._resolved_spec(
        lane_id,
        frozen,
        workdir,
        DEFECT_COMMIT,
    )

    resolved = yaml.safe_load(path.read_text(encoding="utf-8"))
    original = yaml.safe_load(before.decode("utf-8"))
    assert resolved["host_project"]["commit"] == DEFECT_COMMIT
    original["host_project"]["commit"] = DEFECT_COMMIT
    assert resolved == original
    assert spec.host_project == workdir.resolve()
    assert frozen.read_bytes() == before


def test_identity_factory_binds_frozen_and_effective_specs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "formal-artifacts"
    monkeypatch.setattr(formal, "FORMAL_ARTIFACT_ROOT", artifact_root)
    lane_id = LANE_IDS[0]
    frozen = (
        formal.REPO_ROOT
        / "bench/m9/recovery-v2/run-specs"
        / f"{lane_id}.yaml"
    )
    workdir = tmp_path / "source"
    workdir.mkdir()
    effective_path, effective = formal._resolved_spec(
        lane_id,
        frozen,
        workdir,
        PROJECT_TARGET_COMMIT,
    )
    artifact_dir = artifact_root / lane_id / "artifacts"

    collector = formal._identity_factory(
        lane_id=lane_id,
        frozen_path=frozen,
        effective_path=effective_path,
        effective_spec=effective,
        workdir=workdir,
        artifact_dir=artifact_dir,
    )("attempt-identity")

    assert collector.attempt_id == "attempt-identity"
    assert collector.run_spec_snapshot_path == effective_path
    assert collector.run_spec_identity_annotations == {
        "frozen_source_sha256": sha256_file(frozen),
        "source_binding_ref": formal.sealed_source_binding_ref(lane_id),
    }
    assert collector.authoritative_role_identity_dir == (
        artifact_root / lane_id / "production-identities"
    )


def test_probe_token_is_exactly_bound_to_the_text_input() -> None:
    token = PROBE_TOKENS[0]
    layout = [
        {"content-desc": "Text input", "center": "[540,1000]"},
        {
            "text": token,
            "interactions": ["clickable", "focusable", "long-clickable"],
            "center": "[420,1000]",
        },
    ]
    observation = formal._observe_text_input_token(layout, token)
    assert observation["input_field_present"] is True
    assert observation["exact_token_visible_in_input"] is True

    substring = [
        {"content-desc": "Text input", "center": "[540,1000]"},
        {
            "text": f"draft {token}",
            "interactions": ["focusable", "long-clickable"],
            "center": "[420,1000]",
        },
    ]
    assert (
        formal._observe_text_input_token(substring, token)[
            "exact_token_visible_in_input"
        ]
        is False
    )

    unrelated_field = [
        {"content-desc": "Text input", "center": "[540,1000]"},
        {
            "text": token,
            "interactions": ["focusable", "long-clickable"],
            "center": "[420,200]",
        },
    ]
    assert (
        formal._observe_text_input_token(unrelated_field, token)[
            "exact_token_visible_in_input"
        ]
        is False
    )


def test_activity_recreation_requires_destroy_then_create_or_relaunch() -> None:
    activity = formal.ACTIVITY
    lifecycle = (
        f"I/am_on_create_called: [0,{activity},performCreate]\n"
        f"I/am_on_destroy_called: [0,{activity},performDestroy]\n"
        f"I/am_on_create_called: [0,{activity},performCreate]\n"
    )
    lines, observed = formal._activity_recreation_lines(lifecycle)
    assert observed is True
    assert len(lines) == 3

    _lines, observed = formal._activity_recreation_lines(
        f"I/am_on_create_called: [0,{activity},performCreate]\n"
    )
    assert observed is False


def test_lane_exception_creates_one_terminal_record_and_typed_absence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / formal.R4_RUN_RECORD
    artifact_root = tmp_path / formal.R4_ARTIFACT_ROOT
    monkeypatch.setattr(formal, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(formal, "FORMAL_ROOT", run_root)
    monkeypatch.setattr(formal, "FORMAL_ARTIFACT_ROOT", artifact_root)
    lane_id = LANE_IDS[0]
    (artifact_root / lane_id).mkdir(parents=True)

    row = formal._seal_failed_lane(
        lane_id,
        "control",
        RuntimeError("terminal test failure"),
        duration_seconds=0.1,
    )

    record = json.loads(
        (artifact_root / lane_id / "execution-record.json").read_text(
            encoding="utf-8"
        )
    )
    absence = json.loads(
        (artifact_root / lane_id / "typed-absence.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["lifecycle_state"] == "failed"
    assert row["lane_attempt_count"] == 1
    assert row["retry_count"] == 0
    assert row["replacement_count"] == 0
    assert absence["terminal"] is True
    assert absence["retry_permitted"] is False
    assert absence["absent_artifacts"]
    assert "production-identities/*.json" in absence["absent_artifacts"]
    assert "artifacts/after-event-0/logcat.txt" in absence["absent_artifacts"]
    assert "raw/logcat/events-command.json" in absence["absent_artifacts"]
    assert "checksums.sha256" not in absence["absent_artifacts"]
    assert (artifact_root / lane_id / "checksums.sha256").is_file()
    assert "attempt_evidence" not in row
    evidence = row["terminal_absence_receipt"]
    assert evidence["refs"]["execution_record"]["path"].endswith(
        f"{lane_id}/execution-record.json"
    )
    assert evidence["refs"]["execution_record"]["sha256"] == sha256_file(
        artifact_root / lane_id / "execution-record.json"
    )
    assert row["terminal_absence_receipt_ref"]["path"].endswith(
        f"{lane_id}/terminal-absence-receipt.json"
    )
    assert row["terminal_absence_receipt_ref"]["sha256"] == sha256_file(
        artifact_root / lane_id / "terminal-absence-receipt.json"
    )


def test_semantic_evidence_uses_portfolio_lineage_and_withholds_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "formal-artifacts"
    monkeypatch.setattr(formal, "FORMAL_ARTIFACT_ROOT", artifact_root)
    lineage = formal.EvidenceLineage(
        hypothesis_id=formal.FORMAL_HYPOTHESIS_ID,
        explored_fact_ids=("fact-context-1", "fact-context-2"),
    )
    lane_id = LANE_IDS[0]
    (artifact_root / lane_id).mkdir(parents=True)
    monkeypatch.setattr(formal, "is_execution_record_accountable", lambda _record: False)

    oracle, finding = formal._write_semantic_evidence(
        lane_id,
        PROBE_TOKENS[0],
        {"lifecycle_state": "completed"},
        {},
        "inconclusive",
        lineage,
    )

    assert oracle["accountable"] is False
    assert finding is None
    assert not (artifact_root / lane_id / "finding.json").exists()
    residual = json.loads(
        (artifact_root / lane_id / "residual-risk.json").read_text(
            encoding="utf-8"
        )
    )
    risk_map = json.loads(
        (artifact_root / lane_id / "project-risk-map.json").read_text(
            encoding="utf-8"
        )
    )
    assert residual["hypothesis_id"] == formal.FORMAL_HYPOTHESIS_ID
    assert risk_map["findings"] == []
    assert risk_map["explored_fact_ids"] == ["fact-context-1", "fact-context-2"]


def test_external_input_failure_precedes_irreversible_root_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = False
    monkeypatch.setattr(formal, "static_preflight", lambda **_kwargs: {})
    monkeypatch.setattr(formal, "_repository_identity", lambda _commit: {})
    monkeypatch.setattr(formal, "_source_bindings", lambda _inputs: {})

    def reject_inputs(_inputs: object, _bindings: object) -> dict[str, object]:
        raise formal.M9RecoveryFormalError("external APK drift")

    def claim(_preflight: object, _repository: object) -> None:
        nonlocal claimed
        claimed = True

    monkeypatch.setattr(formal, "_validate_formal_inputs", reject_inputs)
    monkeypatch.setattr(formal, "_claim_formal_root", claim)

    with pytest.raises(formal.M9RecoveryFormalError, match="external APK drift"):
        formal.execute_formal(
            formal.FormalInputs(expected_consumer_commit="a" * 40)
        )
    assert claimed is False


def test_claimed_pre_lane_failure_seals_all_six_terminal_absences(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-attempt"
    artifact_root = formal_root / "formal-artifacts"
    monkeypatch.setattr(formal, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(formal, "FORMAL_ROOT", formal_root)
    monkeypatch.setattr(formal, "FORMAL_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(formal, "static_preflight", lambda **_kwargs: {})
    monkeypatch.setattr(
        formal,
        "_repository_identity",
        lambda commit: {"head": commit},
    )
    monkeypatch.setattr(formal, "_source_bindings", lambda _inputs: {})
    monkeypatch.setattr(
        formal,
        "_validate_formal_inputs",
        lambda _inputs, _bindings: {"status": "passed"},
    )
    monkeypatch.setattr(
        formal,
        "validate_target_specific_preclaim",
        lambda _project: SimpleNamespace(
            to_dict=lambda: {
                "schema_version": 1,
                "status": "passed",
                "receipt_sha256": "a" * 64,
            }
        ),
    )

    def fail_contradiction(_manifest: object) -> dict[str, object]:
        raise formal.M9RecoveryFormalError("pre-lane terminal failure")

    monkeypatch.setattr(formal, "_reject_contradiction", fail_contradiction)

    result = formal.execute_formal(
        formal.FormalInputs(
            expected_consumer_commit="b" * 40,
            source_root=tmp_path / "fresh-sources",
        )
    )

    assert result["status"] == "terminal_failed"
    assert result["terminal_lane_count"] == 6
    assert result["formal_holdout_executed"] is False
    inventory = json.loads(
        (formal_root / "formal-attempt-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert inventory["formal_attempts"][0]["terminal_lane_count"] == 6
    for lane_id in LANE_IDS:
        lane_root = artifact_root / lane_id
        assert (lane_root / "execution-record.json").is_file()
        assert (lane_root / "typed-absence.json").is_file()
        assert (lane_root / "checksums.sha256").is_file()
    assert (formal_root / "checksums.sha256").is_file()


@pytest.mark.parametrize(
    "payload",
    (
        {"source_role": "defect"},
        {"lane_role": "control"},
        {"expected_result": "pass"},
    ),
)
def test_role_leakage_guard_rejects_forbidden_material(payload: dict[str, str]) -> None:
    assert formal._ROLE_LEAKAGE.search(json.dumps(payload)) is not None
