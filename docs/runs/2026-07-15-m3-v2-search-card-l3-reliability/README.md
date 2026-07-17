# M3 v2 Search-card semantic L3 reliability re-baseline

Date executed: 2026-07-16 (America/New_York)

Issue: `#56` (parent `#48`)

Fixed point: `1330e7d0acb4549f33b66defcc4c8bdb1475bb38`

Manifest: `bench/goldset/m3-reliability-slice-v2.yaml`

Device: `aiverify_api35`, `emulator-5554`, Android 15 / API 35

The run-record directory retains the `2026-07-15` identity fixed by the
committed schema-v2 manifest. The six live lanes were executed on July 16.

## Result

All six fresh Search-card lanes completed on their first attempt and were
accountable. All three baseline controls passed L3 without a defect-class
hypothesis. All three injected defects failed L3 with `ui_rendering`. L1 and
L2 were inconclusive for both roles, as required for this eventless semantic
seed.

| Metric | Result |
|---|---:|
| Fresh Search-card lanes executed | 6/6 |
| Formal attempts | 6 |
| First-attempt accountable | 6/6 |
| Eventual accountable | 6/6 |
| Retries | 0 |
| Baseline controls passed at L3 | 3/3 |
| Defects caught at L3 / `ui_rendering` | 3/3 |
| Total new formal attempt time | 646.091 s |
| Total new L3 judge time | 165.102 s |
| Operational interventions | 0 |

The evidence-derived full-v2 aggregate in `progress.json` is now 30 planned,
zero pending, 29 first-attempt/eventually accountable, 14 passed controls, 15
caught defects, one historical retry, two historical `preflight_environment`
failures, 3,640.533 seconds of formal attempt time, 165.102 seconds of L3
judge time, and one historical operational intervention. The planner records
29 `accountable_complete` lanes and the one pre-existing exhausted ANR lane.
This reaches the PRD's raw 29/30 accountability threshold; issue `#57` still
owns the independent final audit and readiness conclusion.

## Lane evidence

| Lane / attempt | Child runner exit | Accountability / result | Total | Judge |
|---|---:|---|---:|---:|
| `v2-search-card-baseline-1/attempt-1` | 0 | accountable; L3 pass | 95.045 s | 20.692 s |
| `v2-search-card-baseline-2/attempt-1` | 0 | accountable; L3 pass | 88.211 s | 20.893 s |
| `v2-search-card-baseline-3/attempt-1` | 0 | accountable; L3 pass | 135.937 s | 36.109 s |
| `v2-search-card-defect-1/attempt-1` | 1 | accountable; L3 fail / `ui_rendering` | 103.769 s | 22.873 s |
| `v2-search-card-defect-2/attempt-1` | 1 | accountable; L3 fail / `ui_rendering` | 96.189 s | 29.580 s |
| `v2-search-card-defect-3/attempt-1` | 1 | accountable; L3 fail / `ui_rendering` | 126.940 s | 34.955 s |

Every formal attempt retained a passing runner-enforced five-check live gate,
one exact `action-1` requested-action lineage with `PASSED`, one eventless
checkpoint, a structured final layout, screenshots, annotated screenshots,
logcat, command traces, judge prompt/output/events, verdict, and an attempt-level
checksum manifest. No accountable outcome was retried.

## Matched semantic contract

Baseline and defect lanes used the same Wikipedia commit, Run Spec, product
specification, package, launch activity, requested Journey action, preference
seed, light-mode starting state, and checkpoint boundary. The only intentional
difference was the committed defect patch in `HistoryFragment.kt`.

The single Journey action was preserved exactly from the Run Spec:

> `org.wikipedia.dev is already launched by the runner or by setup; do not use
> launcher search or intents. If onboarding appears, tap Forward until Skip is
> available, then tap Skip. From the main feed, tap the bottom Search tab
> (nav_tab_search) and stop there. Confirm the Search tab is selected and
> search_card is visible; do not tap search_card or enter SearchActivity.`

The strict backend result contains only `action_id`, `status`, `commands`, and
`comment`; it does not echo a free-form `action`. The runner's normalized
result deterministically restores the exact requested action, and the retained
schema-v1 lineage maps `action-1` to that text and `PASSED`. This directly
exercises the stable-ID remediation at the old third-defect exhaustion point.

Each accountable final checkpoint records:

