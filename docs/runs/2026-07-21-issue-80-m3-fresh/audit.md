# M3 Verification Agent Immutable V3 Audit

Slice: `m3-verification-agent-reliability-issue80-fresh`

## Decision

| Criterion | Result | Evidence |
|---|---|---|
| M3 v3 overall | **PASSED** | All strict v3 criteria must pass |
| Eventual accountability | **PASSED** | 30 / 30; required 30 / 30 |
| Baseline controls | **PASSED** | 15 / 15 passed; 0 false positives |
| Expected defect detection | **PASSED** | 15 / 15 caught at expected oracle/class |
| Complete execution provenance | **PASSED** | 30 / 30 attempts |

Original, v2, and v3 remain three distinct 30-lane populations. Their denominators are never merged and no historical lane is replaced.

## Immutable Population Comparison

| Metric | Original | V2 | V3 |
|---|---:|---:|---:|
| Decision | FAILED | PASSED | PASSED |
| Eventual accountable | 27 / 30 | 29 / 30 | 30 / 30 |
| Retries | 6 | 1 | 0 |

## V3 Per-Oracle Breakdown

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 12 | 6 | 6 | 0 |
| L2 | 12 | 12 | 6 | 6 | 0 |
| L3 | 6 | 6 | 3 | 3 | 0 |

## V3 Lane and Attempt Lineage

| Lane | Role | Oracle | Attempt | Accountable | Outcome | Provenance | Checksum |
|---|---|---|---:|---|---|---|---|
| `issue80-anr-baseline-1` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-anr-baseline-2` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-anr-baseline-3` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-anr-defect-1` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-anr-defect-2` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-anr-defect-3` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-oversized-baseline-1` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-oversized-baseline-2` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-oversized-baseline-3` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `issue80-oversized-defect-1` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-oversized-defect-2` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-oversized-defect-3` | defect | L1 | 1 | true | caught | verified | verified |
| `issue80-query-baseline-1` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-query-baseline-2` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-query-baseline-3` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-query-defect-1` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-query-defect-2` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-query-defect-3` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-swallowed-baseline-1` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-swallowed-baseline-2` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-swallowed-baseline-3` | baseline | L2 | 1 | true | passed_control | verified | verified |
| `issue80-swallowed-defect-1` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-swallowed-defect-2` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-swallowed-defect-3` | defect | L2 | 1 | true | caught | verified | verified |
| `issue80-search-baseline-1` | baseline | L3 | 1 | true | passed_control | verified | verified |
| `issue80-search-baseline-2` | baseline | L3 | 1 | true | passed_control | verified | verified |
| `issue80-search-baseline-3` | baseline | L3 | 1 | true | passed_control | verified | verified |
| `issue80-search-defect-1` | defect | L3 | 1 | true | caught | verified | verified |
| `issue80-search-defect-2` | defect | L3 | 1 | true | caught | verified | verified |
| `issue80-search-defect-3` | defect | L3 | 1 | true | caught | verified | verified |

## Execution Identity Coverage

- `package_environment`: 5/5
- `device_serial_crosscheck`: 30/30
- `host_path_crosscheck`: 30/30
- `run_spec_command_crosscheck`: 30/30
- `run_spec_sha256_retained`: 5/5
- `manifest_sha256_retained`: 5/5
- `host_commit_retained`: 5/5
- `backend_version_retained`: 5/5
- `model_identity_retained`: 5/5
- `model_override_crosscheck`: 30/30

## Evidence Packages

- `docs/runs/2026-07-21-issue-80-m3-fresh/anr`: 121 entries, verified
- `docs/runs/2026-07-21-issue-80-m3-fresh/oversized`: 157 entries, verified
- `docs/runs/2026-07-21-issue-80-m3-fresh/query`: 157 entries, verified
- `docs/runs/2026-07-21-issue-80-m3-fresh/search`: 151 entries, verified
- `docs/runs/2026-07-21-issue-80-m3-fresh/swallowed`: 157 entries, verified

## Scope and Claim Boundary

- Wikipedia host only
- Codex CLI Verification Agent Backend only
- Android CLI on one Android 15/API 35 aiverify_api35 emulator only
- versioned five-seed, 30-lane live v3 slice only
- not a fully unattended Journey measurement
- not a benchmark-wide detection or false-positive rate
- not a physical-device, ColorOS, or visual-only/multimodal claim
