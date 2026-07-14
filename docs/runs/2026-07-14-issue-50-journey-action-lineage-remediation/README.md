# Journey Action-Lineage Remediation

Date: 2026-07-14 (Asia/Shanghai)

Issue: `#50`

Fixed point: `8fdf46756fe2974c0d7f4d4a0397432ba4c609b4`

## Result

The host-side remediation passes the public Run Spec / runner seam for both
historical failure shapes without changing the original M3 evidence:

- The backend reports only stable `action-N` IDs. When result count, ID order,
  Journey identity, and status are exact, the runner deterministically restores
  the requested action text. The raw backend result, normalized result, event
  stream, and explicit action-lineage record are all kept.
- A dispatched ANR-triggering input action remains `PASSED` at the driver layer;
  the resulting ANR is product evidence and L1 catches it as `crash_stability`.
- A UI interaction that was not dispatched remains `FAILED`, produces a
  non-accountable `journey_action_failed` result, and does not run any oracle.
- Missing results or IDs, duplicated/reordered IDs, a wrong Journey, any backend
  supplied action text (including a paraphrase or contradiction), unknown statuses,
  FAILED, and SKIPPED results all fail closed.

This is remediation evidence, not a new M3 measurement. The historical `27/30
FAILED` package and its exhausted attempts remain immutable. The fresh 30-lane
re-baseline is tracked separately by #51-#57.

## Public-runner probes

| Probe | Execution | Oracle result | Verdict SHA-256 |
|---|---|---|---|
| `test_public_run_restores_searc0` | completed; accountable | L1/L2 inconclusive; no L3 | `e8fed41bebb00c36a3c6bfb9e21f7b8271555139308a6d8059f49ca1cb2b9689` |
| `test_public_run_reproduces_his0` | non-accountable / `journey_action_failed` | all oracles not run | `421fec11f280936835686aef5793227259c9bfc4855cec202146b8ea7c2d0cf4` |
| `test_public_run_keeps_dispatch0` | completed; accountable | L1 fail / `crash_stability` | `3f0b4749c68ccf60c7f2f7205790e8c6bd6c00c151fc68d93f941ef48935de72` |

The probe names are pytest's deterministic basetemp directories. Each probe has
its runner verdict, passing live-validation fixture, checkpoint fixture, raw
backend result, normalized result, JSONL event stream, and action-lineage JSON.

## Protocol and implementation

- `src/aiverify/runner/journey.py` emits stable 1-based action IDs, validates
  action count/ID/order/Journey/status and the absence of backend-supplied action
  text, restores exact requested text by ID, writes normalized and lineage artifacts,
  and still rejects failed actions.
- `src/aiverify/runner/journey_result_schema.json` makes `action_id` mandatory and
  restricts it to `action-[1-9][0-9]*`.
- `src/aiverify/runner/cli.py` defines dispatch-vs-product-outcome semantics and
  links raw/normalized/lineage evidence from non-accountable verdicts.
- `tests/runner/test_journey.py`, `tests/runner/test_codex_backend.py`, and
  `tests/runner/test_cli.py` cover the protocol and both public-runner shapes.

The normalization is deliberately narrow: only an opaque, exact stable ID can map
back to the requested action text. Natural-language action text is outside the backend
protocol, so even a plausible paraphrase accompanied by a valid ID is rejected. An ID
mismatch, duplicate, reorder, wrong Journey, or extra action text stops the run. No
status is inferred from screenshots, layouts, comments, or apparent UI state.

## TDD trace

Representative red commands and results:

```bash
.venv/bin/pytest -q tests/runner/test_journey.py::test_segment_to_journey_xml_assigns_stable_action_ids
# FAILED: action elements had no stable ids

.venv/bin/pytest -q tests/runner/test_journey.py::test_stable_action_id_restores_exact_requested_action
# FAILED: stable action IDs and deterministic requested-text restoration did not exist

.venv/bin/pytest -q tests/runner/test_codex_backend.py::test_codex_backend_rejects_result_without_action_id
# FAILED: missing action_id was accepted by the output schema

.venv/bin/pytest -q tests/runner/test_cli.py::test_instruction_prefix_separates_action_dispatch_from_product_outcome
# FAILED: driver prompt did not define dispatch-vs-product semantics

.venv/bin/pytest -q tests/runner/test_journey.py::test_unknown_action_status_fails_closed_when_backend_bypasses_schema
# FAILED: unknown status OBSERVED did not interrupt the run

.venv/bin/pytest -q 'tests/runner/test_journey.py::test_invalid_action_lineage_fails_closed[unrelated-action-text]'
# FAILED: a valid ID could be paired with arbitrary backend-supplied action text
```