- `checkpoints=["after-segment-0"]` and `injected_events=[]`.
- `nav_tab_search` selected and `search_card` present.
- `search_text_view` and `search_icon` present; `search_src_text` absent, proving
  the Journey did not enter SearchActivity.
- Baseline target text/content description `Search Wikipedia`; L3 `pass`, class
  null, and no failed oracle.
- Defect target text/content description
  `Track what you've been reading here.`; L3 `fail`, class `ui_rendering`, and
  `failed_oracles=["L3"]`.

The separate History empty-state area legitimately contains history language
on both roles. Judgment is scoped to `search_text_view` / `search_icon` under
the preserved Search card rather than treating unrelated page copy as the
defect.

## L3 judge lineage and leakage boundary

Each attempt has exactly one contiguous judge call triplet:

- `l3-judge-call-1.prompt.md`
- `l3-judge-call-1.md`
- `l3-judge-call-1.events.jsonl`

Every prompt contains the matched `l3_spec`, normalized Journey trace, complete
final layout, and final screenshot reference. It does not contain the Run
Spec's `expected_behavior`, patch body, or that call's frozen output. Every
output and event stream is non-empty, and each final parsed output exactly
matches the persisted `verdict.json` L3 object. Each verdict records one
positive `l3-judge` / `oracle` timing phase.

The normalized trace retains the immutable Journey provenance identifier
`wikipedia-ui-rendering-02-search-card-copy-mismatch-segment-0` for both roles.
That shared identifier does not reveal the role, injected string, patch,
expected outcome, or frozen answer. Its `copy-mismatch` taxonomy slug points to
the same Search-card-copy subject already stated by the correct-behavior
`l3_spec`; it is not the product spec's matched-pair defect description. The
actual wrong copy enters a defect prompt only through the final observed layout.

This is text-layout semantic L3 evidence. Screenshots are retained as secondary
checkpoint evidence and prompt references; this record does not claim a
multimodal or visual-only judge.

## Historical and fixed-evidence isolation

No M2, schema-v1, or fixed-evidence repeatability result was copied into a v2
lane or counted in `progress.json`:

- `docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/`
  is the M2 matched-pair record only.
- Its `discarded-searchactivity-empty-state-attempt/` remains invalid historical
  evidence and was not reused.
- `docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/` is the historical
  5/5 + 5/5 fixed-evidence repeatability calibration. Its ten judge-only calls
  remain outside the live denominator.
- `docs/runs/2026-07-13-m3-search-card-l3-reliability/` is the immutable
  schema-v1 comparison package. Its third defect exhausted two attempts because
  the old backend paraphrased the action; neither old attempt was copied,
  linked, or counted here.

This run contains exactly six fresh v2 lane identities and exactly one fresh
attempt under each identity.

## Exact build and deployment commands

The Wikipedia host was clean at
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`. The target baseline source SHA-256
was `127aece4c11055cbed05ccc7c966def1bdf49e2ff610062aa433532715cd4b85`,
and the Search-card patch passed a forward apply check. The existing Gradle APK
was the prior swallowed-Back defect, so it was not copied or deployed before a
successful fresh baseline build.

Fresh baseline build, from `/Users/peter/hosts/wikipedia`:

```bash
shasum -a 256 app/src/main/java/org/wikipedia/history/HistoryFragment.kt
git apply --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
mkdir -p aiverify-builds/m3-v2-search-card-l3
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-baseline-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-baseline-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-baseline-dev-debug.apk
```

Result: `BUILD SUCCESSFUL in 7s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 8.02 s; 121,628,105 bytes; SHA-256
`8084dee23f7b06099b2cbfa4dc38e5ca6623a26f4519a3c222368fb2fc997dea`.

Baseline deployment:

```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-search-card-l3/wikipedia-baseline-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Android CLI reported successful installation and activation.

Defect injection and build:

```bash
git apply --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
git apply \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
shasum -a 256 app/src/main/java/org/wikipedia/history/HistoryFragment.kt
git apply -R --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-defect-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-defect-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-search-card-l3/wikipedia-defect-dev-debug.apk
```

Result: patched source SHA-256
`1a0594d748220fe70ce4475dbaf9720dca7982da844ef33c299bafaa6195d74b`;
`BUILD SUCCESSFUL in 7s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 8.00 s; 121,628,105 bytes; SHA-256
`a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc`.

