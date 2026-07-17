# M3 v2 Final Audited Comparison

Date: 2026-07-16 (America/New_York)

Issue: `#57` under remediation PRD `#48`

Pre-remediation review fixed point:
`05a018238b55784e44c5d9e993425befebd48332`

Audit generation base revision:
`471b44c27de9c43777bd552d78933050c1cc20f5`

## Decision

The fresh v2 slice **passes** all three unchanged M3 criteria for this bounded
population:

- 29/30 lanes are eventually accountable, exactly meeting the required
  `>=29/30` threshold.
- All 14 accountable baseline controls pass, with zero false positives. The
  exhausted ANR baseline lane is not counted as either a pass or false positive.
- All 15 accountable defect lanes are caught at the expected oracle level and
  expected defect class.

This is not a perfect-reliability claim. `v2-anr-baseline-3` exhausted both
allowed attempts after two independent live-validation preflight failures and
remains an execution-reliability failure. The v2 result has no accountability
margin above the threshold.

The original audited slice remains unchanged and **failed** at 27/30. The
generated comparison keeps the original 30 lanes and the fresh v2 30 lanes as
two independent populations. It does not publish a 56/60 aggregate and does not
replace any historical lane selectively.

## Generated artifacts

- [`environment.json`](environment.json) is the audit configuration and immutable
  comparison anchor. It separates audit-host metadata from each child package's
  checksummed lane-execution environment.
- [`summary.json`](summary.json) is the full structured audit model. It includes
  all 30 final lane results, all 31 bounded attempt lineages, criteria, oracle
  breakdowns, package identities, identity-coverage gaps, and the independent
  historical comparison.
- [`report.md`](report.md) is generated from exactly the same in-memory model as
  `summary.json`.
- `checksums.sha256` is generated after this record and the reviews are final. It
  covers every file in this directory except itself.

Implementation and regression coverage live in:

- `src/aiverify/bench/m3_audit.py`
- `tests/bench/test_m3_rebaseline_audit.py`
- the existing backward-compatibility tests in
  `tests/bench/test_m3_reliability.py`

The historical record at
`docs/runs/2026-07-13-m3-final-reliability-baseline/` was not edited.

## Evidence-derived aggregate

| Metric | Original | Fresh v2 |
|---|---:|---:|
| Decision | FAILED | PASSED |
| Planned lanes | 30 | 30 |
| Formal attempts | 36 | 31 |
| First-attempt accountable | 24/30 | 29/30 |
| Eventual accountable | 27/30 | 29/30 |
| Non-accountable lanes | 3 | 1 |
| Bounded retries | 6 | 1 |
| Accountable controls passed | 15/15 | 14/14 |
| Accountable baseline false positives | 0 | 0 |
| Accountable defects caught at expected level/class | 12/12 | 15/15 |
| Operational interventions | 9 | 1 |
| Total attempt time | 4605.338 s | 3640.533 s |
| Accountable L3 judge time | 97.269 s | 165.102 s |
| Runner gates | 34 passed / 2 failed | 29 passed / 2 failed |

The timing and intervention differences are descriptive only. The v2 packages
span two retained host/device environments, so this record does not attribute
timing changes causally to the remediation.

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 11 | 5 | 6 | 1 |
| L2 | 12 | 12 | 6 | 6 | 0 |
| L3 | 6 | 6 | 3 | 3 | 0 |

The v2 `preflight_environment=2` failure-class count is attempt-level: both
failures belong to the one exhausted ANR baseline lane.

## Package integrity and identities

All five fresh root checksum inventories and all 31 attempt checksum inventories
verified. The five root inventories cover 655 files in total.

