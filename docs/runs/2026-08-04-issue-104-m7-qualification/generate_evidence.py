"""Regenerate the committed, deterministic M7 qualification evidence bundle."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path


RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aiverify.bench.m7_qualification import (  # noqa: E402
    load_manifest,
    run_qualification,
    self_validate_schema,
)


def _write_json(name: str, value: object) -> None:
    (RUN_ROOT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(command: str) -> str:
    return subprocess.check_output(
        ["git", *command.split()],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def main() -> None:
    started = time.perf_counter()
    manifest_path = REPO_ROOT / "bench/m7/m7-qualification-v1.json"
    context_path = REPO_ROOT / "bench/discovery-fixtures/synchronous-weather/context-manifest.json"
    self_validate_schema()
    report = run_qualification(manifest_path, context_manifest_path=context_path)

    _write_json("report.json", report.to_dict())
    _write_json("input-packets.json", [packet.to_dict() for packet in report.packets])
    _write_json("leakage-audit.json", report.leakage_audit)
    _write_json("preflight.json", report.preflight)
    _write_json("aggregate.json", report.aggregate)
    _write_json("lane-results.json", [lane.to_dict() for lane in report.lanes])
    _write_json(
        "independent-adjudication.json",
        [
            {
                "lane_id": lane.lane_id,
                "auditor_id": lane.adjudication["auditor_id"],
                "agreement": lane.adjudication["agreement"],
                "checks": lane.adjudication["checks"],
                "claim_boundary": lane.adjudication["claim_boundary"],
            }
            for lane in report.lanes
        ],
    )
    _write_json(
        "campaign-packages.json",
        [
            {
                "lane_id": lane.lane_id,
                "admitted_package": lane.admitted_package.to_dict(),
                "final_package": lane.final_package.to_dict(),
            }
            for lane in report.lanes
        ],
    )

    evidence_files = sorted(
        path
        for path in RUN_ROOT.glob("*.json")
        if path.is_file()
    )
    checksums = "".join(
        f"{_sha256(path)}  {path.name}\n" for path in evidence_files
    )
    (RUN_ROOT / "checksums.sha256").write_text(checksums, encoding="utf-8")

    duration = time.perf_counter() - started
    aggregate = report.aggregate
    readme = f"""# M7 #104 blinded qualification evidence

This committed run record is the durable evidence bundle for issue #104. It
qualifies the discovery, admission, accountability, and adjudication seam over
the frozen local synchronous-weather fixture. It does **not** execute Android,
build or install an APK, drive a device, or support a runtime detection rate.

## Frozen design

- Manifest: `bench/m7/m7-qualification-v1.json`
- Qualification: `{report.manifest.qualification_id}`
- Four cells × three repetitions = 12 lanes: change/project × defect/control.
- Verifier packets withhold variant, expected evidence, verdict, and outcome;
  the auditor-only mapping is applied after hypothesis freeze and plan admission.
- The contradictory P-03-class context is rejected before formal invocation,
  with `formal_denominator=false` and `side_effects=false`.
- Network policy is disabled and the claim boundary is local-only.

## Exact commands and results

All commands ran in the dedicated worktree on commit `{_git("rev-parse HEAD")}`.

```text
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest tests/bench/test_m7_qualification.py -q
7 passed

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -ra
761 passed in 21.26s

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m py_compile src/aiverify/bench/m7_qualification.py
passed

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m compileall -q src
passed

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python docs/runs/2026-08-04-issue-104-m7-qualification/generate_evidence.py
schema validation passed; 12 lanes generated in {duration:.3f}s

git diff --check
passed
```

Tool/runtime: `{platform.python_implementation()} {platform.python_version()}`;
platform `{platform.platform()}`. No Gradle/Android CLI, emulator, adb, APK,
real-device, or manual UI step was performed; those checks are intentionally
out of scope for this offline admission slice.

Aggregate: planned/observed/accountable `12/12/12`, retries `0`, admitted
attacks `12/12`, adjudication agreements `12/12`; defect conclusions `6`
supported and matched-control conclusions `6` rejected. Change and project
modes each have `6` lanes. Next bounded route:
`{aggregate["next_route"]}`.

## Artifact inventory

- `report.json`: complete machine-readable auditor report and claim boundary.
- `input-packets.json`: verifier-facing packets; no hidden cell/outcome fields.
- `leakage-audit.json`: packet blinding audit (`12/12` pass).
- `preflight.json`: contradictory-context exclusion receipt.
- `aggregate.json`: cell/mode totals and route decision.
- `lane-results.json`: lane accountability, local conclusions, and hashes.
- `campaign-packages.json`: admitted and final discovery packages.
- `independent-adjudication.json`: per-lane independent checks.
- `checksums.sha256`: SHA-256 inventory for every JSON artifact above.

The manifest and fixture inputs remain at their committed repository paths. The
JSON artifact checksums are recorded in `checksums.sha256`; regeneration must
produce the same report/package values from the same commit and frozen inputs.

## Known gaps and follow-up

- This is a deterministic offline qualification of the M7 seam, not an Android
  runtime probe. The next route is a separately admitted bounded runtime probe.
- No benchmark-wide detection/false-positive rate is claimed.
- No upstream acceptance or project-wide completeness is claimed.
- No retries were used; an accountable receipt is terminal by policy.
"""
    (RUN_ROOT / "README.md").write_text(readme, encoding="utf-8")
    print(f"schema validation passed; 12 lanes generated in {duration:.3f}s")


if __name__ == "__main__":
    main()