Defect deployment used the same `android run` command with
`wikipedia-defect-dev-debug.apk`; installation and activation succeeded.

## Exact per-attempt setup

Before every formal attempt, the device was reset to the same light-mode app
state. The committed six-key XML has SHA-256
`38bf4495419940a7887a0178597fe67ad2bba6449654643b501025803c208b18`.

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  <run-root>/setup-probes/issue56-prefs.xml \
  /data/local/tmp/issue56-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue56-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue56-prefs.xml \
  shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -W \
  -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty \
  -o=<run-root>/setup-probes/<lane>-ready-layout.json
```

All six ready layouts contained 23 nodes and the `nav_tab_search` target. The
first baseline and first defect also passed the independent generic-plus-app
eight-check gate. These setup probes are outside oracle accounting; each formal
attempt separately persisted the public runner's mandatory five-check gate.

## Exact public runner commands

An absolute `PYTHONPATH` was used because the child runner changes its working
directory to the Wikipedia host. The declarative Run Spec retains its pinned
comparison path; explicit `--workdir /Users/peter/hosts/wikipedia` selects the
actual clean host without editing the Run Spec.

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-baseline-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-baseline-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-baseline-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-defect-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-defect-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-search-card-defect-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
```

All six outer orchestration commands returned zero after persisting evidence.
The retained child exits were 0 for the three controls and 1 for the three
caught defects.

Aggregate generation:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output <run-root>/plan-after-search-card.json
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output <run-root>/progress.json
```

## Restoration

After the final defect lane, the patch was reversed, the exact baseline source
hash and clean Git state were reverified, and the saved baseline APK was
reinstalled:

```bash
git apply -R --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
git apply -R \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
shasum -a 256 app/src/main/java/org/wikipedia/history/HistoryFragment.kt
git diff --exit-code -- app/src/main/java/org/wikipedia/history/HistoryFragment.kt
git status --short --branch
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-search-card-l3/wikipedia-baseline-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
adb -s emulator-5554 shell pm path org.wikipedia.dev
adb -s emulator-5554 shell sha256sum <installed-base.apk>
```

The restored source SHA-256 was
`127aece4c11055cbed05ccc7c966def1bdf49e2ff610062aa433532715cd4b85`;
the Wikipedia worktree was clean on `main`. The installed device-side base APK
SHA-256 was
`8084dee23f7b06099b2cbfa4dc38e5ca6623a26f4519a3c222368fb2fc997dea`,
matching the saved baseline. A final light-mode reset, 23-node layout, and
eight-check restoration gate passed with `nav_tab_search` / `Search` present.
The Gradle output directory remains the fresh defect build; the explicitly
saved and reinstalled baseline APK is the authoritative restored binary.

## Build outputs and tools

- Installed package: `org.wikipedia.dev`, versionCode `50594`, versionName
  `50594-dev-2026-07-13`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; emulator `36.6.11.0`; Codex CLI `0.144.1`.
- Python `3.11.15`; pytest `9.0.3`; OpenJDK `17.0.19+0`; Gradle `9.5.1`;
  Git `2.50.1 (Apple Git-155)`.
- Neither the runner command nor its L3 child supplied `--model` /
  `--l3-model`. Both Journey driver and L3 judge therefore resolved the base
  Codex CLI default `gpt-5.6-sol` from `/Users/peter/.codex/config.toml`. That
  file was last modified at `2026-07-16T11:53:12-04:00`, before all six lanes,
  and had SHA-256
  `5e099bd752b8b4e17f5ed929d15f88fbee749e71fbebe9f8863802145c367640`.
  Codex CLI 0.144.1 event JSON does not repeat the resolved model, so this
  identity is configuration-derived; `environment.json` preserves the method
  and absence of explicit overrides.
- The two 121,628,105-byte APKs remain outside the repository under
  `/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-search-card-l3/` because
  they total about 243 MB. `environment.json` records absolute paths and exact
  SHA-256 values.

## Artifact inventory

- 6 fresh lane directories and 6 attempt-level checksum manifests.
- 6 attempt records, passing formal live gates, verdicts, and stdout/stderr
  pairs.
- 6 raw Journey results, normalized results, Codex event streams, and stable-ID
  action-lineage records.
- 6 checkpoint capture sets, each with layout, logcat, commands, capture
  manifest, screenshot, and annotated screenshot.
- 6 judge prompt/output/event triplets.
- Under `lanes/`: 114 files total — 54 JSON, 12 JSONL, 12 PNG, 30 text/log/
  Markdown, and 6 checksum manifests. Every attempt has 19 files.
- Under `setup-probes/`: 11 files — six ready layouts, two independent gates,
  one preference XML, and the final restoration layout/gate.
- `plan-after-search-card.json`, `progress.json`, `environment.json`, this
  README, and the root checksum inventory.

## Operational interventions and known gaps

- There were no #56 retries or operational interventions. All attempts
  completed inside runner timeouts and were not interrupted.
- One preliminary read-only `android devices --json` diagnostic returned exit
  2 because Android CLI 1.0.15498356 does not expose that subcommand. The adb
  device/boot checks, independent gates, and all formal gates passed; this probe
  was outside every lane and denominator.
- This seed used `aiverify_api35` Android 15 / API 35, matching the query and
  swallowed-Back v2 slices. The committed v2 ANR and oversized-state slices
  used Android 16 / API 36 elsewhere. Final issue `#57` must preserve that
  mixed-device identity.