| Package | Entries | Root checksum-manifest SHA-256 | Environment SHA-256 |
|---|---:|---|---|
| `2026-07-15-m3-v2-anr-reliability` | 96 | `9c54038840ee0ea06faaf52c243c3253fac8f62d6d468d5898acccd4a21e9a0b` | `ff58e71ea9eaade19a8064fda68298f33b1d5f68487be8ce5ca00621e19c704d` |
| `2026-07-15-m3-v2-oversized-saved-state-reliability` | 136 | `3f8f5426ab34172120af2b4ff931e9c823a818e2b64f36b52d0784f0f49d7731` | `7e41b3679384d77695b84ef4d9d9d235f702f7097b4221e7f1d5466a77cf5309` |
| `2026-07-15-m3-v2-query-duplication-reliability` | 147 | `b432b287b4d59f03bed465815baf5b764525bb76db5324f3e5a31981670e3c95` | `215dc3e57ecb5ea5f4b87fec636c32f5e150946d55cd7f79b2811022aedf9525` |
| `2026-07-15-m3-v2-search-card-l3-reliability` | 129 | `43a6545ef0dde8889c707e16cd0dd38846a0a1addc8ed9167eca14d95c13b252` | `b8315ee4565fdfbd2e4b8bf766af4715d3c3965e64d610dfc1e15fd95b98d4e8` |
| `2026-07-15-m3-v2-swallowed-back-reliability` | 147 | `1f86d42fee4a24ab02977eaebbda3c10f5a465cf0ef1efd16c053014be08ce69` | `299f57b4f360392c826c89f030d58f364c7a7f34bd22e099c1e5d9ddb418f9af` |

All five packages identify application `org.wikipedia.dev`, versionCode `50594`.
The three Peter-host packages additionally retain versionName
`50594-dev-2026-07-13`; the first two packages do not retain versionName.

The 655 root-inventoried artifacts break down as follows:

| Artifact class | Count | Contents |
|---|---:|---|
| JSON | 366 | environments, attempts, gates, verdicts, layouts, capture manifests, normalized Journey results, plans/progress, and setup probes |
| JSONL | 35 | Codex Journey and L3 event streams |
| PNG | 94 | raw and annotated screenshots |
| TXT/log | 109 | logcat, runner stdout/stderr, and retained command output |
| Markdown | 17 | child records plus Journey/L3 prompts and outputs |
| XML | 3 | retained application preference snapshots |
| Attempt checksum manifests | 31 | one complete inventory per bounded attempt |

Per-package detailed inventories:

