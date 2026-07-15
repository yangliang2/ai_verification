# M3 v2 Re-baseline Tracer Setup

Date: 2026-07-15 (Asia/Shanghai)

Issue: `#51` under PRD `#48`

Fixed point: `061f4cdd02fde0b9a92b4bbb275756ced6fea8d5`

## Result

The fresh M3 re-baseline tracer is established without executing or extending
any historical lane:

- Slice `m3-verification-agent-reliability-v2`, schema version 2.
- Explicit comparison to the immutable schema-v1 manifest.
- Five selected seeds, baseline/defect roles, three repetitions per role, and
  30 unique planned lanes.
- Public planner result: 30 `pending`, zero attempts, zero reused lane IDs, and
  zero reused or nested historical evidence namespaces.
- The existing bounded policy remains at most two attempts. Every invocation
  uses the public runner's independent live-validation preflight, and an
  accountable outcome cannot be retried.

No denominator is combined. The historical manifest still derives the audited
27/30 result. The strict final summary continues to reject missing lanes, while
the shared `progress` aggregation reports the v2 slice as 30 pending / zero
accountable until #52-#56 populate its fresh lane directories.

## Comparison contract

Schema version 2 requires `comparison_manifest`. Public manifest loading checks:

- different slice ID and disjoint lane IDs;
- unique evidence directories with no equality or parent/child overlap against
  historical lane directories;
- identical `(seed, role, repetition)` population;
- identical Run Spec, expected oracle level, and expected defect class for each
  identity;
- the unchanged two-attempt maximum.

The unchanged per-seed Run Specs preserve matched host, Journey, target surface,
system event, specification, and observation boundary. The planner treats any
non-`attempt-N` content in a lane directory as stale evidence, reports
`invalid_evidence`, and exits 2. Duplicate identities or evidence directories
fail manifest load.

`progress` and the strict final `summary` share one evidence-loading and outcome
classification implementation. Partial output lists pending lane IDs separately;
non-accountable attempts remain only in failure classes, while valid misses,
wrong-oracle results, wrong classes, and false positives remain visible in their
normal outcome maps. The final summary still fails closed on any pending lane.

## Fresh evidence namespaces

| Seed | New package root | Lanes |
|---|---|---:|
| Main-thread ANR | `docs/runs/2026-07-15-m3-v2-anr-reliability/` | 6 |
| Oversized saved state | `docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability/` | 6 |
| Query duplication | `docs/runs/2026-07-15-m3-v2-query-duplication-reliability/` | 6 |
| Swallowed Back | `docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/` | 6 |
| Search-card semantic mismatch | `docs/runs/2026-07-15-m3-v2-search-card-l3-reliability/` | 6 |

These directories do not exist yet. The public reliability runner creates a
lane's `attempt-1` directory only when its child execution issue begins.

## TDD trace

```bash
.venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py::test_rebaseline_manifest_plans_thirty_fresh_pending_lanes
# RED: v2 manifest did not exist; GREEN: 1 passed

.venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py::test_cli_plan_rejects_stale_evidence_in_rebaseline_namespace
# RED: foreign evidence was reported pending; GREEN: invalid_evidence / exit 2

.venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py::test_cli_plan_writes_durable_machine_readable_schedule
# RED: --json-output unrecognized; GREEN: durable JSON generated

.venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py::test_rebaseline_manifest_rejects_nested_historical_evidence_namespace
# RED: nested historical namespace accepted; GREEN: manifest load fails closed
```

## Exact verification commands

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output docs/runs/2026-07-15-issue-51-m3-v2-tracer-setup/plan.json
# exit 0

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output docs/runs/2026-07-15-issue-51-m3-v2-tracer-setup/progress.json
# planned=30; pending=30; eventual_accountable=0; all outcome maps empty

.venv/bin/python -c 'import json; p=json.load(open("docs/runs/2026-07-15-issue-51-m3-v2-tracer-setup/plan.json")); print(len(p)); print(sorted({x["status"] for x in p})); print(len({x["lane_id"] for x in p}))'
# 30; ['pending']; 30 unique lane IDs

git diff --exit-code 05a0182 -- \
  bench/goldset/m3-reliability-slice.yaml \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability \
  docs/runs/2026-07-13-m3-query-duplication-reliability \
  docs/runs/2026-07-13-m3-swallowed-back-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability \
  docs/runs/2026-07-13-m3-final-reliability-baseline
# exit 0; no output

/usr/bin/time -p .venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py tests/bench/test_run_record_checksums.py
# 68 passed in 11.09s; real 11.59s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -o addopts="" -q
# 413 passed, 2 warnings in 12.44s; real 12.70s

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-15-issue-51-m3-v2-tracer-setup
# checksum inventory verified; 3 covered files
```

All six historical run-record checksum inventories (five seed packages plus the
final audit) also verified. The two full-suite warnings are existing
`DeprecationWarning`s at `src/aiverify/agent/oracle/l2.py:123`.

## Hashes and artifact inventory

- Historical manifest SHA-256:
  `8017320a27a5a8e0a01fff1357abf09edf0164abf59e764dc843b5335c0271b3`.
- v2 manifest SHA-256:
  `c4c0cb8f331ae3e09db8663f8041335ef4614181337551962d5b9a662de8e6cb`.
- Pending plan SHA-256:
  `979efb73b0d1a00545ac3ef00f147bf25907935536927c0bbf24a2be7aa744f6`.
- Initial partial-progress SHA-256:
  `99e22c54385de428cfe8b5ff8bcc6d88396f62e0e0416597f4c1b2c31bb58688`.
- Historical package checksum-manifest hashes: ANR `60afc10d...39d`,
  oversized-state `b1570bb1...291`, query-duplication `816c8c73...428`,
  swallowed-Back `5ab4c2f1...be3`, Search-card `44455e93...94a3`, and final
  audit `a07238f5...e1f`.
- Setup artifacts: this README, v2 manifest, generated 30-row `plan.json`, initial
  `progress.json`, and the setup root checksum inventory.

## Tool identity and scope

- Python `3.12.13`; pytest `9.1.1`; Codex CLI `0.144.1`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; Git `2.50.1 (Apple Git-155)`.

No APK build, install, emulator, physical-device, Codex Journey, oracle, or
manual UI execution was performed. There are no new build durations, app IDs,
screenshots, logs, or external APK hashes. #52-#56 own the live packages; #57
owns the final audited old/new comparison. This setup does not claim M3 v2 passed.

## Review

The initial Standards review found two hard documentation gaps: the review result
placeholder and omission of the exact six-record historical checksum loop. The
Spec review found one high-severity gap: strict final aggregation offered no
partial progress model while #52-#56 are incomplete. A non-blocking Standards
judgment also noted anonymous comparison metadata as a small data clump.

The implementation now provides public `progress` output through the same
evidence loader/classifier as strict `summary`, with regressions for pending,
non-accountable, miss, wrong-oracle, wrong-class, false-positive, and old/new
denominator isolation. Comparison metadata uses a named frozen value type. This
record includes the exact historical checksum verification loop below; the root
checksum was regenerated after these review remediations. Final Standards and
Spec re-reviews returned PASS.

Exact historical checksum verification loop:

```bash
for record in \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability \
  docs/runs/2026-07-13-m3-query-duplication-reliability \
  docs/runs/2026-07-13-m3-swallowed-back-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability \
  docs/runs/2026-07-13-m3-final-reliability-baseline
do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    --verify "$record" || exit
done
# six records verified; each printed `checksum inventory verified`
```
