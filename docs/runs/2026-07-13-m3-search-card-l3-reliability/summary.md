# M3 Verification Agent Reliability Summary

Slice: `m3-verification-agent-reliability`

## Accountability

| Metric | Count |
|---|---:|
| Planned lanes | 30 |
| First-attempt accountable | 24 |
| Eventual accountable | 27 |
| Retries | 6 |
| Operational interventions | 9 |
| Total attempt time (seconds) | 4605.338 |
| L3 judge time (seconds) | 97.269 |

## Baseline Control Outcomes

| Outcome | Count |
|---|---:|
| `passed_control` | 15 |

## Injected-Defect Outcomes

| Outcome | Count |
|---|---:|
| `caught` | 12 |

## Non-Accountable Failure Classes

| Outcome | Count |
|---|---:|
| `evidence_capture` | 1 |
| `preflight_environment` | 2 |
| `verification_agent_journey` | 6 |

## Scope Boundary

This bounded slice does not support a benchmark-wide detection-rate claim,
benchmark-wide false-positive-rate claim, fully unattended Journey claim,
cross-host claim, or visual-only/multimodal L3 claim.
