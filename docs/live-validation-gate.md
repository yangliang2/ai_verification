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

## Runner Contract

`python -m aiverify.runner ...` now runs the generic live-validation gate before
it clears logcat, launches the host app, drives a Journey, or evaluates any
oracle. The runner persists the gate JSON as:

```text
<run-dir>/live-validation-gate.json
```

where `<run-dir>` is the parent of the supplied `--artifact-dir`. The run-level
`verdict.json` links this file under `preflight.live_validation_gate`.

If the preflight fails, the runner writes a non-accountable `verdict.json` with:

- `execution.status=non_accountable`
- `execution.reason=live_validation_preflight_failed`
- `metric_context.seed_outcome=not_accountable`
- `l1`, `l2`, and `l3` set to `null`

In that case the host app is not launched by the runner, no Journey is driven,
and no benchmark outcome is created.

Host-specific app smoke is opt-in through Run Spec configuration. It must be
explicit and host-neutral; the runner does not embed Wikipedia defaults.

```yaml
live_validation:
  timeout_seconds: 60
  snippet_chars: 4000
  app_smoke:
    # package/activity default to the top-level Run Spec package/activity when
    # omitted. Set them here only when the smoke target differs.
    target_resource_id: nav_tab_search
    target_content_desc: Search
    app_settle_seconds: 0
```

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

Generate and verify a run-record checksum inventory with:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/<date>-<slug>
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify \
  docs/runs/<date>-<slug>
```

The generated `checksums.sha256` covers every file under the run record except
itself. Verification exits `0` only when every listed artifact is present and
unchanged.

## Benchmark Accounting Rule

A failed live validation gate blocks benchmark outcome accounting. It is an
environment failure, not a caught, missed, false-positive, or passed-control seed
result.

Any future live retry of #23 or another Android seed must use the runner-enforced
preflight or explicitly link a separately captured passing gate record. If the
gate fails, keep the seed open or quarantined and record the failed gate as the
evidence.

A passing generic gate permits app-level smoke work to start. A passing
Wikipedia app-level smoke permits seed-specific matched-pair execution to start.
Neither gate by itself counts as a benchmark seed outcome.

Evidence captured before runner-enforced preflight is legacy evidence. It may
remain valid for the historical claim it originally supported, but it must not
be silently upgraded to the new runner-enforced contract. When legacy evidence is
used in an aggregate, the aggregate must label it as legacy or fail closed if the
required preflight provenance is absent.
