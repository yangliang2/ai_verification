# M2-beta Aggregate Summary

Generated from `bench/goldset/m2-beta-slice.yaml`, run-spec
`scenario.metric_context` metadata, committed lane verdicts, and
fixed-evidence repeatability summaries.

## Accounting Summary

| Bucket | Count |
|---|---:|
| Included injected-defect seeds | 10 |
| Blocked seeds | 0 |
| Candidate seeds | 0 |
| Repeatability-only packages | 2 |

## Included Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 10 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 10 |

## Expected Oracle Levels

| Oracle level | Count |
|---|---:|
| `L1` | 4 |
| `L2` | 4 |
| `L3` | 2 |

## Taxonomy Coverage

| Taxonomy category | Count |
|---|---:|
| `config-change` | 2 |
| `coroutine-concurrency` | 1 |
| `lifecycle` | 1 |
| `navigation` | 2 |
| `process-death` | 2 |
| `ui-rendering` | 2 |

## Oracle Defect-Class Coverage

| Oracle defect class | Count |
|---|---:|
| `crash_stability` | 4 |
| `state_loss` | 4 |
| `ui_rendering` | 2 |

## Evidence Contracts

| Evidence contract | Count |
|---|---:|
| `legacy_control_document` | 3 |
| `verdict` | 7 |

Standard `verdict` lanes derive caught/missed and control outcomes from
committed baseline/defect `verdict.json` files. `legacy_control_document`
marks pre-runner-contract control evidence that is explicitly documented
but does not have a standalone control verdict; it remains a legacy
historical classification.

## Blocked And Candidate Seeds

| Seed | State | Candidate | Reason |
|---|---|---:|---|
| None | - | - | - |

## Fixed-Evidence L3 Repeatability

| Package | Seed | Calls | Baseline passes | Defect fails | Errors |
|---|---|---:|---:|---:|---:|
| `ui-rendering-01-l3-repeatability` | `wikipedia-ui-rendering-01-nav-label-swap` | 10 | 5 | 5 | 0 |
| `ui-rendering-02-l3-repeatability` | `wikipedia-ui-rendering-02-search-card-copy-mismatch` | 10 | 5 | 5 | 0 |

Fixed-evidence repeatability supports the bounded L3 stability claim.
It does not add extra caught, missed, or control outcomes.

## Scope Boundary

This is a small M2-beta benchmark slice summary. It is not a
benchmark-wide detection-rate claim, benchmark-wide false-positive-rate
claim, ColorOS migration claim, or fully unattended Journey reliability
claim.
