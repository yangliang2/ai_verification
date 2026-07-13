# M3 Verification Agent Reliability Summary

Slice: `m3-verification-agent-reliability`

## Accountability

| Metric | Count |
|---|---:|
| Planned lanes | 18 |
| First-attempt accountable | 14 |
| Eventual accountable | 16 |
| Retries | 4 |
| Operational interventions | 7 |
| Total attempt time (seconds) | 3195.442 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 9 |

## Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 7 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 2 |
| `verification_agent_journey` | 3 |

## Scope Boundary

This bounded slice does not support a benchmark-wide detection-rate claim,
benchmark-wide false-positive-rate claim, fully unattended Journey claim,
cross-host claim, or visual-only/multimodal L3 claim.
