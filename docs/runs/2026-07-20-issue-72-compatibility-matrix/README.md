# Issue #72 Arabic RTL compatibility matrix

Status: complete. Implementation, live execution, automated verification, the
one required independent verification, and the final checksum inventory are
durably recorded here.

This run supports one bounded local conclusion. On two API-35 emulator profiles,
the baseline preserves localized resources, sentinel state, and correct logical
start/end ordering across English phone portrait, Arabic phone portrait, Arabic
phone landscape, and Arabic tablet landscape. A matched one-line candidate that
forces the anchor row to LTR remains healthy in the English control and is rejected
in all three Arabic cells. This is not a benchmark-wide coverage, detection-rate,
Goldset, accessibility, OEM/device-fleet, or upstream-acceptance claim.

## Preregistered matrix and results

| Cell | AVD / serial | Effective configuration | Baseline anchor x | Candidate anchor x | Result |
| --- | --- | --- | --- | --- | --- |
| phone-en-portrait | `aiverify_api35` / `emulator-5554` | `en-US`, portrait, width/smallest `411/411dp` | start 301, end 778 | start 301, end 778 | both supported control |
| phone-ar-portrait | `aiverify_api35` / `emulator-5554` | `ar-EG`, portrait, width/smallest `411/411dp` | start 778, end 301 | start 301, end 778 | candidate rejected |
| phone-ar-landscape | `aiverify_api35` / `emulator-5554` | `ar-EG`, landscape, width/smallest `914/411dp` | start 1768, end 631 | start 631, end 1768 | candidate rejected |
| tablet-ar-landscape | `aiverify_tablet_api35` / `emulator-5556` | `ar-EG`, landscape, width/smallest `1280/800dp` | start 1896, end 664 | start 664, end 1896 | candidate rejected |

`baseline/aggregate.json` is accountable `locally_supported` with all four cells
supported. `candidate/aggregate.json` is accountable `locally_rejected`: the
English control is supported and the three Arabic cells are classified
`rtl_relative_order_violation`. All eight canonical runner invocations completed
with exit 0, L1 inconclusive (no crash/ANR), L2 pass for localized semantics and
sentinel state, and no L3 invocation. The dedicated matrix oracle supplies the
geometry classification.

## Matched inputs and identity

The baseline APK SHA-256 is
`1b6df13a0c50ce9a9bd4d70f0d8a80888fc34bab8b190c1a6d3f13f4a9d7efdf`.
The candidate APK SHA-256 is
`8f2c045ed117557e222d1e38a28a7c11ff62429436a245acec3e6564731feb69`.
Every lane records an identical local and installed APK hash. The candidate source
diff is one line: the anchor row changes from
`LAYOUT_DIRECTION_LOCALE` to `LAYOUT_DIRECTION_LTR`. Baseline phone lanes used
host commit `40cf22a`; the corrected tablet lane used `d468110`; candidate lanes
used `bddd20c` plus the frozen one-line patch. The executable baseline APK hash is
identical across those documentation/Run-Spec commits. Baseline/candidate actions,
locale/rotation/cleanup events, assertions, package/activity, API level, and device
profile allocation match apart from role metadata, target rotation derived from
the profile's natural orientation, and the intended defect.

The phone and tablet both use API 35 and fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
Effective Execution Identity records AVD names `aiverify_api35` and
`aiverify_tablet_api35`. Android CLI is `1.0.15498356`; adb is `1.0.41 / 37.0.0-14910828`;
Codex CLI is `0.144.6`; Python is `3.11.15`.

## Exact verification commands

~~~sh
bench/fixtures/lifecycle-recovery-app/gradlew \
  -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
# baseline BUILD SUCCESSFUL in 6s; 33 tasks; candidate BUILD SUCCESSFUL in 3s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest \
  -o addopts='' -q tests/bench/test_compatibility_matrix.py \
  tests/runner/test_system_events.py tests/runner/test_journey.py \
  tests/runner/test_run_spec.py tests/harness/test_device_controller.py \
  --junitxml=docs/runs/2026-07-20-issue-72-compatibility-matrix/verification/focused-pytest.xml
