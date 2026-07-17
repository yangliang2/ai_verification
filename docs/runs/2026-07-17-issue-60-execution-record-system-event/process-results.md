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

## Network requested-state postcondition probe

The post-review API-35 probe exercised the production injector for both network
events, re-read both requested settings after each event, and restored the exact
captured initial state in a `finally` block:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python - <<'PY'
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.run_spec import SystemEventSpec
from aiverify.runner.system_events import DeviceSystemEventInjector

serial = "emulator-5554"
package = "org.wikipedia.dev"
activity = "org.wikipedia.DefaultIcon"
device = DeviceController(serial=serial)
injector = DeviceSystemEventInjector(
    device=device,
    package=package,
    activity=activity,
)

def setting(name, result):
    if result.returncode != 0:
        raise RuntimeError(f"{name}: {result.stderr or result.stdout}")
    return result.stdout.strip()

def observed():
    return (
        setting("wifi_on", device.get_wifi_setting()),
        setting("mobile_data", device.get_mobile_data_setting()),
    )

original_wifi, original_mobile = observed()
print(f"original: wifi_on={original_wifi} mobile_data={original_mobile}")
try:
    injector.inject(SystemEventSpec(step_index=0, event="network_off"))
    wifi, mobile = observed()
    print(f"network_off: passed; wifi_on={wifi} mobile_data={mobile}")
    injector.inject(SystemEventSpec(step_index=1, event="network_on"))
    wifi, mobile = observed()
    print(f"network_on: passed; wifi_on={wifi} mobile_data={mobile}")
finally:
    restore_wifi = device.set_wifi(enabled=original_wifi == "1")
    restore_mobile = device.set_mobile_data(enabled=original_mobile == "1")
    if restore_wifi.returncode != 0 or restore_mobile.returncode != 0:
        raise RuntimeError("network restoration command failed")
    wifi, mobile = observed()
    print(f"restored: wifi_on={wifi} mobile_data={mobile}")
    if (wifi, mobile) != (original_wifi, original_mobile):
        raise RuntimeError("network restoration postcondition failed")
print("network postcondition probe: passed")
PY
```

```text
original: wifi_on=1 mobile_data=1
network_off: passed; wifi_on=0 mobile_data=0
network_on: passed; wifi_on=1 mobile_data=1
restored: wifi_on=1 mobile_data=1
network postcondition probe: passed
```

## Foreground/background postcondition probe

The post-review API-35 probe exercised the production injector with its default
5.0-second timeout and 0.1-second polling interval. The initial state was Wikipedia
foreground, and the final foreground state was restored:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python - <<'PY'
import time
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.run_spec import SystemEventSpec
from aiverify.runner.system_events import DeviceSystemEventInjector

serial = "emulator-5554"
package = "org.wikipedia.dev"
activity = "org.wikipedia.DefaultIcon"
device = DeviceController(serial=serial)
injector = DeviceSystemEventInjector(
    device=device,
    package=package,
    activity=activity,
)

def resumed_line() -> str:
    result = device.get_resumed_activity()
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if "topResumedActivity" in line
    ]
    if not lines:
        raise RuntimeError("topResumedActivity was not observable")
    return lines[0]

print(f"initial: {resumed_line()}")
for event_name in ("app_to_background", "app_to_foreground"):
    started = time.monotonic()
    injector.inject(SystemEventSpec(step_index=0, event=event_name))
    elapsed = time.monotonic() - started
    print(f"{event_name}: passed in {elapsed:.3f}s")
    print(f"observed: {resumed_line()}")
print("lifecycle postcondition probe: passed")
PY
```

```text
initial: topResumedActivity=ActivityRecord{4347385 u0 org.wikipedia.dev/org.wikipedia.DefaultIcon t109}
app_to_background: passed in 0.060s
observed: topResumedActivity=ActivityRecord{9e7ff29 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t44}
app_to_foreground: passed in 0.099s
observed: topResumedActivity=ActivityRecord{c6cf977 u0 org.wikipedia.dev/org.wikipedia.DefaultIcon t109}
lifecycle postcondition probe: passed
```

## Device restoration

After all probes, the exact initial state was restored and re-read:

```bash
adb -s emulator-5554 shell settings get system accelerometer_rotation
adb -s emulator-5554 shell settings get system user_rotation
adb -s emulator-5554 shell cmd uimode night
adb -s emulator-5554 shell settings get global wifi_on
adb -s emulator-5554 shell settings get global mobile_data
adb -s emulator-5554 shell dumpsys activity activities | \
  rg -m 1 'topResumedActivity'
```

```text
1
0
Night mode: no
1
1
topResumedActivity=ActivityRecord{c6cf977 u0 org.wikipedia.dev/org.wikipedia.DefaultIcon t109}
```

In command order these are `accelerometer_rotation=1`, `user_rotation=0`, night
mode `no`, `wifi_on=1`, and `mobile_data=1`.
