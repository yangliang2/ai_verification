---
status: proposed
---

# Accountable Runtime Calibration Family

The exact V1 protocol is frozen in
[`docs/opencalc-runtime-calibration-v1.md`](../opencalc-runtime-calibration-v1.md).

## Context

The next Injection Lab calibration must prove that ChangeTarget and
ProjectTarget discovery can reach a real Android behavior boundary without
claiming a formal benchmark result. OpenCalc at the pinned upstream revision
offers a narrow matched pair: the only source difference toggles input state
saving, and the observable contract is whether unfinished expression `12+34`
survives orientation-driven Activity recreation. A convenient four-run script
would not prove source identity, blinding, build identity, lifecycle causality,
or attempt accountability.

## Decision

Create `opencalc-runtime-calibration-v1` as a non-formal Runtime Calibration
Family with exactly four cells: ChangeTarget and ProjectTarget crossed with one
matched control and defect. Every cell uses the same neutral Quality Contract,
Risk Hypothesis, Attack Plan, setup, driver actions, lifecycle event, and oracle.
The matched source entries share one upstream commit, target file, insertion
anchor, operator, taxonomy, and patch context; only the boolean right-hand side
differs.

All four side-effect-free Discovery Campaigns and leakage checks close before a
single atomic Runtime Mapping Release. Auditor-only Source-Rich Discovery
Packages retain source meaning; driver-facing Blind Runtime Projections and
lane paths remain uniformly opaque. Only Source Authority and the final pure
reducer may consume the released mapping.

Before any family device attempt, Auditor Runtime Preflight must complete the
frozen nine-cycle Latin-square upstream/control/defect calibration. Runtime
Family Preparation then materializes four fresh source trees, performs one
sealed offline build per lane from the external Runtime Input Vault, verifies
the common family signing identity and APK metadata, and closes all byte-
equality/difference gates. Preparation creates no ExecutionRecord and a failed
family is repaired only under a new version.

Implementation, schemas, public inputs, plans, recipes, manifests, and
discovery/mapping commitments are frozen together in one
`calibration_implementation_commit` before preflight. Both preflight and family
execute from that commit's clean detached verifier worktree and bound external
venv. Successful preflight grants execution through a separate checksum-bound
`family-admission.json`; copying generated evidence into later main-worktree
commits does not change the execution identity and cannot make that evidence
executable input.

Execution is exposed only as explicit `verify-candidate`, `run-preflight`,
`admit-family`, `prepare-family`, `execute-family`, `reduce-family`, and
`verify-record` stages. Each mutating stage requires a new empty output root and
its predecessor's terminal receipt; there is no force, resume, retry, or
automatic stage chaining. A started stage that lacks terminal evidence is
`abandoned` and consumes its version whenever absence of side effects cannot be
proved. Cleanup may stop an orphaned emulator but cannot restore eligibility.

The admitted family uses one fresh API-35 cold boot and the fixed opaque lane
order. Each started lane gets one attempt and zero retries. The accountable
phase order is static identity, deploy and installed-byte verification,
package/portrait setup, one marker-bounded log window, one canonical launch,
the deterministic resource-ID Journey, a proven Boundary Precondition, one
orientation event, a Lifecycle Transition Receipt, and the exact state
preservation oracle. Only package clear and the two declared rotation-setting
writes may modify device state; other identity-critical settings are observed
and held invariant.

The no-I/O Runtime Calibration Reducer emits only
`expected_split_observed`, `unexpected_runtime_result`, or `not_calibrated`.
The expected split is four accountable lanes, L1 `inconclusive` throughout,
control L2 `pass`, and defect L2 `fail` with `state_loss`. Non-accountable,
unattempted, or preparation-rejected lanes cannot be converted into oracle
results. Discovery, Journey execution, L1/L2 evaluation, and reduction are all
deterministic; the family forbids L3, Verification Agent conclusions, Findings,
Falsification Review, independent model adjudication, and every live model call.
Its invocation ledger must prove zero such calls, and an accidental model
invocation invalidates the family. All actual inputs, receipts, commands, APKs,
logs, layouts, reductions, and checksums are preserved in a committed Runtime
Calibration Run Record.

## Rationale

The four-cell matched design tests both discovery entry points while holding the
runtime behavior constant. Separate preflight, preparation, and attempt phases
prevent a build or tooling failure from masquerading as product evidence.
Opaque runtime projection tests the intended data-flow boundary, while the
single mapping release still lets trusted source materialization and reduction
interpret the family. One-attempt execution preserves failures instead of
optimizing the result after observation.

## Consequences

- The family is intentionally expensive: it needs nine auditor cycles, four
  isolated builds, one dedicated device session, and durable evidence.
- Private signing material and the sealed dependency bundle remain outside Git;
  their public manifests, hashes, and receipts are committed.
- Any frozen implementation, input, lifecycle signature, mapping, or identity
  change requires a new family version and, where applicable, a complete new
  preflight.
- `expected_split_observed` is local calibration evidence only. It is not a
  Qualification Cohort, holdout result, pass rate, or Verification Agent
  capability claim.
- This ADR remains proposed through simulated validation and becomes accepted
  only after the complete frozen nine-cycle Auditor Runtime Preflight succeeds;
  the later four-cell reducer result may still be any valid terminal family
  state.

## Rejected alternatives

- **Reuse M8/M9 as a formal population:** incorrectly introduces a denominator
  and capability interpretation before the new runtime seams are calibrated.
- **Run only ChangeTarget or only ProjectTarget:** leaves the other discovery
  and source-materialization path untested.
- **Build and patch inside each device attempt:** mixes preparation failures
  with runtime accountability and permits observed outcomes to influence later
  inputs.
- **Use independent mappings or unblinding per lane:** enables progressive
  leakage and asymmetric treatment.
- **Retry failed cells:** replaces the preregistered attempt with a selected
  result and destroys the intended evidence boundary.
