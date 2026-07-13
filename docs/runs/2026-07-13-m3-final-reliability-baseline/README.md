# M3 Audited Execution-Reliability and False-Positive Baseline

Date: 2026-07-13 (America/New_York)

Issues: `#47` under PRD `#41`

Commit under review: changes after `07f5304`

## Decision

M3 is **not met** for this bounded reliability slice. The evidence-derived result
is 27/30 eventually accountable lanes, below the required minimum of 29/30. The
three exhausted non-accountable lanes remain execution-reliability failures; they
are not reclassified as oracle misses, catches, passed controls, or false
positives.

The other two required criteria pass within the accountable population:

- 15/15 accountable baseline controls passed, with zero false positives.
- 12/12 accountable injected-defect lanes failed at the expected oracle level
  with the expected oracle defect class.

The generated human report is [`report.md`](report.md), and the identical
structured model is [`summary.json`](summary.json). Both contain all 30 lane
resolutions.

## Evidence-derived aggregate

| Metric | Result |
|---|---:|
| Selected seeds | 5 |
| Planned lanes | 30 |
| Formal attempts | 36 |
| First-attempt accountable | 24/30 |
| Eventual accountable | 27/30 |
| Bounded retries | 6 |
| Accountable controls passed | 15/15 |
| Accountable baseline false positives | 0 |
| Accountable defects caught at expected level/class | 12/12 |
| Planned defects caught | 12/15 |
| Total attempt time | 4605.338 s |
| Accountable L3 judge time | 97.269 s |
| Operational interventions | 9 |
| Runner gates | 34 passed / 2 failed |

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 10 | 6 | 4 | 2 |
| L2 | 12 | 12 | 6 | 6 | 0 |
| L3 | 6 | 5 | 3 | 2 | 1 |

Non-accountable attempt failure classes are
`verification_agent_journey=6`, `preflight_environment=2`, and
`evidence_capture=1`.

## Retained evidence packages

The final model verifies every package-level checksum manifest before rendering:

| Package | Covered files | Status |
|---|---:|---|
| `docs/runs/2026-07-13-m3-anr-reliability/` | 103 | verified |
| `docs/runs/2026-07-13-m3-oversized-saved-state-reliability/` | 134 | verified |
| `docs/runs/2026-07-13-m3-query-duplication-reliability/` | 144 | verified |
| `docs/runs/2026-07-13-m3-swallowed-back-reliability/` | 218 | verified |
| `docs/runs/2026-07-13-m3-search-card-l3-reliability/` | 118 | verified |

Together these five packages retain 717 package-level checksummed files. They
contain the 36 attempt lineages, verdicts, runner gates, operational
interventions, screenshots, layouts, logcat, Journey inputs/results/event
streams, L3 judge prompts/outputs/events, and prior run records. Exact APK,
source, patch, Run Spec, and product-spec hashes are retained in the respective
child README files. Large APKs remain outside this repo at the paths and hashes
recorded there.

## Execution identity

The generated report loads [`environment.json`](environment.json), cross-checks
its device serial against every committed attempt gate, and derives gate status
counts from those attempt artifacts.

- Host: Wikipedia Android, clean git checkout at
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`, path
  `/Users/peter/hosts/wikipedia`.
- Device: `emulator-5554`, AVD `aiverify_api35`, Android 15 / API 35,
  `sdk_gphone64_arm64`.
- Package/activity used by the live child runs:
  `org.wikipedia.dev/org.wikipedia.DefaultIcon`.
- Codex CLI `0.144.1`; Android CLI `1.0.15498356`; adb `1.0.41`,
  platform-tools `37.0.0-14910828`; OpenJDK `17.0.19`; Python `3.11.15`;
  pytest `9.0.3`.

## Exact commands and important results

Final environment audit:

```bash
android --version
# 1.0.15498356

adb version
# Android Debug Bridge 1.0.41; Version 37.0.0-14910828

codex --version
# codex-cli 0.144.1

java -version
# openjdk version "17.0.19" 2026-04-21

.venv/bin/python --version
# Python 3.11.15

.venv/bin/pytest --version
# pytest 9.0.3

git -C /Users/peter/hosts/wikipedia rev-parse HEAD
# 6ccb8d85a21a8e34b96e4813d3caee5c690ece9b

git -C /Users/peter/hosts/wikipedia status --porcelain
# no output; clean

adb -s emulator-5554 shell getprop ro.build.version.release
# 15
adb -s emulator-5554 shell getprop ro.build.version.sdk
# 35
adb -s emulator-5554 shell getprop ro.product.model
# sdk_gphone64_arm64
adb -s emulator-5554 emu avd name
# aiverify_api35 / OK
```

Generate both final documents from one model:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability audit \
  --environment docs/runs/2026-07-13-m3-final-reliability-baseline/environment.json \
  --json-output docs/runs/2026-07-13-m3-final-reliability-baseline/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-final-reliability-baseline/report.md
# exit 0; M3 overall failed; eventual accountability 27/30
```

Verify retained evidence and the final record:

```bash
for record in \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability \
  docs/runs/2026-07-13-m3-query-duplication-reliability \
  docs/runs/2026-07-13-m3-swallowed-back-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability
do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    --verify "$record" || exit
done
# five `checksum inventory verified` results

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-final-reliability-baseline
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-final-reliability-baseline
# checksum inventory verified; 4 covered files
```

Host-side fixture and generated-document consistency verification:

```bash
/usr/bin/time -p .venv/bin/pytest -q \
  tests/bench/test_m3_reliability.py \
  tests/test_codex_cli_provider.py \
  tests/bench/test_goldset_ui_rendering_02_search_card_copy_mismatch.py
# 63 passed; real 1.43 s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -q
# 384 passed; real 7.33 s

.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
# 384
```

## Two-axis review

The required Standards and Spec reviews used fixed point `07f5304`. Initial
findings required benchmark-valid wrong-oracle/wrong-class outcomes to remain
visible, report prose to derive from actual criterion states, gate artifacts to
agree with verdict preflight semantics, and final-audit responsibilities to move
out of the lane orchestration module. All findings were covered by regressions
and resolved. Final Standards and Spec re-reviews both returned `No findings`.

## Manual/device verification

Issue #47 did not execute new product lanes or alter the Wikipedia host. It re-read all
retained live attempt evidence, reverified each package checksum, queried the
still-running emulator identity, and confirmed the host checkout remained clean.
The actual UI navigation, system events, builds, deployments, screenshots, and
restoration steps are preserved in the five child run records.

## Known gaps and claim boundary

This result applies only to the Wikipedia host, Codex CLI Verification Agent
Backend, Android CLI, one API 35 emulator, and this selected five-seed, 30-lane
live slice. It is not a benchmark-wide detection or false-positive rate, a fully
unattended Journey measurement, a cross-host or physical-device result, a ColorOS
migration result, or a visual-only/multimodal L3 claim.

The unmet 27/30 accountability criterion is the principal M3 gap. The report does
not hide it behind the zero observed false positives or the consistent outcomes
among accountable defect lanes.
