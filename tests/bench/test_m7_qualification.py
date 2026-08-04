"""Contract tests for the frozen, blinded M7 qualification slice."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from aiverify.bench.m7_qualification import (
    M7QualificationError,
    audit_packet,
    load_manifest,
    run_qualification,
    self_validate_schema,
)


_ROOT = Path(__file__).parents[2]
_MANIFEST = _ROOT / "bench/m7/m7-qualification-v1.json"
_CONTEXT = _ROOT / "bench/discovery-fixtures/synchronous-weather/context-manifest.json"


def _report():
    return run_qualification(_MANIFEST, context_manifest_path=_CONTEXT)


def test_frozen_manifest_schema_and_semantics() -> None:
    self_validate_schema()
    manifest = load_manifest(_MANIFEST)

    assert manifest.qualification_id == "m7-temporal-discovery-v1"
    assert manifest.document["status"] == "frozen"
    assert [cell["cell_id"] for cell in manifest.cells] == [
        "change-defect",
        "change-control",
        "project-defect",
        "project-control",
    ]
    assert all(cell["repetitions"] == 3 for cell in manifest.cells)
    assert manifest.document["policy"]["blinding"]["network_disabled"] is True
    assert manifest.document["source_identity"]["fixture_id"] == "synchronous-weather-v1"
    assert manifest.document["source_identity"]["change_input"]["path"].endswith(
        "weather-delay.diff"
    )
    assert manifest.document["environment"] == {
        "runner": "local-python",
        "network": "disabled",
        "android_execution": False,
        "device": "none",
    }
    assert manifest.document["budgets"]["discovery_budget"] == 8
    assert manifest.document["evidence"]["checksums_required"] is True
    assert manifest.document["adjudication"]["independent"] is True
    assert manifest.document["contradictory_preflight"]["formal_denominator"] is False


def test_qualification_has_exact_four_cells_and_twelve_accountable_lanes() -> None:
    report = _report()
    aggregate = report.aggregate

    assert len(report.packets) == 12
    assert len(report.lanes) == 12
    assert aggregate["planned_lanes"] == aggregate["observed_lanes"] == 12
    assert aggregate["accountable_lanes"] == 12
    assert aggregate["retry_count"] == 0
    assert aggregate["adjudication_agreements"] == 12
    assert aggregate["contradictory_preflight_excluded"] is True
    assert aggregate["next_route"] == "proceed_to_bounded_runtime_probe"

    for cell_id, cell in aggregate["cells"].items():
        assert cell["planned_lanes"] == cell["observed_lanes"] == 3
        assert cell["admitted_attacks"] == 3
        assert cell["accountable_lanes"] == 3
        assert cell["retry_count"] == 0
        assert cell["adjudication_agreements"] == 3
        assert len(cell["local_conclusions"]) == 3
        if cell_id.endswith("defect"):
            assert cell["local_conclusions"] == ["supported"] * 3
        else:
            assert cell["local_conclusions"] == ["rejected"] * 3

    assert aggregate["modes"]["change"]["observed_lanes"] == 6
    assert aggregate["modes"]["project"]["observed_lanes"] == 6
    assert aggregate["defect_supporting_conclusions"] == 6
    assert aggregate["matched_control_non_supporting_conclusions"] == 6


def test_verifier_packets_withhold_variant_expected_evidence_and_verdict() -> None:
    report = _report()
    assert report.leakage_audit["status"] == "pass"
    assert report.leakage_audit["packet_count"] == 12
    assert all(audit_packet(packet)["status"] == "pass" for packet in report.packets)

    serialized = json.dumps(
        [packet.to_dict() for packet in report.packets],
        sort_keys=True,
    ).lower()
    for term in ("defect", "control", "variant", "verdict", "oracle", "supported"):
        assert term not in serialized

    assert all(packet.diff_ref is not None for packet in report.packets[:6])
    assert all(packet.diff_ref is None for packet in report.packets[6:])


def test_each_lane_freezes_and_admits_before_one_accountable_attempt() -> None:
    report = _report()

    for lane in report.lanes:
        record = lane.to_dict()
        assert record["hypothesis_frozen"] is True
        assert record["plan_admitted"] is True
        assert record["attempt_count"] == 1
        assert record["retry_count"] == 0
        assert record["accountable"] is True
        assert record["adjudication"]["agreement"] is True
        assert record["adjudication"]["checks"]["hypothesis_frozen_before_oracle"] is True
        assert record["adjudication"]["checks"]["plan_admitted_before_oracle"] is True
        assert record["adjudication"]["checks"]["hypothesis_relevance"] is True
        assert record["adjudication"]["checks"]["causal_chain"] is True
        assert record["adjudication"]["checks"]["experiment_validity"] is True
        assert record["adjudication"]["checks"]["accountable_receipt"] is True
        assert record["adjudication"]["checks"]["finding_support"] is True
        assert record["adjudication"]["checks"]["residual_risk_honesty"] is True
        assert record["adjudication"]["checks"]["leakage_boundary"] is True
        assert lane.final_package.campaign.residual_risks == ()


def test_contradictory_preflight_is_rejected_without_formal_side_effects() -> None:
    preflight = _report().preflight

    assert preflight["status"] == "rejected"
    assert preflight["formal_denominator"] is False
    assert preflight["side_effects"] is False
    assert preflight["route"] == "exclude_before_formal_invocation"
    assert "no synchronous path" in preflight["reason"]


def test_qualification_regeneration_is_deterministic() -> None:
    first = _report().to_dict()
    second = _report().to_dict()

    assert first == second
    assert [lane["package_sha256"] for lane in first["lanes"]] == [
        lane["package_sha256"] for lane in second["lanes"]
    ]


def test_manifest_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    tampered = deepcopy(document)
    tampered["policy"]["planned_lanes"] = 11
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(M7QualificationError, match="planned_lanes"):
        load_manifest(path)
