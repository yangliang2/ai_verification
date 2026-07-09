# Live Validation Gate

The live validation gate is the required preflight before new Android live-run
evidence can enter benchmark accounting. It separates an unhealthy execution
environment from a seed outcome.

## Required Checks

The generic environment gate passes only when all checks pass for the selected
device:

| Check | Command | Pass condition |
|---|---|---|
| adb device present | `adb devices -l` | Device serial is listed with state `device`. |
| boot completed | `adb -s <device> shell getprop sys.boot_completed` | Stdout is `1`. |
| boot animation stopped | `adb -s <device> shell getprop init.svc.bootanim` | Stdout is `stopped`. |
| Android CLI layout JSON | `android layout --pretty --device <device>` | Exit code is 0 and stdout is a JSON list. |
| direct UIAutomator dump | `adb -s <device> shell uiautomator dump /sdcard/window_dump.xml` | Exit code is 0. |

The Android CLI layout and direct UIAutomator checks are both required because
the 2026-07-09 #23 retry failed in that channel after boot completed.

## CLI

Run the generic gate with:

```bash
PYTHONPATH=src python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --output docs/runs/<date>-live-validation-gate/live-validation-gate.json
```

The command exits `0` when the gate passes and `2` when any check fails. The JSON
payload is written to stdout and to `--output` when provided.

Run an app-level Wikipedia smoke gate by adding the app package, launcher
activity, and target surface criteria:

```bash
PYTHONPATH=src python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --app-package org.wikipedia.dev \
  --app-activity org.wikipedia.DefaultIcon \
  --target-resource-id nav_tab_search \
  --target-content-desc Search \
  --output docs/runs/<date>-wikipedia-app-smoke-gate/live-validation-gate.json
```

The app-level smoke first runs the generic gate, then launches the app with an
explicit launcher intent, checks that the package appears in foreground window
state, and verifies that one Android CLI layout node matches all supplied target
surface criteria. This is still a gate, not a seed journey: it proves the app
entry surface is healthy enough to start seed-specific baseline/defect work.

## Artifact Contract

The gate JSON contains:

- `schema_version`
- overall `status`
- target `device`
- optional `app` package, activity, and target surface metadata
- `failed_checks`
- per-check command args, status, return code, stdout/stderr snippets, timeout,
  truncation flags, and error reason

For non-trivial validation work, store the JSON under `docs/runs/` with a README
that records tool versions, command transcript, artifact inventory, checksums,
and known gaps.

## Benchmark Accounting Rule

A failed live validation gate blocks benchmark outcome accounting. It is an
environment failure, not a caught, missed, false-positive, or passed-control seed
result.

Any future live retry of #23 or another Android seed must link a passing gate
record before collecting baseline/defect matched-pair evidence. If the gate
fails, keep the seed open or quarantined and record the failed gate as the
evidence.

A passing generic gate permits app-level smoke work to start. A passing
Wikipedia app-level smoke permits seed-specific matched-pair execution to start.
Neither gate by itself counts as a benchmark seed outcome.
