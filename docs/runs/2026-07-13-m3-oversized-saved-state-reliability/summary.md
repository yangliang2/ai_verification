# M3 Verification Agent Reliability Summary

Slice: `m3-verification-agent-reliability`

## Accountability

| Metric | Count |
|---|---:|
| Planned lanes | 12 |
| First-attempt accountable | 9 |
| Eventual accountable | 10 |
| Retries | 3 |
| Operational interventions | 5 |
| Total attempt time (seconds) | 2519.497 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 6 |

## Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 4 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 2 |
| `verification_agent_journey` | 2 |

## Scope Boundary

This bounded slice does not support a benchmark-wide detection-rate claim,
benchmark-wide false-positive-rate claim, fully unattended Journey claim,
cross-host claim, or visual-only/multimodal L3 claim.
