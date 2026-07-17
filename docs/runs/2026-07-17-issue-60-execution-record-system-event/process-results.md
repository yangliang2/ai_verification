# Public runner process results

All commands ran from `/Users/peter/projects/ai_verfication` against
`emulator-5554`. Before each rotate attempt the device was forced to portrait
with `accelerometer_rotation=0` and `user_rotation=0`.

## Discovery attempt: preserved non-accountable retry input

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/success-run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-17-issue-60-execution-record-system-event/success-attempt/artifacts \
  --workdir /Users/peter/hosts/wikipedia
```

```text
scenario: issue-60-rotate-success
execution: non_accountable (journey_backend_error)
exit 2
```

The backend completed its Android layout command, but Codex 0.144.5 did not
create its relative `--output-last-message` path after changing to the host
workdir. Attempt `cff4d1b1-5cc4-4c11-9e67-a33248472dac` was atomically finalized
and retained. It was not overwritten by later retries.

## Absolute-path success attempts

Attempts 2 and 3 used the same public command with an absolute artifact path:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-60-execution-record-system-event/success-run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-60-execution-record-system-event/success-attempt-3/artifacts \
  --workdir /Users/peter/hosts/wikipedia
```

```text
scenario: issue-60-rotate-success
L1: inconclusive (None)  |  L2: pass (None)  |  L3: not run
exit 0
```

Attempt 3 is the primary visual evidence: its complete portrait and landscape
Wikipedia frames were manually inspected.

## Final relative-path success

After resolving backend artifact paths before changing cwd, the original
relative-path form succeeded as a fresh fourth attempt:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/success-run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-17-issue-60-execution-record-system-event/success-attempt-4/artifacts \
  --workdir /Users/peter/hosts/wikipedia
```

```text
scenario: issue-60-rotate-success
L1: inconclusive (None)  |  L2: pass (None)  |  L3: not run
exit 0
```

## Forced failed event

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-60-execution-record-system-event/failed-run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-60-execution-record-system-event/failed-attempt/artifacts \
  --workdir /Users/peter/hosts/wikipedia
```

```text
scenario: issue-60-forced-event-failure
execution: non_accountable (system_event_error)
exit 2
```

The injected command was:

```bash
adb -s emulator-5554 shell pm revoke \
  org.wikipedia.dev android.permission.DOES_NOT_EXIST
```

It returned 255 with `IllegalArgumentException: Unknown permission`. The runner
retained `after-segment-0`, created no `after-event-0`, wrote no L1/L2/L3
outcome, and finalized attempt `498b3cba-1515-4ba5-97d7-02d6d454cf2a` as
`interrupted / system_event_error / exit 2`.

## Device restoration

After all probes, the exact initial state was restored and re-read:

```text
accelerometer_rotation=1
user_rotation=0
Night mode: no
wifi_on=1
mobile_data=1
```
