# M3 Verification Agent Reliability Summary

Slice: `m3-verification-agent-reliability`

## Accountability

| Metric | Count |
|---|---:|
| Planned lanes | 24 |
| First-attempt accountable | 19 |
| Eventual accountable | 22 |
| Retries | 5 |
| Operational interventions | 8 |
| Total attempt time (seconds) | 4104.583 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 12 |

## Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 10 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 2 |
| `verification_agent_journey` | 4 |

## Scope Boundary

This bounded slice does not support a benchmark-wide detection-rate claim,
benchmark-wide false-positive-rate claim, fully unattended Journey claim,
cross-host claim, or visual-only/multimodal L3 claim.
