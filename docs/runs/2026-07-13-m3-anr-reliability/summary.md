# M3 Verification Agent Reliability Summary

Slice: `m3-verification-agent-reliability`

## Accountability

| Metric | Count |
|---|---:|
| Planned lanes | 6 |
| First-attempt accountable | 4 |
| Eventual accountable | 4 |
| Retries | 2 |
| Operational interventions | 4 |
| Total attempt time (seconds) | 1535.477 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 3 |

## Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 1 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 1 |
| `verification_agent_journey` | 2 |

## Scope Boundary

This bounded slice does not support a benchmark-wide detection-rate claim,
benchmark-wide false-positive-rate claim, fully unattended Journey claim,
cross-host claim, or visual-only/multimodal L3 claim.