Each test was rerun after its minimal implementation and passed before the next
vertical slice was added.

## Exact verification commands

Durable public-runner probes:

```bash
mkdir -p docs/runs/2026-07-14-issue-50-journey-action-lineage-remediation
.venv/bin/pytest -o addopts="" -q \
  tests/runner/test_cli.py::test_public_run_restores_search_card_action_from_stable_id \
  tests/runner/test_cli.py::test_public_run_reproduces_historical_anr_failed_status \
  tests/runner/test_cli.py::test_public_run_keeps_dispatched_anr_trigger_accountable_for_l1 \
  --basetemp docs/runs/2026-07-14-issue-50-journey-action-lineage-remediation/public-runner-probes
# 3 passed in 0.16s
```

Historical immutability and hashes:

```bash
git diff --exit-code 05a0182 -- \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability
# exit 0; no output

shasum -a 256 \
  docs/runs/2026-07-13-m3-anr-reliability/checksums.sha256 \
  docs/runs/2026-07-13-m3-search-card-l3-reliability/checksums.sha256
# 60afc10dfa5cbdd6a66a4aa63095ccbc2958016283df6eac800ec171b40db39d  ANR
# 44455e93de3b8586549c6e0534b2b6b4d9ee50f513c4ca3a2138a54b759594a3  Search-card
```

Focused and full verification:

```bash
/usr/bin/time -p .venv/bin/pytest -o addopts="" -q \
  tests/runner/test_codex_backend.py tests/runner/test_journey.py \
  tests/runner/test_cli.py tests/bench/test_m3_reliability.py
# 106 passed in 9.88s; real 10.22s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -o addopts="" -q
# 402 passed, 2 warnings in 11.63s; real 11.92s

.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-14-issue-50-journey-action-lineage-remediation
.venv/bin/python -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-14-issue-50-journey-action-lineage-remediation
# wrote 31 checksums; verified 31 checksums
```

The two warnings are existing `DeprecationWarning`s at
`src/aiverify/agent/oracle/l2.py:123` about future Element truth-value behavior.

An earlier probe command omitted creation of the run-record parent directory.
Pytest reported 3 setup errors before executing any test. The corrected command
above creates the parent first and passed all three probes.

## Artifact inventory

- 3 runner verdicts and 3 live-validation fixture reports.
- 3 raw Journey results, 3 normalized results, 3 action-lineage records, and 3
  JSONL event streams.
- 3 checkpoint fixture sets: layout, screenshot, logcat, and commands.
- 30 probe files total: 21 JSON, 3 JSONL, 3 PNG, and 3 text files.
- This README and the final root `checksums.sha256` inventory.

## Tool and environment identity

- Python `3.12.13`; pytest `9.1.1`; Codex CLI `0.144.1`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; Git `2.50.1 (Apple Git-155)`.
- Historical application package: `org.wikipedia.dev`.

## Known gaps and scope

- No APK build, install, emulator, physical-device, or manual UI work was performed.
  Build duration, application version, and new external APK hashes are not applicable.
- These deterministic probes exercise the public Run Spec / runner seam with retained
  historical response shapes and command/log fixtures. A real Codex CLI + Android live
  evaluation belongs to the fresh versioned re-baseline, not this remediation record.
- Stable IDs eliminate paraphrase/reorder ambiguity; they do not make a
  malicious backend trustworthy. Command/event evidence and oracle evidence remain
  independently auditable.
- The original M3 attempts, summaries, and 27/30 FAILED decision were not modified.

## Review

Parallel Standards and Spec reviews were run against fixed point `8fdf467`. The
Standards review found stale handoff status, an unfinished checksum placeholder,
and duplicated action-ID formatting. The Spec review found that accepting arbitrary
text beside a valid ID was broader than the issue allowed, and that the historical
ANR `FAILED` response shape had not been reproduced directly.

All findings were remediated: action IDs now use one formatter; the backend schema is
ID-only; any extra action text fails closed; the public probes pair the historical ANR
`FAILED` response with the repaired dispatched-`PASSED`/L1-caught path; this record,
checksums, and `HANDOFF.md` are finalized before commit.