# 176 passed in 0.205s (JUnit suite time)

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest \
  -o addopts='' -q \
  --junitxml=docs/runs/2026-07-20-issue-72-compatibility-matrix/verification/full-pytest.xml
# 639 passed in 16.591s (JUnit suite time)

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  -m aiverify.bench.compatibility_matrix \
  --contract bench/capability-slices/compatibility-matrix/contract.json \
  --layouts docs/runs/2026-07-20-issue-72-compatibility-matrix/baseline \
  --runner-lanes \
  --output docs/runs/2026-07-20-issue-72-compatibility-matrix/baseline/aggregate.json
# exit 0; accountable locally_supported

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  -m aiverify.bench.compatibility_matrix \
  --contract bench/capability-slices/compatibility-matrix/contract.json \
  --layouts docs/runs/2026-07-20-issue-72-compatibility-matrix/candidate \
  --runner-lanes \
  --output docs/runs/2026-07-20-issue-72-compatibility-matrix/candidate/aggregate.json
# expected exit 1; accountable locally_rejected
~~~

Each runner lane used the public `python -m aiverify.runner <run-spec> --device
<serial> --artifact-dir <lane>/artifacts --workdir
/Users/peter/hosts/aiverify-issue-72` seam. The eight exact consumed Run Specs,
arguments, process outcomes, Journey action lineage, and model/tool identity are
retained in each lane's ExecutionRecord, provenance, verdict, and Journey receipts.
Canonical runner time totals 1,382.652 seconds.

## Artifact inventory

The eight canonical lanes contain 56 screenshots, 56 layout dumps, 56 logcats,
24 system-event receipts, eight ExecutionRecords, eight provenance records, eight
verdicts, Journey invocation/result/action-lineage evidence, capture manifests,
and exact Run-Spec/source/APK/deployment/device/tool identities. The two aggregate
JSON files replay the canonical `after-event-1` layouts and require completed
ExecutionRecords, three passed locale/rotate/cleanup receipts, matching local and
installed APK hashes, API 35, and the declared AVD profile.

`verification/` contains focused and full pytest JUnit reports plus
`device-cleanup.json`. After the canonical lanes, both emulators were explicitly
restored to natural rotation `0`; both fixture locale postconditions were `en-US`.
Representative
baseline/candidate phone and tablet screenshots were visually inspected: baseline
Arabic start appears on the right and end on the left; candidate labels move into
incorrect LTR order and visibly converge near the center. No subjective screenshot
judgment enters the machine conclusion.

One preregistration error is preserved at
`attempts/baseline-tablet-ar-landscape-rotation1-nonaccountable/`: rotation `1`
made the naturally-landscape tablet portrait. The initial aggregate failed closed
with `orientation_postcondition_mismatch`. The attempt was never rewritten or
counted; the corrected Run Spec uses natural rotation `0` and has its own fresh
attempt identity.

## Known gaps and limits

The exactly one separate Verification Agent returned accountable
`locally_supported` after 15 passed evidence checks. Its prompt, invocation
boundary, schema-valid conclusion, and limitations are retained under
`independent-verification/`.

- Two local emulator profiles on one API/fingerprint are covered; no additional
  API, foldable posture, font scale, night mode, OEM, or physical-device claim.
- Android CLI screen capture cannot select a device, so named-device lanes use the
  ADR-0001 serial-scoped adb screenshot fallback; capture manifests record this.
- APK binaries remain in the isolated host worktree rather than this run directory;
  durable provenance records build path, byte size, local SHA-256, Android CLI
  deployment receipt, installed path/hash, and equality for every lane.
- The fixture emits configuration telemetry and stable IDs solely for this bounded
  compatibility contract. It is not a general layout engine or accessibility audit.