- No physical-device, cross-host, second-AVD, ColorOS, fully unattended,
  visual-only, or multimodal validation was performed.
- Layout/resource-ID evidence was primary. Runner screenshots were retained
  byte-for-byte as secondary evidence and were not manually recaptured.
- The six device-originated `logcat.txt` files are retained byte-for-byte. A
  full staged `git diff --cached --check` reports 455 trailing-whitespace
  findings in those immutable raw logs. The scoped check over the other 125
  authored/structured evidence files passes; raw captures were not normalized
  after checksum generation.
- Fixed-evidence repeatability remains historical calibration only and is not
  presented as live execution evidence.
- A two-axis review flagged the shared Journey identifier's `copy-mismatch`
  slug as a possible semantic hint. It was retained because it is required
  provenance shared by baseline and defect and adds no defect value, role, or
  expected verdict beyond the correct-behavior spec. The prohibited full defect
  description, patch, `expected_behavior`, and frozen answers remain absent.
- This issue records the complete Search-card population and evidence-derived
  aggregate, but does not replace the independent final audit/readiness decision
  assigned to `#57`.

## Verification

Before evidence generation, the new committed-evidence regression test was run
alone:

```bash
.venv/bin/pytest \
  tests/bench/test_m3_reliability.py::test_committed_v2_search_card_progress_has_fresh_auditable_l3_attempts \
  -q
```

It failed as expected with one failure on the missing `progress.json`; this was
the TDD red state before any #56 evidence existed. After execution and root
checksum generation, the same command passed (`1 passed`).

Artifact format and checksum validation:

```bash
find <run-root> -type f -name '*.json' -print0 | xargs -0 -n1 jq empty
find <run-root> -type f -name '*.jsonl' -print0 | xargs -0 -n1 jq -e .
xmllint --noout <run-root>/setup-probes/issue56-prefs.xml
find <run-root> -type f -name '*.png' -print0 | \
  xargs -0 -n1 sips -g pixelWidth -g pixelHeight
for attempt in <run-root>/lanes/*/attempt-*; do
  PYTHONPATH=src .venv/bin/python \
    -m aiverify.bench.run_record_checksums "$attempt" --verify
done
PYTHONPATH=src .venv/bin/python \
  -m aiverify.bench.run_record_checksums <run-root> --verify
```

Result: 67 JSON files, 12 JSONL files, one XML file, 12 PNG files, all
six attempt inventories, and the complete root inventory validated; exit 0.

Full repository test suite:

```bash
/usr/bin/time -p .venv/bin/pytest
```

After replacing a checkout-specific absolute-path existence assertion with
current-checkout relative checkpoint validation, the final code/evidence result
was `418 passed in 8.42s`; real 8.60 s; exit 0. Earlier complete runs in the
same verification cycle passed all 418 tests in 7.69 s and 7.71 s.

The committed-evidence test independently re-parses every final judge output,
matches it to `verdict.json`, verifies exact requested-action lineage, checks
role-specific final layout text and L3 outcomes, rejects prompt leakage, derives
the full-v2 aggregate, verifies every checksum, and checks that each checksum
inventory lists every file exactly once.
