# M3 Verification Agent Audited Re-Baseline Comparison

Slice: `m3-verification-agent-reliability-v2`

## Decision

| Criterion | Result | Evidence |
|---|---|---|
| M3 overall | **PASSED** | All unchanged criteria passed |
| Eventual accountability | **PASSED** | 29 / 30; required >=29 / 30 |
| Accountable baseline false positives | **PASSED** | 0 observed; required 0 |
| Accountable defect consistency | **PASSED** | 15 / 15 caught at expected level/class |

All unchanged M3 criteria passed for the bounded v2 slice. The 29/30 accountability result meets the threshold exactly, with no margin.

The original and v2 runs remain distinct populations: **30 + 30**, not a combined 60-lane denominator. No historical lane was replaced.
Non-accountable lanes remain execution-reliability failures and are not reclassified as oracle outcomes.

## Immutable Original vs Fresh V2

| Metric | Original (distinct 30) | V2 (distinct 30) |
|---|---:|---:|
| M3 decision | **FAILED** | **PASSED** |
| Formal attempts | 36 | 31 |
| First-attempt accountable | 24 / 30 | 29 / 30 |
| Eventual accountable | 27 / 30 | 29 / 30 |
| Non-accountable lanes | 3 | 1 |
| Retries | 6 | 1 |
| Accountable controls passed | 15 / 15 | 14 / 14 |
| Accountable baseline false positives | 0 | 0 |
| Accountable defects caught | 12 / 12 | 15 / 15 |
| Operational interventions | 9 | 1 |
| Total attempt time (seconds) | 4605.338 | 3640.533 |
| L3 judge time (seconds) | 97.269 | 165.102 |
| Runner gates | 34 passed / 2 failed | 29 passed / 2 failed |

Timing and intervention differences are descriptive only because v2 used mixed retained host/device environments.

## V2 Per-Oracle Breakdown

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 11 | 5 | 6 | 1 |
| L2 | 12 | 12 | 6 | 6 | 0 |
| L3 | 6 | 6 | 3 | 3 | 0 |

## V2 Attempt Failure Classes

| Outcome | Count |
|---|---:|
| `preflight_environment` | 2 |

Failure classes count non-accountable attempts; 2 failed attempt(s) resolve to 1 non-accountable lane(s).

## V2 Lane Resolution

