# Wikipedia deterministic network reliability fixture

This debug-only fixture is a bounded behavior-layer verification slice for GitHub
#69. It does not exercise Wikipedia production endpoints and makes no production
networking redesign claim. Fixed content values and fixed main-loop delays remove
server variance while real `network_off`, `network_on`, and `wait` system events
prove the device transition contract.

The matched baseline and candidate use the same API/device, content, action list,
system events, and checkpoint timing. Their only behavioral difference is the
fixture constant `INJECT_DEFECT`: the candidate performs six retry attempts and
allows the delayed old response to overwrite the newer response.

The Activity logs JSON objects under the `AIVerifyNetwork` tag. Every object has a
strictly increasing `sequence`, `scenario`, `kind`, and `request_id`, with optional
`attempt` and `content`. Visible terminal state uses the fixed fields `Fixture ID`,
`Scenario`, `State`, `Content`, and `Retry enabled`.

The machine oracle consumes a baseline and candidate evidence bundle. Missing or
contradictory identity, Journey, transition, checkpoint, sequence, or event evidence
is `non_accountable`. A clean baseline plus a rejected injected candidate is
`locally_supported`; an escaped defect or failing baseline is `locally_rejected`.
It detects crash/ANR, blank/error UI, duplicate retry/retry storm, cancellation
failure, stale-response overwrite, and missing recovery evidence. It never emits a
detection-rate, Goldset, or upstream-acceptance claim.