- [ANR artifact inventory](../2026-07-15-m3-v2-anr-reliability/README.md#artifact-inventory)
- [Oversized-state artifact inventory](../2026-07-15-m3-v2-oversized-saved-state-reliability/README.md#artifact-inventory)
- [Query-duplication artifact inventory](../2026-07-15-m3-v2-query-duplication-reliability/README.md#artifact-inventory)
- [Search-card L3 artifact inventory](../2026-07-15-m3-v2-search-card-l3-reliability/README.md#artifact-inventory)
- [Swallowed-Back artifact inventory](../2026-07-15-m3-v2-swallowed-back-reliability/README.md#artifact-inventory)

The audit loads each package environment only after its root inventory verifies,
then cross-checks every attempt's runner executable/workspace, Wikipedia
workdir, Run Spec command path, artifact path, device flag, and gate device. It
also cross-checks retained Run Spec and v2 manifest hashes where the package
captured them.

### Mixed execution environments

- ANR and oversized-state: `/Users/80268204`, AVD `medium_phone`, Android
  16/API 36, emulator `36.5.11.0`, Python `3.12.13`, pytest `9.1.1`, Temurin
  17.0.19, and Gradle `9.5.1`. The ANR package does not retain Codex CLI
  version; oversized-state retains `0.144.1`.
- Query duplication, swallowed Back, and Search-card L3: `/Users/peter`, AVD
  `aiverify_api35`, Android 15/API 35, emulator `36.6.11.0`, Python `3.11.15`,
  pytest `9.0.3`, OpenJDK 17.0.19, Gradle `9.5.1`, Codex CLI `0.144.1`, and
  Wikipedia commit `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`.

Both environments used serial `emulator-5554`; the audit therefore never treats
serial equality as proof of a homogeneous AVD, API level, host, or toolchain.
Android CLI `1.0.15498356` and adb/platform-tools
`1.0.41 / 37.0.0-14910828` are retained in all five packages.

### Identity coverage and gaps

| Identity | Coverage |
|---|---:|
| Package environment | 5/5 packages |
| Device serial, host path, and Run Spec command cross-check | 31/31 attempts |
| Contemporaneous Run Spec SHA-256 | 3/5 packages |
| Contemporaneous v2 manifest SHA-256 | 3/5 packages |
| Wikipedia git commit | 3/5 packages |
| Codex CLI version | 4/5 packages |
| Effective model identity | 1/5 packages |
| Retained model override cross-check | 6/6 attempts in that package |

Only the Search-card package explicitly retains effective Journey-driver and L3
judge model `gpt-5.6-sol`, resolved from its checksummed pre-run configuration
snapshot with no command override. The other four package environments retain no
model field. This final record reports those values as unavailable and does not
backfill them from the current Codex configuration. In particular, the ANR and
oversized-state model cannot be recovered from their retained event streams.

The first two packages also omit a Wikipedia git commit and contemporaneous Run
Spec/manifest hashes. Their environment files retain source/APK hashes and the
complete 31-attempt inventory resolves the expected Run Spec paths. The current
repository Run Spec hashes are included in `summary.json` with status
`not_retained`, not presented as contemporaneous captures.

## External APK inventory

The six Peter-host APK files remain present and independently matched their
recorded byte sizes and SHA-256 values during this audit:

| Package/role | Bytes | SHA-256 |
|---|---:|---|
| Query baseline | 121282950 | `7af65b50f282a2204595cb6e7a78a61a7c3370a06da2ee1306eb696982a1c957` |
| Query defect | 121628323 | `f0a3a81272c6da61d5302024db47756c1de5f67b450cca7b3cb7f6a172be46de` |
| Swallowed Back baseline | 121628105 | `c0a3bfb315d758385918d273f5b5a36802ad59ec8e3b24c5492d8db97f7f06b0` |
| Swallowed Back defect | 121628216 | `bd3700b4fb92b832b0912a3b7f57a4e395985f80b9d53e33bdf960fc1670d1a0` |
| Search-card baseline | 121628105 | `8084dee23f7b06099b2cbfa4dc38e5ca6623a26f4519a3c222368fb2fc997dea` |
| Search-card defect | 121628105 | `a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc` |

The four APK paths under `/Users/80268204` are not available on this audit host,
so this turn could only verify their checksummed retained metadata:

| Package/role | Bytes | Retained SHA-256 |
|---|---:|---|
| ANR baseline | 121199720 | `dcd9ac00c6ce9af57ed58e997c8c0b1492c59c6964510f58ebf39d55cfca4cf7` |
| ANR defect | 121545135 | `a20ce876573563bef3adbca89948426e09be5a4ecf5a310bbaf705d97f37bc2b` |
| Oversized-state baseline | 121205472 | `b89edc28d16955bd9d9980090e217127863c2691eb4549c2151d2fb6f5632029` |
| Oversized-state defect | 121550865 | `c7270130e27a6109c28d12160e52bb353ecff27da7d317691c5f1b4494b3e119` |

## Historical baseline integrity

The audit fails closed unless the historical final root verifies, its generated
JSON/Markdown exactly re-derive from the original evidence, its five evidence
package checksum anchors match, and these immutable artifact hashes match:

| Historical artifact | SHA-256 |
|---|---|
| `bench/goldset/m3-reliability-slice.yaml` | `8017320a27a5a8e0a01fff1357abf09edf0164abf59e764dc843b5335c0271b3` |
| `README.md` | `6e585904695625d8def7aab3d7d2068c8ea009ac2169f956addc727ba385b8b7` |
| `checksums.sha256` | `a07238f51b65e5dc6e65ee69dfa6f4876609227e99e85f846a1371212d593e1f` |
| `environment.json` | `1d5bd589118dfc069e22256a40f4f997858ca117085e1225b89def7de3a43055` |
| `report.md` | `43eb0fe11f91865e7b699763829e4ad36bfdd4cd6034cb5d913a5dcc3fc61e20` |
| `summary.json` | `e738af441b760e146412c5fd1afb921ccda528b93bdd787416a4d92702a42b58` |

`git diff --exit-code 05a0182 -- ...` also returned exit 0 for the original
manifest, five original evidence packages, and original final record.

## Exact commands and important results

Capture the audit-host tool identity:

```bash
sw_vers
uname -m
codex --version
android --version
adb version
java -version
.venv/bin/python --version
.venv/bin/pytest --version
git --version
# macOS 26.3 (25D125), arm64; Codex CLI 0.144.1;
# Android CLI 1.0.15498356; adb 1.0.41 / platform-tools 37.0.0-14910828;
# OpenJDK 17.0.19; Python 3.11.15; pytest 9.0.3;
# git 2.50.1 (Apple Git-155)
```

Resolve the complete v2 inventory and derive the strict aggregate:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  plan --json-output /tmp/m3-v2-final-plan.json
jq '{count:length,statuses:group_by(.status)|map({status:.[0].status,count:length}),unique_lanes:(map(.lane_id)|unique|length)}' \
  /tmp/m3-v2-final-plan.json
# 30 unique lanes; 29 accountable_complete; 1 non_accountable_exhausted

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml \
  summary --json-output /tmp/m3-v2-final-summary.json
# exit 0; 29 first/eventual; 1 retry; 14 controls; 15 catches;
# preflight_environment=2; 3640.533 s; judge=165.102 s; interventions=1
```

Generate JSON and Markdown from one model:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml audit \
  --environment docs/runs/2026-07-16-m3-v2-final-audited-comparison/environment.json \
  --json-output docs/runs/2026-07-16-m3-v2-final-audited-comparison/summary.json \
  --markdown-output docs/runs/2026-07-16-m3-v2-final-audited-comparison/report.md
# exit 0; original FAILED 27/30; distinct v2 PASSED 29/30
```

Verify all fresh package and attempt inventories:

```bash
for record in docs/runs/2026-07-15-m3-v2-*-reliability; do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    --verify "$record" || exit
done
# five checksum inventory verified results; 96 + 136 + 147 + 129 + 147 = 655 entries

find docs/runs/2026-07-15-m3-v2-*-reliability/lanes \
  -mindepth 2 -maxdepth 2 -type d -name 'attempt-*' -print0 | \
while IFS= read -r -d '' attempt; do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    --verify "$attempt" >/dev/null || exit 1
done
count=$(find docs/runs/2026-07-15-m3-v2-*-reliability/lanes \
  -mindepth 2 -maxdepth 2 -type d -name 'attempt-*' | wc -l | tr -d ' ')
echo "verified_attempt_inventories=$count"
# verified_attempt_inventories=31
```

Re-hash the six locally available external APKs against each package
environment:

```bash
for f in docs/runs/2026-07-15-m3-v2-{query-duplication,swallowed-back,search-card-l3}-reliability/environment.json; do
  jq -r '.application | [.baseline_apk.path, (.baseline_apk.bytes|tostring), .baseline_apk.sha256], [.defect_apk.path, (.defect_apk.bytes|tostring), .defect_apk.sha256] | @tsv' "$f"
done | while IFS=$'\t' read -r apk_path expected_bytes expected_sha; do
  actual_bytes=$(/usr/bin/stat -f %z "$apk_path")
  actual_sha=$(/usr/bin/shasum -a 256 "$apk_path" | /usr/bin/awk '{print $1}')
  [[ "$actual_bytes" == "$expected_bytes" && "$actual_sha" == "$expected_sha" ]] || exit 1
  printf 'verified\t%s\t%s\t%s\n' "$actual_bytes" "$actual_sha" "$apk_path"
done
# six verified results; exact byte sizes and hashes are inventoried above

git -C /Users/peter/hosts/wikipedia rev-parse HEAD
git -C /Users/peter/hosts/wikipedia status --porcelain
# 6ccb8d85a21a8e34b96e4813d3caee5c690ece9b; no status output (clean)
```

Verify the immutable historical comparison:

```bash
for record in \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability \
  docs/runs/2026-07-13-m3-query-duplication-reliability \
  docs/runs/2026-07-13-m3-swallowed-back-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability \
  docs/runs/2026-07-13-m3-final-reliability-baseline
do
  PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
    --verify "$record" || exit
done
# six checksum inventory verified results

git diff --exit-code 05a0182 -- \
  bench/goldset/m3-reliability-slice.yaml \
  docs/runs/2026-07-13-m3-anr-reliability \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability \
  docs/runs/2026-07-13-m3-query-duplication-reliability \
  docs/runs/2026-07-13-m3-swallowed-back-reliability \
  docs/runs/2026-07-13-m3-search-card-l3-reliability \
  docs/runs/2026-07-13-m3-final-reliability-baseline
# exit 0; no differences
```

Focused regression and generated-document checks:

```bash
/usr/bin/time -p .venv/bin/pytest -o addopts="" -q \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_m3_rebaseline_audit.py \
  tests/bench/test_run_record_checksums.py
# 84 passed in 7.58 s; real 7.72 s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -o addopts="" -q
# 429 passed in 12.82 s; real 12.94 s

.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
# 429
```

Generate and verify the final record only after this README and both reviews are
complete:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-16-m3-v2-final-audited-comparison
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-16-m3-v2-final-audited-comparison
wc -l docs/runs/2026-07-16-m3-v2-final-audited-comparison/checksums.sha256
# checksum inventory verified; 4 covered files
```

## Manual and device verification

Issue #57 performed an evidence audit and publication; it did not build, deploy,
launch, manipulate, or rerun a product lane. The live emulator work, Android CLI
navigation, system events, UI layouts, screenshots, logcat, Journey event
streams, L3 prompts/outputs, APK transitions, and restoration checks were done in
issues `#52` through `#56` and remain in those five checksummed child records.

This turn re-read every committed attempt, verified all package and attempt
inventories, cross-checked the still-present six Peter-host APKs, and confirmed
the Peter Wikipedia checkout remained clean at
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`. It did not claim access to the
other host's four APK files.

The one v2 operational intervention is retained on ANR baseline attempt 2: the
operator terminated a stalled Android CLI deployment and used a direct headless
cold boot plus adb reinstall to restore an independently passing layout gate
before retry. The retry still failed a later preflight condition and remained
non-accountable. No other v2 attempt records an intervention.

## Two-axis review

Standards and Spec reviews ran independently and in parallel against
pre-remediation fixed point
`05a018238b55784e44c5d9e993425befebd48332`.

Standards final verdict: **No findings**. Findings resolved during review:

- rounded descriptive timing deltas to retained evidence precision;
- cross-checked `--model`/`--l3-model` against the retained explicit-override
  state for all six model-identified attempts;
- made result, margin, comparison, and identity prose model-derived;
- made checksum verification reject duplicate and unlisted artifacts; and
- added exact tool, APK, host, and artifact-inventory evidence to this record.

Spec final verdict: **No blocking findings**. Findings resolved during review:

- independent accountability, false-positive, and defect-consistency failure
  combinations now render coherent top-level and side-by-side decisions;
- the original and v2 summaries remain separate and immutable;
- all package inventories now enforce completeness, not merely listed-file hash
  validity; and
- mixed environment/model gaps remain explicit rather than inferred.

The final evidence-record audit found no additional substantive gaps after the
artifact counts, package identifiers, exact attempt count, and child inventory
links were added. Reviewer verification included the 84-test focused suite,
compile check, historical immutability check, and clean `git diff --check`.

## Known gaps and claim boundary

- The v2 accountability criterion passes at 29/30 with zero margin. One baseline
  lane remains exhausted and non-accountable.
- Model identity is explicitly retained for only one of five packages; missing
  model fields are not inferred or backfilled.
- Codex CLI version is absent from the ANR environment. Run Spec/manifest hashes
  and Wikipedia commits are absent from the first two package environments.
- The four other-host APKs are not available on this audit machine; only their
  checksummed metadata was verified here.
- The mixed API 35/API 36 environments prevent homogeneous-device or causal
  performance claims.
- This result is limited to the Wikipedia Android application, Codex CLI
  Verification Agent Backend, Android CLI, the declared package environments,
  and the versioned five-seed/30-lane v2 slice.
- It is not a benchmark-wide detection or false-positive rate, a fully
  unattended Journey measurement, a physical-device or ColorOS result, a
  cross-application result, or a visual-only/multimodal claim.
