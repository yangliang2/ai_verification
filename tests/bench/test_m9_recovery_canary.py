from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from aiverify.bench.m9_recovery_canary import (
    ENGLISH_US_INPUT_SUBTYPE,
    REVIEW_SCHEMA,
    RUN_SPEC_ROOT,
    M9RecoveryCanaryError,
    _assert_default_receipt,
    _configure_device_input,
    _contradiction_gate,
    _copy_peer_evidence,
    _copy_raw_evidence,
    _finalize_failed_attempt,
    _oracle_conclusion,
    _peer_control_artifacts,
    _reconcile_canary,
    _review_contract,
    _review_input_audit,
    _review_prompt,
)
from aiverify.discovery import Finding, FalsificationReviewerIdentity
from aiverify.runner.run_spec import load_run_spec


def test_recovery_run_specs_use_new_neutral_lane_ids_and_default_model_policy(
    tmp_path: Path,
) -> None:
    variables = {
        "M9_R2_CANARY_ALPHA_PROJECT": str(tmp_path / "alpha"),
        "M9_R2_CANARY_BETA_PROJECT": str(tmp_path / "beta"),
    }
    specs = [
        load_run_spec(path, environ=variables)
        for path in sorted(RUN_SPEC_ROOT.glob("*.yaml"))
    ]

    assert [spec.scenario.id for spec in specs] == [
        "m9-r2-canary-alpha",
        "m9-r2-canary-beta",
    ]
    assert all(not spec.scenario.id.startswith("m9-lane-") for spec in specs)
    assert all(spec.scenario.l3_spec for spec in specs)
    assert [spec.host_locator.expected_commit for spec in specs] == [
        "ee66e1526b84c026615df032c705842b7d2a521f",
        "208575f78d59716669d0733b5ed3e08797b08787",
    ]


