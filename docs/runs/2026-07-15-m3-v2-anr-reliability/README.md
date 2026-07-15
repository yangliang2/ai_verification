# M3 v2 ANR reliability re-baseline

Date: 2026-07-15 (Asia/Shanghai)

Issue: `#52` (parent `#48`)

Manifest: `bench/goldset/m3-reliability-slice-v2.yaml`

Device: `medium_phone`, `emulator-5554`, Android 16 / API 36

## Result

All six fresh v2 ANR lanes executed through the public reliability runner. Five
lanes were accountable: both accountable baseline controls passed without an
oracle failure, and all three injected-defect repetitions failed L1 with the
expected `crash_stability` class and retained `ANR in org.wikipedia.dev`
evidence. Baseline repetition 3 exhausted its one allowed retry in preflight and
remains outside oracle accounting.

| Metric | Result |
|---|---:|
| Fresh ANR lanes executed | 6/6 |
| Formal attempts | 7 |
| First-attempt accountable | 5/6 |
| Eventual accountable | 5/6 |
| Retries | 1 |
| Accountable baseline controls passed | 2/2 |
| Planned baseline controls accountable | 2/3 |
| Defects caught | 3/3 |
| Preflight-environment failures | 2 |
| Total formal attempt time | 508.567 s |
| Recorded operational interventions | 1 |

This is a partial aggregate over the ANR slice. `progress.json` preserves the
full v2 denominator: 30 planned lanes, 24 still pending. It is not a final M3
claim.

## Lane evidence

| Lane / attempt | Runner exit | Accountability / result | Duration |
|---|---:|---|---:|
| `v2-anr-baseline-1/attempt-1` | 0 | accountable; L1 inconclusive; control passed | 111.695 s |
| `v2-anr-baseline-2/attempt-1` | 0 | accountable; L1 inconclusive; control passed | 95.431 s |
| `v2-anr-baseline-3/attempt-1` | 2 | non-accountable; `android-layout-json` preflight failure | 18.112 s |
| `v2-anr-baseline-3/attempt-2` | 2 | non-accountable; `boot-animation-stopped` preflight failure | 5.430 s |
| `v2-anr-defect-1/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 88.791 s |
| `v2-anr-defect-2/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 77.691 s |
| `v2-anr-defect-3/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 111.417 s |

No accountable result was retried. Both baseline-3 attempts were classified
non-accountable before Journey execution and therefore did not enter oracle
metrics. The retry intervention is stored in `attempt-2/attempt.json`.

## Historical remediation evidence

The original ANR reliability run had two exhausted defect lanes caused by
checkpoint evidence capture and Journey action failures. The remediated paths
from #49 and #50 were exercised directly here:

- All three fresh defect lanes completed both requested Journey actions with
  `PASSED` lineage entries in `codex-journey-action-lineage.json`.
- All three fresh defect lanes retained normalized Journey results, raw event
  streams, checkpoint capture manifests, layout, logcat, screenshots, annotated
  screenshots, and command records.
- The two accountable baseline lanes completed through the same Journey and
  checkpoint paths, giving five successful fresh path executions in total.
- All three fresh defect verdicts cite the retained system ANR lines, including
  `ActivityManager: ANR in org.wikipedia.dev`.
- The historical manifest, #49/#50 remediation records, and original ANR record
  were checked against fixed point `2155727d80546706f643cf9e18442fcea8090609`
  with no differences. Old evidence was not edited.

The historical evidence-capture and Journey failures are therefore remediated
for all three fresh defect repetitions. The remaining exhausted lane is a new
preflight/environment reliability finding, not an oracle miss.

## Exact execution commands

Baseline build, from `/Users/80268204/hosts/wikipedia`:

```bash
mkdir -p aiverify-builds/m3-v2-anr
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-anr/baseline-app-dev-debug.apk
```

Fresh baseline build result: `BUILD SUCCESSFUL in 17s`; 77 tasks (1 executed,
5 from cache, 71 up-to-date); `/usr/bin/time` real 18.33 s.

Defect injection, build, and restoration:

```bash
git apply /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-anr/defect-app-dev-debug.apk
git apply -R /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch
sha256sum app/src/main/java/org/wikipedia/search/SearchFragment.kt
```

Fresh defect build result: `BUILD SUCCESSFUL in 25s`; 77 tasks (1 executed,
5 from cache, 71 up-to-date); `/usr/bin/time` real 26.14 s. The final source
hash was restored to
`324c78af401539508bdbdba117a1b6cd0c7fc8a52189880eff0e1c7b9da88f1f`,
identical to the pre-injection hash.

The initial baseline deployment used this literal Android CLI command:

```bash
android run \
  --apks=/Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-anr/baseline-app-dev-debug.apk \
  --device=emulator-5554
