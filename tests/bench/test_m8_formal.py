from __future__ import annotations

from pathlib import Path

from aiverify.bench.m8_formal import _audit_reconciliation, _migration_receipt
from aiverify.bench.m8_qualification import load_manifest
from aiverify.bench.state_evolution import load_state_evolution_contract


def test_m8_audit_reconciles_ordered_twelve_lanes_without_combining_modes(tmp_path: Path) -> None:
    manifest = load_manifest("bench/m8/m8-state-evolution-qualification-v1.json")
    results = []
    for lane in manifest.lanes:
        defect = str(lane["cell_id"]).endswith("defect")
        results.append(
            {
                "lane_id": lane["lane_id"],
                "attempt": 1,
                "accountable": True,
                "oracle_conclusion": "locally_rejected" if defect else "locally_supported",
                "oracle_classification": "stale_state" if defect else "correct_restoration",
            }
        )

    audit = _audit_reconciliation(
        manifest=manifest,
        results=results,
        mapping={"control": "base", "fault": "changed"},
        out=tmp_path / "independent-adjudication.json",
    )

    assert audit["lanes_reconciled"] == 12
    assert audit["qualification_conclusion"] == "locally_supported"
    assert audit["modes"]["change"]["locally_supported"] is True
    assert audit["modes"]["project"]["locally_supported"] is True
    assert audit["claim_boundary"]["no_combined_mode_rate"] is True


def test_m8_migration_receipt_is_bound_to_contract_and_observation(tmp_path: Path) -> None:
    contract = load_state_evolution_contract(
        "bench/discovery-fixtures/state-evolution/contract.json"
    )
    observations = tmp_path / "state-observations.json"
    observations.write_text("{}\n", encoding="utf-8")

    receipt = _migration_receipt(contract, observations)

    assert receipt["status"] == "passed"
    assert receipt["count"] == 1
    assert receipt["edge_id"] == contract.migration.edge_id
    assert receipt["provenance"]["sha256"]
