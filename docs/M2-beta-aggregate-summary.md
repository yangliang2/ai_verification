# M2-beta Aggregate Summary

Generated from `bench/goldset/m2-beta-slice.yaml` and run-spec
`scenario.metric_context` metadata.

## Accounting Summary

| Bucket | Count |
|---|---:|
| Included injected-defect seeds | 9 |
| Blocked seeds | 1 |
| Candidate seeds | 1 |
| Repeatability-only packages | 2 |

## Included Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 9 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 9 |

## Expected Oracle Levels

| Oracle level | Count |
|---|---:|
| `L1` | 3 |
| `L2` | 4 |
| `L3` | 2 |

## Taxonomy Coverage

| Taxonomy category | Count |
|---|---:|
| `config-change` | 2 |
| `coroutine-concurrency` | 1 |
| `lifecycle` | 1 |
| `navigation` | 2 |
| `process-death` | 1 |
| `ui-rendering` | 2 |

## Oracle Defect-Class Coverage

| Oracle defect class | Count |
|---|---:|
| `crash_stability` | 3 |
| `state_loss` | 4 |
| `ui_rendering` | 2 |

## Blocked And Candidate Seeds

| Seed | State | Candidate | Reason |
|---|---|---:|---|
| `wikipedia-process-death-03-oversized-saved-state` | `blocked` | true | No valid baseline/defect matched pair; Android execution environment blocked the live retry. |

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
