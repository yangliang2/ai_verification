# M3 Verification Agent Immutable V3 Audit

Slice: `m3-verification-agent-reliability-v3`

## Decision

| Criterion | Result | Evidence |
|---|---|---|
| M3 v3 overall | **FAILED** | All strict v3 criteria must pass |
| Eventual accountability | **FAILED** | 6 / 30; required 30 / 30 |
| Baseline controls | **FAILED** | 3 / 15 passed; 0 false positives |
| Expected defect detection | **FAILED** | 3 / 15 caught at expected oracle/class |
| Complete execution provenance | **FAILED** | 6 / 54 attempts |

Original, v2, and v3 remain three distinct 30-lane populations. Their denominators are never merged and no historical lane is replaced.

## Immutable Population Comparison

| Metric | Original | V2 | V3 |
|---|---:|---:|---:|
| Decision | FAILED | PASSED | FAILED |
| Eventual accountable | 27 / 30 | 29 / 30 | 6 / 30 |
| Retries | 6 | 1 | 24 |

## V3 Per-Oracle Breakdown

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 6 | 3 | 3 | 6 |
| L2 | 12 | 0 | 0 | 0 | 12 |
| L3 | 6 | 0 | 0 | 0 | 6 |

## V3 Lane and Attempt Lineage

| Lane | Role | Oracle | Attempt | Accountable | Outcome | Provenance | Checksum |
|---|---|---|---:|---|---|---|---|
| `v3-anr-baseline-1` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `v3-anr-baseline-2` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `v3-anr-baseline-3` | baseline | L1 | 1 | true | passed_control | verified | verified |
| `v3-anr-defect-1` | defect | L1 | 1 | true | caught | verified | verified |
| `v3-anr-defect-2` | defect | L1 | 1 | true | caught | verified | verified |
| `v3-anr-defect-3` | defect | L1 | 1 | true | caught | verified | verified |
| `v3-oversized-state-baseline-1` | baseline | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-baseline-1` | baseline | L1 | 2 | false | non_accountable | missing | verified |
| `v3-oversized-state-baseline-2` | baseline | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-baseline-2` | baseline | L1 | 2 | false | non_accountable | missing | verified |
| `v3-oversized-state-baseline-3` | baseline | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-baseline-3` | baseline | L1 | 2 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-1` | defect | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-1` | defect | L1 | 2 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-2` | defect | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-2` | defect | L1 | 2 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-3` | defect | L1 | 1 | false | non_accountable | missing | verified |
| `v3-oversized-state-defect-3` | defect | L1 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-1` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-1` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-2` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-2` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-3` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-baseline-3` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-1` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-1` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-2` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-2` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-3` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-query-duplication-defect-3` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-1` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-1` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-2` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-2` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-3` | baseline | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-baseline-3` | baseline | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-1` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-1` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-2` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-2` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-3` | defect | L2 | 1 | false | non_accountable | missing | verified |
| `v3-swallowed-back-defect-3` | defect | L2 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-1` | baseline | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-1` | baseline | L3 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-2` | baseline | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-2` | baseline | L3 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-3` | baseline | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-baseline-3` | baseline | L3 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-defect-1` | defect | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-defect-1` | defect | L3 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-defect-2` | defect | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-defect-2` | defect | L3 | 2 | false | non_accountable | missing | verified |
| `v3-search-card-defect-3` | defect | L3 | 1 | false | non_accountable | missing | verified |
| `v3-search-card-defect-3` | defect | L3 | 2 | false | non_accountable | missing | verified |

## Execution Identity Coverage

- `package_environment`: 5/5
- `device_serial_crosscheck`: 54/54
- `host_path_crosscheck`: 54/54
- `run_spec_command_crosscheck`: 54/54
- `run_spec_sha256_retained`: 5/5
- `manifest_sha256_retained`: 5/5
- `host_commit_retained`: 5/5
- `backend_version_retained`: 5/5
- `model_identity_retained`: 5/5
- `model_override_crosscheck`: 54/54

## Evidence Packages

- `docs/runs/2026-07-17-m3-v3-anr-reliability`: 128 entries, verified
- `docs/runs/2026-07-17-m3-v3-oversized-saved-state-reliability`: 74 entries, verified
- `docs/runs/2026-07-17-m3-v3-query-duplication-reliability`: 74 entries, verified
- `docs/runs/2026-07-17-m3-v3-search-card-l3-reliability`: 74 entries, verified
- `docs/runs/2026-07-17-m3-v3-swallowed-back-reliability`: 74 entries, verified

## Scope and Claim Boundary

- Wikipedia host only
- Codex CLI Verification Agent Backend only
- Android CLI on one Android 15/API 35 aiverify_api35 emulator only
- versioned five-seed, 30-lane live v3 slice only
- not a fully unattended Journey measurement
- not a benchmark-wide detection or false-positive rate
- not a physical-device, ColorOS, or visual-only/multimodal claim
