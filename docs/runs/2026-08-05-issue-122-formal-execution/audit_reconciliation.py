"""Reproduce the post-run independent M8 reconciliation without rerunning lanes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aiverify.bench.m8_formal import _audit_reconciliation
from aiverify.bench.m8_qualification import load_manifest
from aiverify.bench.state_evolution import load_state_evolution_contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [
        json.loads(line)
        for line in args.inventory.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audit = _audit_reconciliation(
        manifest=load_manifest(args.manifest),
        results=results,
        mapping={"control": "base", "fault": "changed"},
        out=args.output,
        preflight=json.loads(args.preflight.read_text(encoding="utf-8")),
        artifact_root=args.artifact_root,
        contract=load_state_evolution_contract(args.contract),
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "qualification_conclusion": audit["qualification_conclusion"],
                "checks": len(audit["checks"]),
                "ordered_lanes": audit["lanes_reconciled"],
                "accountable": sum(1 for item in results if item.get("accountable")),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
