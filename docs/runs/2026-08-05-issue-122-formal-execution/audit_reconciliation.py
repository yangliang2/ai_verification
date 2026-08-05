"""Reproduce the post-run independent M8 reconciliation without rerunning lanes."""

from __future__ import annotations

import argparse
import json
import tempfile
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
    output = args.output
    temporary_output: Path | None = None
    if output.exists():
        handle = tempfile.NamedTemporaryFile(prefix="m8-audit-", suffix=".json", delete=False)
        temporary_output = Path(handle.name)
        handle.close()
        temporary_output.unlink()
        audit_output = temporary_output
    else:
        audit_output = output
    audit = _audit_reconciliation(
        manifest=load_manifest(args.manifest),
        results=results,
        mapping={"control": "base", "fault": "changed"},
        out=audit_output,
        preflight=json.loads(args.preflight.read_text(encoding="utf-8")),
        artifact_root=args.artifact_root,
        contract=load_state_evolution_contract(args.contract),
    )
    if temporary_output is not None:
        generated = json.loads(temporary_output.read_text(encoding="utf-8"))
        expected = json.loads(output.read_text(encoding="utf-8"))
        if generated != expected:
            raise SystemExit("existing adjudication artifact does not match regenerated audit")
        temporary_output.unlink()
    print(
        json.dumps(
            {
                "output": str(output),
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
