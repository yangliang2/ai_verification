# Independent Verification Agent invocation

- Agent kind: collaboration subagent
- Canonical task name: /root/issue71_verification_agent
- Mode: read-only
- Audited lanes: baseline/attempt-2 and candidate/attempt-2
- Output contract:
  bench/capability-slices/lifecycle-recovery/independent-conclusion-schema.json
- Final output: exactly one schema-shaped JSON object, archived as
  conclusion.json

The collaboration API exposes the final agent message but not a raw model
transcript or CLI thread identifier. No such transcript or identifier is
claimed. The primary agent copied the final JSON message byte-for-JSON into
conclusion.json and validated that file locally.

During the audit, the agent reported that both attempt-2 lane directories
remained stable. Root documentation and the pre-review audit directory changed
outside the two audited lanes; the agent observed that and found no evidence
contamination.
