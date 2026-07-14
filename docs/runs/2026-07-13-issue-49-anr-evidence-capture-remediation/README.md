# Issue 49 ANR Evidence-Capture Remediation

Date: 2026-07-13 (America/New_York)

Issue: `#49` under PRD `#48`

Base commit: `05a0182`

## Result

The public Run Spec path now retains bounded diagnostic evidence when Android
layout capture exhausts its retries during an ANR. The checkpoint remains failed,
the run remains `non_accountable`, and L1/L2/L3 remain unexecuted; no partial
artifact is promoted into oracle accounting.

After the primary layout failure, the collector makes one bounded best-effort
attempt for each independent diagnostic phase: screenshot, annotated screenshot,
and logcat. Every phase result and every error is recorded in `commands.json` and
`capture-manifest.json`. The raised `EvidenceCaptureError` carries the partial
checkpoint so `JourneySegmentRunner` and the top-level verdict retain durable
paths to the manifest and whatever diagnostics were successfully captured.

## Historical Reproduction

The regression fixture reproduces the exact important shape from
`anr-defect-1/attempt-2`: Android layout returns exit code 0, empty stdout, and
`Failed to retrieve UI dump:` on stderr until the retry bound is exhausted.

The TDD regression initially failed at the public Journey seam:

```text
FAILED tests/runner/test_journey.py::test_anr_layout_failure_retains_bounded_checkpoint_diagnostics
AssertionError: assert [] == ['after-segment-0']
1 failed
```

After the fix, the same test proves that the failed checkpoint is retained and
that the bounded command phases are exactly two layout attempts followed by one
screenshot, one annotated screenshot, and one logcat attempt.

## Implemented Surface

- `src/aiverify/runner/evidence.py`
  - captures independent diagnostics after a phase failure without relaxing the
    checkpoint success contract;
  - rejects a nominally successful screenshot command when it does not create a
    non-empty artifact;
  - refuses to run in a checkpoint directory containing prior capture artifacts,
    preserving the old files and preventing stale command-to-artifact lineage;
  - aggregates ordered phase errors in the capture manifest;
  - attaches the partial checkpoint to `EvidenceCaptureError`;
  - preserves the configured six-attempt production layout bound and existing
    screenshot/logcat timeouts.
- `src/aiverify/runner/journey.py`
  - retains a failed collector checkpoint in the interrupted Journey flow so the
    top-level non-accountable verdict can link its diagnostics.
- `tests/runner/test_journey.py`
  - reproduces the historical ANR layout failure at the real Journey runner seam.
- `tests/runner/test_cli.py`
  - verifies the public `run(spec, ...)` result is non-accountable, skips all
    oracles, and links the failed checkpoint manifest, screenshot, and ANR logcat.
- `tests/runner/test_evidence.py`
  - verifies bounded best-effort diagnostic collection after command failures and
    timeouts.

## Exact Commands And Results

Focused runner validation:

```bash
.venv/bin/pytest -o addopts='' \
  tests/runner/test_evidence.py \
  tests/runner/test_journey.py \
  tests/runner/test_cli.py -q
# 42 passed in 0.07s
```

Fail-closed reliability and checksum cases:

```bash
.venv/bin/pytest -o addopts='' tests/bench/test_m3_reliability.py \
  -k 'checksum or missing or contradict or partial' -q
# 11 passed, 42 deselected in 0.64s
```

Full repository validation:

```bash
.venv/bin/pytest
# 388 passed in 6.78s
```

Historical package immutability and integrity:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-anr-reliability --verify
# checksum inventory verified

git diff --exit-code origin/main -- \
  docs/runs/2026-07-13-m3-anr-reliability
# exit 0, no output

shasum -a 256 \
  docs/runs/2026-07-13-m3-anr-reliability/checksums.sha256 \
  docs/runs/2026-07-13-m3-anr-reliability/summary.json \
  docs/runs/2026-07-13-m3-anr-reliability/summary.md \
  docs/runs/2026-07-13-m3-anr-reliability/README.md
# 60afc10dfa5cbdd6a66a4aa63095ccbc2958016283df6eac800ec171b40db39d  checksums.sha256
# 3a528891c0eed1becd639bd7ccc3da34c1f2b43c240c962099a108931aada926  summary.json
# fbfcef11e3b630e120ef80f2c56c9a85d67d64f9f14be4d3347c724238295912  summary.md
# 39cfabea6560be08d7ca42abf098b35e1a9ee731a8156caa738bd4ff0ce1e269  README.md

git diff --check
# exit 0, no output

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-issue-49-anr-evidence-capture-remediation
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-issue-49-anr-evidence-capture-remediation --verify
# checksum inventory verified; 1 covered file
```

Tool versions:

```text
Python 3.11.15
pytest 9.0.3
Android CLI 1.0.15498356
Android Debug Bridge 1.0.41 / platform-tools 37.0.0-14910828
```

The first attempted test command used an unavailable global `pytest` executable
and exited 127. It was not treated as a test result; all recorded verification
uses `.venv/bin/pytest`. A first checksum invocation also passed the literal word
`verify` instead of `--verify` and exited with argparse error; the valid command
and result are recorded above.

## Artifact Inventory

- This `README.md`: durable reproduction, implementation, command, result, and
  risk record.
- `checksums.sha256`: complete checksum inventory for this remediation record.
- The implementation and regression tests listed in `Implemented Surface`.
- Historical evidence remains at
  `docs/runs/2026-07-13-m3-anr-reliability/` with no changed files.

The deterministic regression creates temporary layout/screenshot/logcat fixtures
inside pytest's temporary directory. They are intentionally not claimed as durable
device evidence; their artifact shape and contents are asserted by committed tests.

## Device, Build, And Manual Verification

No APK was built, installed, or launched, and no emulator or physical-device
interaction was performed. Package identifier for the historical fixture is
`org.wikipedia.dev`; build duration and app version are not applicable. This issue
changes host-side evidence retention and reproduces the device failure at the
command-runner seam using the exact retained stderr/stdout/return-code shape.

## Known Gaps And Follow-Up Risk

- The remediation does not invent a layout when UIAutomator cannot produce one.
  Such a run correctly remains non-accountable even if screenshot/logcat capture
  succeeds.
- Each independent diagnostic phase can still fail or time out. The manifest's
  ordered `phase_errors`, artifact-existence map, and command records make that
  failure explicit while preserving fixed retry/timeout bounds.
- A reused checkpoint directory now fails before executing a capture command and
  reports the conflicting paths in the non-accountable error. Operators must use
  a fresh attempt directory; the collector never silently overwrites old evidence.
- This issue does not add a new attempt to the historically exhausted ANR lane.
  A fresh versioned tracer and new live lanes are tracked separately under #51
  and #52.