```

It installed and launched package `org.wikipedia.dev`, versionCode `50594`.
Repeating that exact command during baseline-3 recovery remained in its install
phase for more than 90 seconds without an application PID; processes `60177`
and `60176` were terminated. The subsequent recovery commands and observed
results were:

```bash
adb -s emulator-5554 install -r \
  /Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-anr/baseline-app-dev-debug.apk
# Performing Streamed Install; Success

adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell monkey -p org.wikipedia.dev \
  -c android.intent.category.LAUNCHER 1
android layout --device emulator-5554 -p
# Failed to retrieve UI dump: ERROR: null root node returned by UiTestAutomationBridge.

android emulator stop emulator-5554
android emulator start --cold medium_phone
# Exit 1 after the CLI's 300-second readiness timeout:
# Virtual device does not seem to be online after waiting for 300 seconds
# Compatibility log: available 4202 MB; required 5120 MB

android emulator start medium_phone
# CLI reported: Virtual device successfully started as emulator-5554
# The emulator process then exited before adb enumeration; adb listed no device.

/Users/80268204/Library/Android/sdk/emulator/emulator @medium_phone \
  -memory 1536 -no-window -gpu swiftshader_indirect \
  -no-snapshot-load -no-snapshot-save -no-boot-anim \
  -netdelay none -netspeed full
# Emulator 36.5.11.0 started; it raised guest RAM to 2048 MB.

adb -s emulator-5554 install -r \
  /Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-anr/baseline-app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell am start -n \
  org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device emulator-5554 -p \
  > /tmp/m3-v2-recovery-layout.json
# PID 4453; focused activity org.wikipedia.DefaultIcon;
# 38 layout nodes, 5272 bytes.
```

That final headless command intentionally disabled boot animation; the system
property was empty rather than `stopped`, which directly caused baseline-3
attempt 2 to fail the runner's `boot-animation-stopped` preflight check in
5.430 seconds. Before defect execution the emulator was restarted without that
flag:

```bash
adb -s emulator-5554 emu kill
/Users/80268204/Library/Android/sdk/emulator/emulator @medium_phone \
  -no-window -gpu swiftshader_indirect \
  -no-snapshot-load -no-snapshot-save -netdelay none -netspeed full
# adb device ready after 6 polls: sys.boot_completed=1,
# init.svc.bootanim=stopped

adb -s emulator-5554 install -r \
  /Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-anr/defect-app-dev-debug.apk
# Performing Streamed Install; Success
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell am start -n \
  org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device emulator-5554 -p
# PID 3023; bootanim=stopped; 38 layout nodes, 5272 bytes
```

After all defect lanes, the same explicit adb install/start commands were run
with `baseline-app-dev-debug.apk`; they returned `Success`. The final device has
the baseline APK installed and the source tree is restored.

The seven literal public-runner invocations were:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-baseline-1 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-baseline-2 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-baseline-3 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-baseline-3 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python \
  --intervention "Pre-retry recovery: terminated stalled Android CLI deployment; adb fallback still failed independent android-layout-json with null root; Android CLI cold start timed out after 300s; snapshot start exited before adb enumeration; direct same-AVD headless cold boot plus adb reinstall restored app focus and independent layout gate (38 nodes, 5272 bytes)."

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-defect-1 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-defect-2 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  run-lane v2-anr-defect-3 \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
```