def test_falsification_review_schema_is_valid() -> None:
    schema = json.loads(REVIEW_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "prefixItems" not in json.dumps(schema)
    assert all(
        "type" in node
        for node in (
            schema["properties"]["schema_version"],
            schema["properties"]["reasons"]["items"]["properties"]["schema_version"],
            schema["$defs"]["dimension"]["properties"]["schema_version"],
        )
    )


def test_device_input_setup_freezes_enabled_english_us_subtype(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = iter(
        [
            (
                "com.google.android.inputmethod.latin/"
                "com.android.inputmethod.latin.LatinIME\n"
            ),
            (
                "com.google.android.inputmethod.latin/"
                "com.android.inputmethod.latin.LatinIME;"
                f"617035939;{ENGLISH_US_INPUT_SUBTYPE}\n"
            ),
            "617035939\n",
            "",
            f"{ENGLISH_US_INPUT_SUBTYPE}\n",
        ]
    )

    def fake_command(args: list[str], **_: object) -> dict[str, object]:
        return {
            "args": args,
            "cwd": None,
            "returncode": 0,
            "stdout": next(outputs),
            "stderr": "",
            "duration_seconds": 0.001,
        }

    monkeypatch.setattr(
        "aiverify.bench.m9_recovery_canary._command",
        fake_command,
    )
    _configure_device_input(tmp_path, device="emulator-5554")

    receipt = json.loads(
        (tmp_path / "device-input-setup.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "passed"
    assert receipt["expected_subtype"]["hash"] == ENGLISH_US_INPUT_SUBTYPE
    assert receipt["operations"][-1]["stdout"].strip() == ENGLISH_US_INPUT_SUBTYPE


def test_failed_attempt_is_create_only_and_checksum_sealed(tmp_path: Path) -> None:
    (tmp_path / "partial.json").write_text("{}\n", encoding="utf-8")

    _finalize_failed_attempt(tmp_path, RuntimeError("terminal canary failure"))

    failure = json.loads(
        (tmp_path / "attempt-failure.json").read_text(encoding="utf-8")
    )
    assert failure["status"] == "terminal_failure"
    assert failure["ready_for_r3"] is False
    assert failure["rerun_of_this_attempt_permitted"] is False
    assert "attempt-failure.json" in (
        tmp_path / "checksums.sha256"
    ).read_text(encoding="utf-8")
    original_failure = (tmp_path / "attempt-failure.json").read_bytes()
    original_checksums = (tmp_path / "checksums.sha256").read_bytes()
    _finalize_failed_attempt(tmp_path, RuntimeError("second failure"))
    assert (tmp_path / "attempt-failure.json").read_bytes() == original_failure
    assert (tmp_path / "checksums.sha256").read_bytes() == original_checksums


def test_raw_evidence_exposes_provenance_and_fixture_binding(
    tmp_path: Path,
) -> None:
    for name in (
        "verdict.json",
        "runner-setup.json",
        "live-validation-gate.json",
        "execution-provenance.json",
        "neutral-fixture-binding.json",
        "device-input-setup.json",
        "package-reset.json",
        "production-seam-admission.json",
    ):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    (tmp_path / "artifacts").mkdir()

    refs = _copy_raw_evidence(tmp_path)

    assert "review-execution-provenance.json" in refs
    assert "execution-provenance.json" not in refs
    assert "neutral-fixture-binding.json" not in refs
    assert "production-seam-admission.json" not in refs
    assert "device-input-setup.json" in refs
    inventory = json.loads(
        (tmp_path / "raw-evidence-inventory.json").read_text(encoding="utf-8")
    )
    indexed = {item["ref"]: item for item in inventory["artifacts"]}
    assert indexed["execution-provenance.json"]["reviewer_visible"] is False
    assert indexed["neutral-fixture-binding.json"]["reviewer_visible"] is False
    assert indexed["review-execution-provenance.json"]["reviewer_visible"] is True


def test_peer_control_artifacts_verify_every_index_binding(
    tmp_path: Path,
) -> None:
    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    peer_verdict = peer_dir / "verdict.json"
    peer_provenance = peer_dir / "execution-provenance.json"
    peer_verdict.write_text('{"execution": "completed"}\n', encoding="utf-8")
    peer_provenance.write_text('{"api_level": "35"}\n', encoding="utf-8")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    index_path = tmp_path / "peer-evidence-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "ref": "peer/verdict.json",
                        "sha256": digest(peer_verdict),
                        "bytes": peer_verdict.stat().st_size,
                    },
                    {
                        "ref": "peer/execution-provenance.json",
                        "sha256": digest(peer_provenance),
                        "bytes": peer_provenance.stat().st_size,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    refs = _peer_control_artifacts(tmp_path, index_path)

    assert [item.ref for item in refs] == [
        "peer-evidence-index.json",
        "peer/verdict.json",
        "peer/execution-provenance.json",
    ]
    assert all(item.immutable for item in refs)

    peer_verdict.write_text('{"execution": "tampered"}\n', encoding="utf-8")
    with pytest.raises(M9RecoveryCanaryError, match="binding failed"):
        _peer_control_artifacts(tmp_path, index_path)


def test_peer_evidence_copy_includes_semantic_and_raw_files(
    tmp_path: Path,
) -> None:
    lane_dir = tmp_path / "lane"
    peer_dir = tmp_path / "peer-lane"
    lane_dir.mkdir()
    for name in (
        "verdict.json",
        "execution-record.json",
        "raw-evidence-inventory.json",
        "effective-execution-identity.json",
        "review-execution-provenance.json",
        "finding.json",
        "device-input-setup.json",
        "package-reset.json",
        "runner-setup.json",
        "live-validation-gate.json",
        "raw/after-event-0/layout.json",
    ):
        path = peer_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")

    index_path = _copy_peer_evidence(
        {"lane_dir": lane_dir},
        {
            "lane_dir": peer_dir,
            "lane_id": "peer-neutral",
            "raw_refs": (
                "verdict.json",
                "review-execution-provenance.json",
                "raw/after-event-0/layout.json",
            ),
        },
    )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    refs = [item["ref"] for item in index["artifacts"]]
    assert len(refs) == len(set(refs))
    assert "peer/finding.json" in refs
    assert "peer/review-execution-provenance.json" in refs
    assert "peer/neutral-fixture-binding.json" not in refs
    assert "peer/raw/after-event-0/layout.json" in refs
    assert (
        lane_dir
        / "review-input/peer/raw/after-event-0/layout.json"
    ).is_file()


def test_review_prompt_uses_citable_brief_and_exact_allowlist() -> None:
    def ref(value: str) -> SimpleNamespace:
        return SimpleNamespace(ref=value)

    context = SimpleNamespace(
        source_refs=(ref("source-target.json"), ref("review-brief.json")),
        oracle_contract=ref("oracle-contract.json"),
        execution_record=ref("execution-record.json"),
        effective_identity=ref("effective-execution-identity.json"),
        raw_evidence=(ref("execution-provenance.json"),),
        control_evidence=(ref("peer/verdict.json"),),
    )

    prompt = _review_prompt(context)

    assert "candidate Finding in review-brief.json" in prompt
    assert "Do not open or cite falsification-review-context.json" in prompt
    assert "- execution-provenance.json" in prompt
    assert "- peer/verdict.json" in prompt
    assert "must exactly match one bullet above" in prompt


def test_review_input_audit_scans_allowlisted_artifact_bytes(
    tmp_path: Path,
) -> None:
    def artifact(ref: str, content: bytes) -> SimpleNamespace:
        path = tmp_path / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return SimpleNamespace(
            ref=ref,
            sha256=hashlib.sha256(content).hexdigest(),
        )

    source = artifact("source-target.json", b"safe source")
    oracle = artifact("oracle-contract.json", b"safe oracle")
    record = artifact("execution-record.json", b"safe record")
    identity = artifact("effective-execution-identity.json", b"safe identity")
    raw = artifact(
        "raw/layout.json",
        (
            b'{"cwd":"/private/tmp/m9-r1-canary-recovery/defect",'
            b'"subject":"candidate(m9): omit persisted update for option a"}'
        ),
    )
    peer = artifact("peer/layout.json", b"safe peer")
    context = SimpleNamespace(
        source_refs=(source,),
        oracle_contract=oracle,
        execution_record=record,
        effective_identity=identity,
        raw_evidence=(raw,),
        control_evidence=(peer,),
        context_sha256="a" * 64,
        to_dict=lambda: {"context_id": "review-context-neutral"},
    )

    audit = _review_input_audit(context, "review only listed files", tmp_path)

    assert audit["status"] == "fail"
    assert audit["audit_method"] == "byte_level_allowlisted_workspace_scan"
    assert any(
        item.startswith("external_second_input_path:raw/layout.json")
        for item in audit["forbidden_disclosures"]
    )
    assert any(
        item.startswith("historical_defect_commit_subject:raw/layout.json")
        for item in audit["forbidden_disclosures"]
    )


def test_review_contract_binds_brief_provenance_and_peer_semantics(
    tmp_path: Path,
) -> None:
    lane_dir = tmp_path / "neutral-lane"
    lane_dir.mkdir()
    for name in (
        "execution-provenance.json",
        "execution-record.json",
        "effective-execution-identity.json",
    ):
        (lane_dir / name).write_text("{}\n", encoding="utf-8")
    peer_dir = lane_dir / "peer"
    peer_dir.mkdir()
    peer_verdict = peer_dir / "verdict.json"
    peer_verdict.write_text('{"l3": {"outcome": "fail"}}\n', encoding="utf-8")

    peer_sha = hashlib.sha256(peer_verdict.read_bytes()).hexdigest()
    peer_index = lane_dir / "peer-evidence-index.json"
    peer_index.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "ref": "peer/verdict.json",
                        "sha256": peer_sha,
                        "bytes": peer_verdict.stat().st_size,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    finding = Finding(
        finding_id="finding-neutral-lane",
        target_id="target-neutral-lane",
        hypothesis_id="hypothesis-neutral-lane",
        conclusion="rejected",
        evidence_refs=("execution-provenance.json",),
        impact="one local state path",
        claim_boundary="one local exact-source execution",
        rationale="terminal runtime evidence rejected the candidate risk",
    )
    row = {
        "lane_id": "neutral-lane",
        "lane_dir": lane_dir,
        "worktree": tmp_path,
        "source_commit": "1" * 40,
        "finding": finding,
        "raw_refs": ("execution-provenance.json",),
        "identity": {"production_invocation_id": "thread:turn"},
        "record": {"attempt_id": "attempt-neutral"},
    }

    context, _, _, _ = _review_contract(row, peer_index)

    assert {item.ref for item in context.source_refs} == {
        "source-target.json",
        "review-brief.json",
    }
    assert {item.ref for item in context.raw_evidence} == {
        "execution-provenance.json"
    }
    assert {item.ref for item in context.control_evidence} == {
        "peer-evidence-index.json",
        "peer/verdict.json",
    }
    brief = json.loads(
        (lane_dir / "review-brief.json").read_text(encoding="utf-8")
    )
    assert brief["candidate_finding"] == finding.to_dict()
    assert any(
        item["ref"] == "peer/verdict.json" for item in brief["peer_evidence"]
    )


def test_default_identity_requires_null_request_and_no_model_flag() -> None:
    receipt = {
        "requested_model": None,
        "effective_model": "gpt-5.2-codex",
        "command": {"argv_without_prompt": ["codex", "exec", "--json"]},
    }
    _assert_default_receipt(receipt)

    with pytest.raises(M9RecoveryCanaryError, match="default-selection"):
        _assert_default_receipt(
            {
                **receipt,
                "command": {
                    "argv_without_prompt": [
                        "codex",
                        "exec",
                        "--model",
                        "gpt-5.2-codex",
                    ]
                },
            }
        )


def test_falsification_reviewer_identity_can_record_cli_default_selection() -> None:
    identity = FalsificationReviewerIdentity.capture(
        backend="codex_cli",
        requested_model=None,
        effective_model="gpt-5.2-codex",
        invocation_id="thread:turn",
        provider_family="openai-codex-cli",
        same_family_limitation="separate read-only invocation",
    )

    assert identity.to_dict()["requested_model"] is None
    assert FalsificationReviewerIdentity.from_dict(identity.to_dict()) == identity


def test_oracle_conclusion_is_terminal_and_fail_closed() -> None:
    accountable = {"status": "completed", "accounting_eligible": True}
    assert (
        _oracle_conclusion(
            {"execution": accountable, "l1": {"outcome": "fail"}}
        )
        == "supported"
    )
    assert (
        _oracle_conclusion(
            {
                "execution": accountable,
                "l1": {"outcome": "pass"},
                "l2": {"outcome": "pass"},
                "l3": {"outcome": "pass"},
            }
        )
        == "rejected"
    )
    assert (
        _oracle_conclusion(
            {
                "execution": {
                    "status": "non_accountable",
                    "accounting_eligible": False,
                }
            }
        )
        == "inconclusive"
    )


def _row(lane_id: str, role: str, conclusion: str) -> dict:
    return {
        "lane_id": lane_id,
        "role": role,
        "accountable": True,
        "finding_conclusion": conclusion,
        "duration_seconds": 1.0,
        "run_spec_sha256": "a" * 64,
        "review": {
            "status": "complete",
            "outcome": "survived",
            "separate_invocation": True,
            "receipt": {
                "ref": f"canary-artifacts/{lane_id}/falsification-review.json",
                "sha256": "b" * 64,
            },
        },
        "chain_checks": {"full_chain": True},
        "execution_record_receipt": {
            "ref": f"canary-artifacts/{lane_id}/execution-record.json",
            "sha256": "c" * 64,
        },
    }


def test_canary_reconciliation_can_only_report_readiness_not_formal_support() -> None:
    result = _reconcile_canary(
        [
            _row("m9-r2-canary-alpha", "control", "rejected"),
            _row("m9-r2-canary-beta", "defect", "supported"),
        ],
        {"status": "pass"},
    )

    assert result["ready_for_r3"] is True
    assert result["canary_result"] == "ready_for_fresh_qualification_packet"
    assert result["formal_qualification_eligible"] is False
    assert result["formal_holdout_executed"] is False
    assert result["old_136_137_population_invoked"] is False
    assert result["counts"]["accountable"] == 2
    assert all("role" not in lane for lane in result["lanes"])
    assert all(lane["non_holdout_canary"] is True for lane in result["lanes"])
    assert all(
        lane["formal_qualification_eligible"] is False
        and lane["formal_denominator"] is False
        for lane in result["lanes"]
    )
    assert all(
        lane["execution_record"]["sha256"] == "c" * 64
        and lane["falsification_review"]["sha256"] == "b" * 64
        for lane in result["lanes"]
    )
    assert '"aggregate_result"' not in json.dumps(result)

    blocked_rows = [
        _row("m9-r2-canary-alpha", "control", "rejected"),
        {**_row("m9-r2-canary-beta", "defect", "supported"), "accountable": False},
    ]
    blocked = _reconcile_canary(blocked_rows, {"status": "pass"})
    assert blocked["ready_for_r3"] is False
    assert blocked["canary_result"] == "blocked_by_canary_evidence"


def test_contradiction_gate_is_outside_denominator_and_has_no_commands(
    tmp_path: Path,
) -> None:
    audit = _contradiction_gate(tmp_path)
    receipt = json.loads(
        (tmp_path / "contradiction-rejection.json").read_text(encoding="utf-8")
    )

    assert audit["status"] == "pass"
    assert audit["command_calls"] == []
    assert receipt["denominator_member"] is False
    assert receipt["formal_qualification_eligible"] is False
    assert receipt["rejected_before_build_device_agent_runtime"] is True
    assert receipt["source"]["stage"] == "M9-R2"
    assert receipt["source"]["fresh_for_attempt"] is True
    assert receipt["source"]["old_136_137_artifact"] is False
    assert (tmp_path / "r2-contradiction-packet.json").is_file()
