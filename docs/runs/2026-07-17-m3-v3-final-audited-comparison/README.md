# M3 V3 Final Immutable Failed Audit

Date: 2026-07-17 (America/New_York)

Issue: `#62` under remediation PRD `#58`

## Decision

The fresh immutable v3 population **FAILED** and does not unblock M4:

- 6/30 lanes were eventually accountable; v3 required 30/30.
- The 3 accountable baseline controls passed with zero false positives, but the
  required denominator was 15/15.
- The 3 accountable ANR defects were caught at L1 as `crash_stability`, but the
  required defect denominator was 15/15.
- Only the 6 accountable ANR attempts produced complete checksummed execution
  provenance; the audit requires provenance for all 54 formal attempts.

The remaining 24 lanes exhausted both bounded attempts before live validation,
producing 48 terminal
`execution_identity_error`: four frozen Run Specs declare the unavailable
`/Users/80268204/hosts/wikipedia` path, while the preregistered effective worktree
is `/Users/peter/hosts/wikipedia`. The new execution-identity gate rejected that
contradiction. The failure was not bypassed by modifying frozen Run Specs,
changing the manifest, changing runner semantics, replacing lanes, or merging
historical denominators.

Original M3 (27/30, FAILED), v2 (29/30, PASSED under its unchanged threshold),
and v3 (6/30, FAILED under the strict threshold) remain three separate 30-lane
populations.

## Generated artifacts

- `environment.json`: final audit configuration and v2 comparison anchors.
- `summary.json`: the single structured audit model for all 30 lanes/attempts.
- `report.md`: generated from the same in-memory model as `summary.json`.
- `restored-baseline-layout.json`: final Android CLI layout after restoring the
  baseline APK; 38 nodes.
- `checksums.sha256`: final root inventory (generated last).

The five child packages contain 429 files: 221 JSON, 6 JSONL, 5 Markdown,
6 patches, 12 PNG screenshots, 59 SHA-256 manifests, 114 text/log files, and
6 YAML snapshots. All 54 attempt IDs are unique. The ANR package has 128 covered
entries; each deterministic identity-failure package has 74.

## Child package checksum anchors

| Package | Root checksum-manifest SHA-256 |
|---|---|
| `2026-07-17-m3-v3-anr-reliability` | `34cae38c7d95ca4c52d1a05346da5b6e24b2a62cf6d6cb20f04ed44b28811a3e` |
| `2026-07-17-m3-v3-oversized-saved-state-reliability` | `34c9ee5a57af35276e7425d0dace993c730feb873c047ff19d7068f56e8e7ecd` |
| `2026-07-17-m3-v3-query-duplication-reliability` | `d96309d9cd05e09e3a96807613021f7425eb5ddd5b11ed10bacd1f1046370340` |
| `2026-07-17-m3-v3-search-card-l3-reliability` | `7321233f7016a9176ddb55b6334d82d9d3d154cef540525777cba6706bda0cda` |
| `2026-07-17-m3-v3-swallowed-back-reliability` | `f1737ddb1bade6034c355454820119bc6ed8eaa0f556dc4a25337accd41b97e0` |

## External APK inventory

APKs remain outside the repository because the six files total about 695 MiB.

| Target | Bytes | SHA-256 |
|---|---:|---|
| Baseline | 121628105 | `32ec2d364f5fd3b291fc0486dd809a8412e7f23bfd3b5d99e3fd999c4985a227` |
| ANR defect | 121283210 | `ea5dc10f79c2bd767ac3566eacbc8b5fd489fd3dae7acb68ddd58839b1c7392c` |
| Oversized-state defect | 121283188 | `228a9ff92e98d95197cace295f12e0e085ee98f3590a0484cb1892ed60ab2525` |
| Query-duplication defect | 121283168 | `61450b80bec76ee94638602aa8054facfad84403c5b7e6fd7b660295e761e784` |
| Swallowed-Back defect | 121283061 | `4b37babd6ede7136dfe499b369056f34d793bef65a83a23e08b2cce95b824afd` |
| Search-card L3 defect | 121282915 | `bcafbdb2b07bde007d524c37bffa9fdc3a308e1c78fd993d01b30e283d1ee94d` |