The committed partial aggregates were generated with:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output docs/runs/2026-07-15-m3-v2-anr-reliability/plan-after-anr.json
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output docs/runs/2026-07-15-m3-v2-anr-reliability/progress.json
```

## Build outputs and tools

- Installed package: `org.wikipedia.dev`, versionCode `50594`.
- Baseline APK: 121,199,720 bytes; SHA-256
  `dcd9ac00c6ce9af57ed58e997c8c0b1492c59c6964510f58ebf39d55cfca4cf7`.
- Defect APK: 121,545,135 bytes; SHA-256
  `a20ce876573563bef3adbca89948426e09be5a4ecf5a310bbaf705d97f37bc2b`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; emulator `36.5.11.0`; Python `3.12.13`; pytest
  `9.1.1`; Temurin JDK `17.0.19+10`; Gradle `9.5.1`.

The APKs remain external because they total about 243 MB. Their absolute paths,
sizes, and hashes are retained in `environment.json`.

## Artifact inventory

- 7 formal attempt directories and 7 attempt-level checksum manifests.
- 7 attempt records, live-validation gates, verdicts, and stdout/stderr pairs.
- 5 raw Journey event streams, structured results, normalized results, and
  action-lineage records.
- 5 checkpoint capture sets with layout, logcat, command records, capture
  manifests, screenshots, and annotated screenshots.
- Under `lanes/`: 92 files total — 51 JSON, 5 JSONL, 10 PNG, 19 text/log,
  and 7 checksum manifests.
- `plan-after-anr.json`, `progress.json`, `environment.json`, this README, and
  the root `checksums.sha256` inventory.

## Operational interventions and known gaps

- Baseline-3 attempt 1 failed the runner preflight because Android CLI returned
  an empty/null UI root. No Journey ran.
- Before the bounded retry, Android CLI deployment stalled; adb fallback still
  observed the null root; an Android CLI cold start timed out after 300 seconds;
  a snapshot start exited before adb enumeration. A same-AVD direct headless
  cold boot and adb reinstall restored application focus and a 38-node layout.
- That recovery used `-no-boot-anim`, so attempt 2 then failed the independent
  runner check expecting `init.svc.bootanim=stopped`. The two-attempt limit was
  honored; no third attempt was created. Subsequent defect lanes used a normal
  animation cold boot and passed every preflight.
- The host Wikipedia tree is extracted and has no `.git`; restoration was
  verified by the exact patched source-file checksum.
- No physical-device, cross-host, or second-AVD validation was performed. L2 is
  not applicable to this seed, and L3 is outside this ANR slice.

## Verification

The committed evidence contract is covered by
`test_committed_v2_anr_progress_is_derived_from_auditable_attempts`. It derives
the partial aggregate from the public API, verifies every attempt checksum,
enforces the retry/accountability rules, checks all defect lineages and retained
ANR evidence, and verifies the root inventory.

Commands and final results:

```bash
.venv/bin/pytest -q \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_coroutine_03_anr.py \
  tests/runner/test_cli.py tests/runner/test_journey.py
# 120 passed; /usr/bin/time real 12.53 s

.venv/bin/python -m compileall -q src tests
# exit 0

.venv/bin/pytest -q
# 414 passed, 2 warnings; /usr/bin/time real 13.73 s

.venv/bin/pytest --collect-only -q
# 414 tests collected

.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-anr-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-anr-reliability --verify
# checksum inventory verified; 96 covered files
```

The two warnings are existing `DeprecationWarning`s from
`src/aiverify/agent/oracle/l2.py:123` about future XML element truth-value
behavior.

TDD evidence: the new committed-evidence test first failed because `README.md`
did not yet exist, then passed after the run record and root checksum inventory
were created. The first 120-test focused run subsequently exposed three stale
#51 assertions that still required all 30 v2 lanes to be pending (117 passed,
3 failed; real 13.69 s). Updating those assertions to derive the current partial
state produced the final 120-test green run above.

The required two-axis review uses fixed point
`2155727d80546706f643cf9e18442fcea8090609`. The initial Spec review passed.
The initial Standards review requested exact literal deployment and emulator
recovery commands/results, and made a low-priority judgment call against
transient whole-v2 counts in generic tests. Remediation added the seven literal
runner calls and the full deployment/recovery command sequence with salient
outputs, then replaced generic snapshot counts with stable invariants while
retaining exact counts in the dedicated ANR evidence test. After regenerating
the root checksum and rerunning tests, both Standards and Spec re-reviews passed
with no remaining findings.
