from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from aiverify.bench.m9_recovery_canary import (
    REVIEW_SCHEMA,
    RUN_SPEC_ROOT,
    M9RecoveryCanaryError,
    _assert_default_receipt,
    _contradiction_gate,
    _oracle_conclusion,
    _reconcile_canary,
)
from aiverify.discovery import FalsificationReviewerIdentity
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


def test_falsification_review_schema_is_valid() -> None:
    schema = json.loads(REVIEW_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


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
        },
        "chain_checks": {"full_chain": True},
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