| Lane | Role | Oracle | Attempts | First accountable | Final status | Outcome |
|---|---|---|---:|---|---|---|
| `v2-anr-baseline-1` | baseline | L1 | 1 | true | accountable | passed_control |
| `v2-anr-baseline-2` | baseline | L1 | 1 | true | accountable | passed_control |
| `v2-anr-baseline-3` | baseline | L1 | 2 | false | non_accountable | non_accountable / preflight_environment |
| `v2-anr-defect-1` | defect | L1 | 1 | true | accountable | caught |
| `v2-anr-defect-2` | defect | L1 | 1 | true | accountable | caught |
| `v2-anr-defect-3` | defect | L1 | 1 | true | accountable | caught |
| `v2-oversized-state-baseline-1` | baseline | L1 | 1 | true | accountable | passed_control |
| `v2-oversized-state-baseline-2` | baseline | L1 | 1 | true | accountable | passed_control |
| `v2-oversized-state-baseline-3` | baseline | L1 | 1 | true | accountable | passed_control |
| `v2-oversized-state-defect-1` | defect | L1 | 1 | true | accountable | caught |
| `v2-oversized-state-defect-2` | defect | L1 | 1 | true | accountable | caught |
| `v2-oversized-state-defect-3` | defect | L1 | 1 | true | accountable | caught |
| `v2-query-duplication-baseline-1` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-query-duplication-baseline-2` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-query-duplication-baseline-3` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-query-duplication-defect-1` | defect | L2 | 1 | true | accountable | caught |
| `v2-query-duplication-defect-2` | defect | L2 | 1 | true | accountable | caught |
| `v2-query-duplication-defect-3` | defect | L2 | 1 | true | accountable | caught |
| `v2-swallowed-back-baseline-1` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-swallowed-back-baseline-2` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-swallowed-back-baseline-3` | baseline | L2 | 1 | true | accountable | passed_control |
| `v2-swallowed-back-defect-1` | defect | L2 | 1 | true | accountable | caught |
| `v2-swallowed-back-defect-2` | defect | L2 | 1 | true | accountable | caught |
| `v2-swallowed-back-defect-3` | defect | L2 | 1 | true | accountable | caught |
| `v2-search-card-baseline-1` | baseline | L3 | 1 | true | accountable | passed_control |
| `v2-search-card-baseline-2` | baseline | L3 | 1 | true | accountable | passed_control |
| `v2-search-card-baseline-3` | baseline | L3 | 1 | true | accountable | passed_control |
| `v2-search-card-defect-1` | defect | L3 | 1 | true | accountable | caught |
| `v2-search-card-defect-2` | defect | L3 | 1 | true | accountable | caught |
| `v2-search-card-defect-3` | defect | L3 | 1 | true | accountable | caught |

## V2 Bounded Attempt Lineage

| Lane | Attempt | Gate | Accountable | Exit | Seconds | Judge seconds | Interventions | Checksum |
|---|---:|---|---|---:|---:|---:|---:|---|
| `v2-anr-baseline-1` | 1 | passed | true | 0 | 111.695 | 0 | 0 | verified |
| `v2-anr-baseline-2` | 1 | passed | true | 0 | 95.431 | 0 | 0 | verified |
| `v2-anr-baseline-3` | 1 | failed | false | 2 | 18.112 | 0 | 0 | verified |
| `v2-anr-baseline-3` | 2 | failed | false | 2 | 5.43 | 0 | 1 | verified |
| `v2-anr-defect-1` | 1 | passed | true | 1 | 88.791 | 0 | 0 | verified |
| `v2-anr-defect-2` | 1 | passed | true | 1 | 77.691 | 0 | 0 | verified |
| `v2-anr-defect-3` | 1 | passed | true | 1 | 111.417 | 0 | 0 | verified |
| `v2-oversized-state-baseline-1` | 1 | passed | true | 0 | 107.935 | 0 | 0 | verified |
| `v2-oversized-state-baseline-2` | 1 | passed | true | 0 | 110.757 | 0 | 0 | verified |
| `v2-oversized-state-baseline-3` | 1 | passed | true | 0 | 120.292 | 0 | 0 | verified |
| `v2-oversized-state-defect-1` | 1 | passed | true | 1 | 118.741 | 0 | 0 | verified |
| `v2-oversized-state-defect-2` | 1 | passed | true | 1 | 122.373 | 0 | 0 | verified |
| `v2-oversized-state-defect-3` | 1 | passed | true | 1 | 135.263 | 0 | 0 | verified |
| `v2-query-duplication-baseline-1` | 1 | passed | true | 0 | 115.745 | 0 | 0 | verified |
| `v2-query-duplication-baseline-2` | 1 | passed | true | 0 | 124.343 | 0 | 0 | verified |
| `v2-query-duplication-baseline-3` | 1 | passed | true | 0 | 134.208 | 0 | 0 | verified |
| `v2-query-duplication-defect-1` | 1 | passed | true | 1 | 137.473 | 0 | 0 | verified |
| `v2-query-duplication-defect-2` | 1 | passed | true | 1 | 133.554 | 0 | 0 | verified |
| `v2-query-duplication-defect-3` | 1 | passed | true | 1 | 249.976 | 0 | 0 | verified |
| `v2-swallowed-back-baseline-1` | 1 | passed | true | 0 | 161.599 | 0 | 0 | verified |
| `v2-swallowed-back-baseline-2` | 1 | passed | true | 0 | 126.656 | 0 | 0 | verified |
| `v2-swallowed-back-baseline-3` | 1 | passed | true | 0 | 153.189 | 0 | 0 | verified |
| `v2-swallowed-back-defect-1` | 1 | passed | true | 1 | 134.359 | 0 | 0 | verified |
| `v2-swallowed-back-defect-2` | 1 | passed | true | 1 | 141.505 | 0 | 0 | verified |
| `v2-swallowed-back-defect-3` | 1 | passed | true | 1 | 157.907 | 0 | 0 | verified |
| `v2-search-card-baseline-1` | 1 | passed | true | 0 | 95.045 | 20.692 | 0 | verified |
| `v2-search-card-baseline-2` | 1 | passed | true | 0 | 88.211 | 20.893 | 0 | verified |
| `v2-search-card-baseline-3` | 1 | passed | true | 0 | 135.937 | 36.109 | 0 | verified |
| `v2-search-card-defect-1` | 1 | passed | true | 1 | 103.769 | 22.873 | 0 | verified |
| `v2-search-card-defect-2` | 1 | passed | true | 1 | 96.189 | 29.58 | 0 | verified |
| `v2-search-card-defect-3` | 1 | passed | true | 1 | 126.94 | 34.955 | 0 | verified |

## Execution and Evidence Identity

Audit host: `/Users/peter/projects/ai_verfication` at `471b44c27de9c43777bd552d78933050c1cc20f5`; Codex CLI `0.144.1`, Python `3.11.15`, pytest `9.0.3`.

Each lane is cross-checked against its own checksummed package environment; the reused serial alone is not treated as a homogeneous device identity.

| Package | Lanes / attempts | Host workspace | Wikipedia commit | Device | Android | Codex | Model |
|---|---:|---|---|---|---|---|---|
| `docs/runs/2026-07-15-m3-v2-anr-reliability` | 6 / 7 | `/Users/80268204/Projects/ai_verification` | `not retained` | `emulator-5554` / `medium_phone` | API 36 / Android 16 | `not retained` | `not retained` |
| `docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability` | 6 / 6 | `/Users/80268204/Projects/ai_verification` | `not retained` | `emulator-5554` / `medium_phone` | API 36 / Android 16 | `0.144.1` | `not retained` |
| `docs/runs/2026-07-15-m3-v2-query-duplication-reliability` | 6 / 6 | `/Users/peter/projects/ai_verfication` | `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b` | `emulator-5554` / `aiverify_api35` | API 35 / Android 15 | `0.144.1` | `not retained` |
| `docs/runs/2026-07-15-m3-v2-search-card-l3-reliability` | 6 / 6 | `/Users/peter/projects/ai_verfication` | `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b` | `emulator-5554` / `aiverify_api35` | API 35 / Android 15 | `0.144.1` | `gpt-5.6-sol` |
| `docs/runs/2026-07-15-m3-v2-swallowed-back-reliability` | 6 / 6 | `/Users/peter/projects/ai_verfication` | `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b` | `emulator-5554` / `aiverify_api35` | API 35 / Android 15 | `0.144.1` | `not retained` |

| Identity check | Coverage |
|---|---:|
| Package environment retained | 5/5 |
| Attempt device serial cross-check | 31/31 |
| Attempt host path cross-check | 31/31 |
| Attempt Run Spec command cross-check | 31/31 |
| Run Spec SHA-256 retained | 3/5 |
| Manifest SHA-256 retained | 3/5 |
| Wikipedia commit retained | 3/5 |
| Codex CLI version retained | 4/5 |
| Model identity retained | 1/5 |
| Retained model override cross-check | 6/6 |

`2026-07-15-m3-v2-search-card-l3-reliability` explicitly retain(s) effective model(s) `gpt-5.6-sol`. The other 4 package model identities are reported as unavailable, not backfilled from current configuration.
2 package(s) omit contemporaneous Run Spec hashes and 2 omit Wikipedia commits; current Run Spec hashes are shown in JSON as repository cross-checks with `not_retained` status.

## V2 Evidence Packages

| Package | Checksum entries | Status |
|---|---:|---|
| `docs/runs/2026-07-15-m3-v2-anr-reliability` | 96 | verified |
| `docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability` | 136 | verified |
| `docs/runs/2026-07-15-m3-v2-query-duplication-reliability` | 147 | verified |
| `docs/runs/2026-07-15-m3-v2-search-card-l3-reliability` | 129 | verified |
| `docs/runs/2026-07-15-m3-v2-swallowed-back-reliability` | 147 | verified |

## Historical Integrity

- Status: **VERIFIED**.
- Manifest: `bench/goldset/m3-reliability-slice.yaml` / `8017320a27a5a8e0a01fff1357abf09edf0164abf59e764dc843b5335c0271b3`.
- Final record: `docs/runs/2026-07-13-m3-final-reliability-baseline`.
- The retained historical JSON and Markdown were regenerated from their evidence and matched byte-for-model; all five historical package checksum anchors also matched.
- Original and v2 denominators are not combined, and no original lane is selectively replaced.

## Scope and Claim Boundary

- Wikipedia host only
- Codex CLI Verification Agent Backend only
- Android CLI across the two declared package environments: Android 16/API 36 medium_phone and Android 15/API 35 aiverify_api35 emulators
- versioned five-seed, 30-lane live v2 slice only
- mixed host/device environments prevent causal timing comparisons
- not a fully unattended Journey measurement
- not a benchmark-wide detection or false-positive rate
- not a physical-device, ColorOS, or visual-only/multimodal claim
