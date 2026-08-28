---
status: proposed
---

# First-class Journey driver backends

## Context

The production Run Spec path currently assumes that every Journey is driven by
Codex CLI. That assumption leaks into request types, artifact names, and
execution identity: even a deterministic runtime calibration would appear to
have invoked a model. OpenCalc needs a constrained deterministic Journey while
preserving Codex as the existing production-shaped backend and keeping Run Spec
semantics independent of either implementation.

## Decision

Introduce an admitted runner-policy choice with the closed backend identities
`codex_cli` and `deterministic_android_v1`. Selection is explicit and remains
outside the Run Spec. Existing callers default to `codex_cli`, and existing
Codex records remain verifiable without migration.

Each backend has a distinct request/protocol type and owns only its raw
execution evidence. The runner emits backend-neutral
`journey-result.normalized.json` and `journey-action-lineage.json`, while
Effective Execution Identity binds only tools and models actually invoked.
Journey and L3 identities remain independent.

`deterministic_android_v1` requires one strict-JSON Deterministic Driver Plan
bound to one exact Run Spec. Its request contains only opaque action identity,
the admitted plan slice, a narrow device-primitive adapter, and an opaque
evidence sink. V1 admits only fixed-timing resource-ID waits and taps; it
receives no source mapping, diff, oracle, expected result, host worktree, or
unrestricted command/filesystem interface. This is an enforced type,
admission, and capability boundary, not a claim that the process runs in an
operating-system sandbox.

## Rationale

A first-class backend seam prevents deterministic execution from fabricating a
Codex receipt and makes the evidence boundary testable. Separate request types
keep sensitive source-rich fields out of the deterministic driver's reachable
data flow, while normalized artifacts let downstream accountability code remain
backend-neutral. Retaining the Codex default avoids rewriting historical
evidence or changing existing callers merely to add the new backend.

## Consequences

- Backend admission, raw-receipt validation, and identity collection become
  explicit extension points.
- Adding another backend requires a new closed identity, request type, receipt
  validator, and identity policy; backend inference from files is forbidden.
- A deterministic action success proves only validated dispatch. Product state
  and oracle conclusions remain runner-owned.
- This ADR remains proposed until strict contract tests and recording-fake
  integration tests cover both backends, their rejection paths, normalized
  evidence, least-authority requests, zero retries, and legacy Codex fixtures.

## Rejected alternatives

- **A one-off deterministic script:** bypasses the production Journey seam and
  cannot establish backend-neutral evidence or identity behavior.
- **A shared request with optional sensitive fields:** creates a shallow
  blindness claim because source and oracle data remain reachable.
- **Pretend deterministic execution is Codex:** falsifies the execution record
  and tool/model provenance.
- **Replace Codex with deterministic execution globally:** discards the
  production-shaped agent backend instead of adding a bounded calibration role.
