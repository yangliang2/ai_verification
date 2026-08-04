# M7 #104 blinded qualification evidence

This committed run record is the durable evidence bundle for issue #104. It
qualifies the discovery, admission, accountability, and adjudication seam over
the frozen local synchronous-weather fixture. It does **not** execute Android,
build or install an APK, drive a device, or support a runtime detection rate.

## Frozen design

- Manifest: `bench/m7/m7-qualification-v1.json`
- Qualification: `m7-temporal-discovery-v1`
- Four cells × three repetitions = 12 lanes: change/project × defect/control.
- The manifest freezes fixture/source identity, change-input checksum, offline
  environment, discovery/context budgets, exclusions, evidence requirements,
  and independent-adjudication checks before lane generation.
- Verifier packets withhold variant, expected evidence, verdict, and outcome;
  the auditor-only mapping is applied after hypothesis freeze and plan admission.
- The contradictory P-03-class context is rejected before formal invocation,
  with `formal_denominator=false` and `side_effects=false`.
- Network policy is disabled and the claim boundary is local-only.

## Exact commands and results

All commands ran in the dedicated worktree on commit `b483a1a57ab7c561dad5c3f78d695483920b6216`.

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
schema validation passed; 12 lanes generated in 0.033s

git diff --check
passed
```

Tool/runtime: `CPython 3.11.15`;
platform `macOS-26.3-arm64-arm-64bit`. No Gradle/Android CLI, emulator, adb, APK,
real-device, or manual UI step was performed; those checks are intentionally
out of scope for this offline admission slice.

Aggregate: planned/observed/accountable `12/12/12`, retries `0`, admitted
attacks `12/12`, adjudication agreements `12/12`; defect conclusions `6`
supported and matched-control conclusions `6` rejected. Change and project
modes each have `6` lanes. Next bounded route:
`proceed_to_bounded_runtime_probe`.

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
