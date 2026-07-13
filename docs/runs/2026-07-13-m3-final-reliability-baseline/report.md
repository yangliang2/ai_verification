# M3 Verification Agent Audited Reliability Baseline

Slice: `m3-verification-agent-reliability`

## Decision

| Criterion | Result | Evidence |
|---|---|---|
| M3 overall | **FAILED** | One or more required M3 criteria failed |
| Eventual accountability | **FAILED** | 27 / 30; required >=29 / 30 |
| Accountable baseline false positives | **PASSED** | 0 observed; required 0 |
| Accountable defect consistency | **PASSED** | 12 / 12 caught at expected level/class |

M3 is unmet because these criteria failed: eventual accountability (27 / 30; required >=29 / 30).
Non-accountable lanes remain execution-reliability failures and are not
reclassified as oracle misses, catches, passed controls, or false positives.

## Aggregate

| Metric | Value |
|---|---:|
| Planned lanes | 30 |
| First-attempt accountable | 24 |
| Eventual accountable | 27 |
| Retries | 6 |
| Passed controls | 15 |
| Caught defects | 12 |
| Operational interventions | 9 |
| Total attempt time (seconds) | 4605.338 |
| L3 judge time (seconds) | 97.269 |

## Per-Oracle Breakdown

| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |
|---|---:|---:|---:|---:|---:|
| L1 | 12 | 10 | 6 | 4 | 2 |
| L2 | 12 | 12 | 6 | 6 | 0 |
| L3 | 6 | 5 | 3 | 2 | 1 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 2 |
| `verification_agent_journey` | 6 |

## Lane Resolution

| Lane | Role | Oracle | Attempts | First accountable | Eventual result |
|---|---|---|---:|---|---|
| `anr-baseline-1` | baseline | L1 | 1 | true | passed_control |
| `anr-baseline-2` | baseline | L1 | 1 | true | passed_control |
| `anr-baseline-3` | baseline | L1 | 1 | true | passed_control |
| `anr-defect-1` | defect | L1 | 2 | false | non_accountable / evidence_capture |
| `anr-defect-2` | defect | L1 | 2 | false | non_accountable / verification_agent_journey |
| `anr-defect-3` | defect | L1 | 1 | true | caught |
| `oversized-state-baseline-1` | baseline | L1 | 1 | true | passed_control |
| `oversized-state-baseline-2` | baseline | L1 | 1 | true | passed_control |
| `oversized-state-baseline-3` | baseline | L1 | 1 | true | passed_control |
| `oversized-state-defect-1` | defect | L1 | 1 | true | caught |
| `oversized-state-defect-2` | defect | L1 | 1 | true | caught |
| `oversized-state-defect-3` | defect | L1 | 2 | false | caught |
| `query-duplication-baseline-1` | baseline | L2 | 1 | true | passed_control |
| `query-duplication-baseline-2` | baseline | L2 | 1 | true | passed_control |
| `query-duplication-baseline-3` | baseline | L2 | 1 | true | passed_control |
| `query-duplication-defect-1` | defect | L2 | 1 | true | caught |
| `query-duplication-defect-2` | defect | L2 | 2 | false | caught |
| `query-duplication-defect-3` | defect | L2 | 1 | true | caught |
| `swallowed-back-baseline-1` | baseline | L2 | 1 | true | passed_control |
| `swallowed-back-baseline-2` | baseline | L2 | 1 | true | passed_control |
| `swallowed-back-baseline-3` | baseline | L2 | 1 | true | passed_control |
| `swallowed-back-defect-1` | defect | L2 | 2 | false | caught |
| `swallowed-back-defect-2` | defect | L2 | 1 | true | caught |
| `swallowed-back-defect-3` | defect | L2 | 1 | true | caught |
| `search-card-baseline-1` | baseline | L3 | 1 | true | passed_control |
| `search-card-baseline-2` | baseline | L3 | 1 | true | passed_control |
| `search-card-baseline-3` | baseline | L3 | 1 | true | passed_control |
| `search-card-defect-1` | defect | L3 | 1 | true | caught |
| `search-card-defect-2` | defect | L3 | 1 | true | caught |
| `search-card-defect-3` | defect | L3 | 2 | false | non_accountable / verification_agent_journey |

## Execution Identity

- Host: Wikipedia at `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`; clean audit worktree.
- Device: `emulator-5554` / `aiverify_api35`, Android 15 API 35, model `sdk_gphone64_arm64`.
- Verification Agent Backend: Codex CLI `0.144.1`.
- Android CLI `1.0.15498356`; adb `1.0.41 / platform-tools 37.0.0-14910828`; OpenJDK `17.0.19`; Python `3.11.15`; pytest `9.0.3`.
- Runner gates: 34 passed, 2 failed.

## Evidence Packages

| Package | Checksum entries | Status |
|---|---:|---|
| `docs/runs/2026-07-13-m3-anr-reliability` | 103 | verified |
| `docs/runs/2026-07-13-m3-oversized-saved-state-reliability` | 134 | verified |
| `docs/runs/2026-07-13-m3-query-duplication-reliability` | 144 | verified |
| `docs/runs/2026-07-13-m3-search-card-l3-reliability` | 118 | verified |
| `docs/runs/2026-07-13-m3-swallowed-back-reliability` | 218 | verified |

## Scope and Claim Boundary

- Wikipedia host only
- Codex CLI Verification Agent Backend only
- Android CLI on one API 35 emulator only
- five-seed, 30-lane live slice only
- not a fully unattended Journey measurement
- not a benchmark-wide detection or false-positive rate
- not a cross-host, physical-device, ColorOS, or visual-only/multimodal claim
