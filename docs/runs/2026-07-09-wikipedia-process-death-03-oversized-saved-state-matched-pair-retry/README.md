# 2026-07-09 Wikipedia process-death-03 oversized saved-state matched-pair retry

Issue: #23
Run spec: `bench/goldset/run-specs/wikipedia-process-death-03-oversized-saved-state.yaml`
Host: `/Users/80268204/hosts/wikipedia`
Device: `emulator-5554`

## Result

Final matched-pair result: **included / caught**.

The successful run uses `app_to_background` as the system-event boundary. The
earlier `dark_mode` attempt in this same run record is retained as diagnostic
evidence: it reached `SearchActivity` but did not trigger
`TransactionTooLargeException`.

## Commands

Targeted regression:

```bash
.venv/bin/pytest tests/bench/test_goldset_process_death_03_oversized_saved_state.py -q
```

Baseline/control build:

```bash
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Baseline/control runner:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-process-death-03-oversized-saved-state.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/background-baseline/artifacts \
  --no-launch
```

Defect patch/build/runner:

```bash
patch --batch -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-process-death-03-oversized-saved-state.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/background-defect/artifacts \
  --no-launch
patch --batch -R -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
```

Both final lanes installed with `adb install -r -d -t --no-streaming` after the
earlier streamed install attempt hung.

## Final Lane Results

| Lane | Build | Setup | Runner | Oracle result |
|---|---|---|---|---|
| `background-baseline` | exit `0`, 23s | all setup commands exit `0`, prelaunch ready attempt 1 | exit `0`, 134s | L1 `inconclusive`, L2 `pass`, L3 not run |
| `background-defect` | exit `0`, 50s | all setup commands exit `0`, prelaunch ready attempt 1 | exit `1`, 122s | L1 `fail`, `crash_stability`; L2 `pass`; L3 not run |

Defect L1 evidence:

- `FATAL EXCEPTION: main`
- `java.lang.RuntimeException: android.os.TransactionTooLargeException: data parcel size 2110592 bytes`

The runner's metric context for the defect lane reports
`seed_outcome=caught`, `failed_oracles=["L1"]`.

## APK Checksums

```text
background-baseline: e3fd4468f07832793d5c8ebf44fe2034c7169726b6b7dbeaba0d5bf1c6626e8c
background-defect:   f876af648d5de85e6b08a0de294df17fa45079eac787d5d8470f55f3cca5e68b
```

## Boundary Diagnostics

The initial `baseline/` and `defect/` lanes used the old `dark_mode` boundary.
They produced valid UI journeys but did not trigger the oversized saved-state
crash:

- baseline: runner exit `0`, L1 `inconclusive`, L2 `pass`;
- defect: runner exit `0`, L1 `inconclusive`, L2 `pass`, `seed_outcome=missed`.

Manual probe `defect/manual-background-probe-2mib/` then pressed Home from the
same defect `SearchActivity` state and captured:

- `FAILED BINDER TRANSACTION` with parcel size `2110572`;
- `FATAL EXCEPTION`;
- `TransactionTooLargeException`;
- `Process org.wikipedia.dev ... has died`.

That probe justified changing the run spec boundary from `dark_mode` to
`app_to_background`.

## Environment And Tool Versions

- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Android emulator: `36.5.11.0`
- Generic live validation gate: passed before the run; post-reboot retry passed
  with a 60s timeout after one 20s `android-layout-json` timeout.
- Wikipedia app smoke gate: passed before the run. A post-install smoke attempt
  during diagnostics failed due cold-start launch timeout and is retained as
  environment evidence, not as a seed verdict.

## Artifact Inventory

Final included evidence:

- `background-baseline/verdict.json`
- `background-baseline/artifacts/after-segment-0/`
- `background-baseline/artifacts/after-event-0/`
- `background-defect/verdict.json`
- `background-defect/artifacts/after-segment-0/`
- `background-defect/artifacts/after-event-0/`
- `background-defect/patch-applied-searchactivity.txt`
- `host-restore-after-background-defect/`
  - includes a post-restore baseline rebuild; restored APK checksum
    `396a3edda8634d0035c5d9794cb0fae51e8d1851f162195889d2c397663308d6`.

Diagnostic evidence:

- `baseline/` and `defect/` old dark-mode matched attempt.
- `defect/manual-background-probe-2mib/`.
- `environment-refresh/` and `environment-refresh-2-defect-install-hang/`.
- `baseline-attempt-*` and `defect/setup-attempt-install-timeout/`.

Screenshots, full checkpoint logcat files, and full checkpoint command traces
were captured during runner evidence collection but were removed before commit
after `git push` failed on large evidence artifacts. The affected
`capture-manifest.json` files mark `screen`, `screen_annotated`, `logcat`, and
`commands` as pruned. Final verdicts, journey results, layout JSON, build/setup
outputs, and critical logcat extracts remain committed. `checksums.sha256`
covers the committed run-record files.

## Known Gaps

- Final accounting relies on the `app_to_background` boundary, not the original
  `dark_mode` boundary.
- The run was performed on emulator `emulator-5554`, not a physical Android
  device.
- Some retained diagnostics show Android CLI or emulator cold-start instability;
  they are preserved to explain why the live validation gate and boundary probe
  were necessary.
- Screenshot PNGs, full checkpoint logcat, and full checkpoint command traces
  are not committed. The retained evidence for final accounting is
  `verdict.json`, journey result JSON, Android layout JSON, critical logcat
  extracts, build/setup outputs, and checksums.