Location: `/Users/peter/hosts/wikipedia/aiverify-builds/m3-v3/`.

Builds used `./gradlew assembleDevDebug --no-daemon` at the frozen Wikipedia
commit. Results were: baseline `BUILD SUCCESSFUL in 8s` (real 8.57s), ANR
defect 37s (real 38.22s), oversized-state defect 21s (real 21.47s),
query-duplication defect 6s (real 7.03s), swallowed-Back defect 6s
(real 6.80s), and Search-card defect 7s (real 8.06s). Each patch passed
`git apply --check`, was applied only for its defect build, and was reversed
before the next target.

## Exact verification commands and results

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.m3_reliability \
  --manifest /Users/peter/projects/ai_verfication/bench/goldset/m3-reliability-slice-v3.yaml \
  run-lane <the exact lane_id listed in report.md> \
  --device emulator-5554 \
  --workdir /Users/peter/hosts/wikipedia \
  --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
# invoked for each of the 30 report.md lane IDs; the 24 identity failures were
# rerun once with the recorded diagnosis/intervention, exhausting max_attempts=2.
# Across 54 formal attempts: 3 control=0, 3 caught defects=1,
# 48 non-accountable=2.

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v3.yaml progress
# 30 planned, 0 pending, 6 first/eventual accountable, 24 retries,
# 3 passed controls, 3 caught defects, execution_identity=48,
# total_seconds=588.695, judge_seconds=0.0, interventions=24

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v3.yaml audit \
  --environment docs/runs/2026-07-17-m3-v3-final-audited-comparison/environment.json \
  --json-output docs/runs/2026-07-17-m3-v3-final-audited-comparison/summary.json \
  --markdown-output docs/runs/2026-07-17-m3-v3-final-audited-comparison/report.md
# exit 0; structured decision m3_overall=failed

for d in docs/runs/2026-07-17-m3-v3-*-reliability; do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    "$d" --verify
done
# five checksum inventories verified

.venv/bin/pytest -q tests/bench/test_m3_v3_audit.py \
  tests/bench/test_m3_rebaseline_audit.py tests/bench/test_m3_reliability.py
# 96 passed in 8.16s

.venv/bin/pytest
# 521 passed in 12.42s (12.65s wall clock)

git diff --exit-code 6aabe4d198eef1f22c701a492f54bde05a0d0ec0 -- \
  bench/goldset/m3-reliability-slice.yaml \
  bench/goldset/m3-reliability-slice-v2.yaml \
  docs/runs/2026-07-13-m3-* docs/runs/2026-07-15-m3-v2-* \
  docs/runs/2026-07-16-m3-v2-final-audited-comparison
# exit 0
```

Historical anchors remained unchanged: original manifest
`8017320a…`, original final checksum manifest `a07238f5…`, v2 manifest
`c4c0cb8f…`, and v2 final checksum manifest `246e798d…`.

## Real-device/emulator/manual verification

- Android CLI `1.0.15498356` installed and activated every baseline/defect APK
  on `emulator-5554` / `aiverify_api35` (Android 15/API 35).
- Six ANR attempts passed the mandatory live-validation gate; 48 identity
  failures correctly stopped before that gate (`not_run`), so they have no
  fabricated Journey or oracle result.
- After execution, Android CLI restored the baseline APK. Device-side base APK
  SHA-256 matched `32ec2d36…`; a cold restart followed by `android layout`
  returned the committed 38-node layout.
- The Wikipedia source worktree was clean at
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b` after all five defect builds.

## Known gaps and follow-up risk

- v3 does not satisfy M3 and must not unblock M4.
- All 24 deterministic identity-failure lanes spent their one permitted retry
  after diagnosis. The only corrective remedies required changing frozen
  inputs/runner semantics or administrator-only creation of the old
  `/Users/80268204` alias, so the unchanged retries failed identically and all
  lanes are terminally exhausted.
- Validation used one emulator, not a physical device, ColorOS device, second
  AVD, or cross-host fleet.
- A post-restoration launcher attempt briefly opened LeakCanary; an explicit
  force-stop/cold start of `org.wikipedia.DefaultIcon` and a three-second settle
  produced the retained 38-node layout. This did not affect any formal lane.
