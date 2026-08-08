# R3 dual-axis review remediation

Scope: issue #152 candidate freeze, reviewed against repository standards,
`CONTEXT.md`, ADRs 0001–0003, and the issue acceptance criteria.

## Standards findings remediated

- Reconciliation now verifies the released mapping's raw/canonical commitments,
  exact lane order, balanced three-block 3+3 design, and each lane-role
  assignment before counting.
- The Supported reducer no longer emits constant attempt/retry/replacement
  counts. It consumes a checksum-bound one-entry formal-attempt inventory,
  cross-checks every terminal lane, and derives all counts.
- Six reviews require unique invocation, identity, and clean-context digests;
  default Codex selection and effective model come from authoritative events.
  The complete authoritative review and production identity sets are globally
  disjoint, not merely different within the same lane.
- Attempt Evidence is read from real files below an explicit clean repository
  root. Hashes, terminal ExecutionRecord/provenance, fresh R4 admission, runner
  setup, authoritative production identities, ordered raw evidence, oracle,
  typed Finding and ResidualRisk, Project Risk Map, claim boundary, review
  identity/context, persisted validation receipt, and exhaustive lane ledger
  must agree before a lane can count.
- All approval-bound packet sections now have semantic validation. Deleting a
  section and recomputing the packet commitment is rejected by regression
  tests.
- Existing mappings are validated before RunSpec generation; an unbalanced
  pre-existing mapping fails closed.
- R3 admissions are explicitly feasibility-only. Exact portable R4 artifact
  identities are frozen, only clean worktree paths may be re-resolved, and R4
  must obtain new admissions.
- Admission audit binds worktree/host identity, artifact namespace and absence,
  outer/nested policy versions, default tool names and tool identities, and
  both default-model selection receipts.
- A frozen manifest blocks ordinary candidate regeneration and checksum-ledger
  regeneration. Post-freeze ledger checking is read-only.
- Approval finalization requires a #152 GitHub issue-comment URL, nonblank
  reviewer, timezone-aware timestamp, and identical `frozen_at`/`approved_at`.
- Generated `__pycache__` content was removed from the run-record tree.

The second sealed tree
`c4f1c8f65202c45272e8f58b24a54dbf595e66a4` received a failing Standards
verdict before approval. Its four reproduced P1 classes are also closed:

- the review command parser rejects `--model`/`-m`, `--profile`/`-p`, and
  `--config`/`-c` model overrides in both split and equals forms;
- only a fresh `codex exec` command is admitted, so a resumed production
  session cannot qualify as a clean review;
- exhaustive formal-root enumeration examines every regular file regardless
  of suffix, rejects malformed `execution-record*` files, and counts a valid
  `.bak` ExecutionRecord as a forbidden seventh record; and
- admission receipts require exact complete nested schemas, production
  execution provenance is checked by the authoritative runner validator and
  cross-bound to the frozen lane, and PNG evidence must parse as a complete
  CRC-valid, decompressible image with the required dimensions and orientation.

## Spec findings remediated

The first sealed tree `95822aaf1f41f94afe3e0228ade79d7fccfedef1`
received Standards PASS and Spec FAIL. Before any approval or formal execution,
the Spec reviewer independently reproduced three P1 fail-open paths:

- required runner setup, fresh admission, raw Android evidence, and semantic
  ResidualRisk could be absent while the synthetic happy path still returned
  `Supported`;
- six review identities could cyclically reuse the other lanes' production
  identities because disjointness was checked only per lane; and
- a second valid ExecutionRecord could exist beneath the formal root while
  self-reported counts still claimed one attempt and zero retries.

Validator v2 closes those paths:

- all required runner/raw/domain files now have exact portable names, real byte
  bindings, semantic validation, and exhaustive lane-ledger coverage;
- every production and review Codex receipt binds its session/turn observation,
  default-model command, effective model, and clean context, followed by global
  set disjointness; and
- reconciliation scans every JSON/ExecutionRecord-shaped artifact under the
  whole formal-attempt root, requires exactly the six canonical paths and six
  distinct attempt IDs, and makes the persisted inventory match those bytes.

The second Spec review reproduced two further fail-open classes in the same
unapproved tree:

- the clean-review context hashes were accepted without scanning the actual
  reviewer-facing artifact bytes, so expected-result language injected into a
  Finding or Project Risk Map could still qualify; and
- an empty execution-provenance object and non-evidentiary review artifacts
  could still reach the Supported reducer.

Those paths are closed by an exact allowlisted review-input directory whose
files must be byte-equal to the source evidence, a canonical role-blind
ExecutionRecord projection, whole-file role/expected-result leakage scanning,
the authoritative execution-provenance verifier, and a structured review
contract. The review prompt, invocation ledger, JSONL lifecycle events,
six-dimension output, evidence references, invocation/context identities, and
final agent message must all agree. A post-seal challenge to any structured
review artifact now produces terminal `Not Supported`.

The third sealed tree
`61d8a9484f50f61395e0f56925330b3ec1e9e65b` received Standards PASS and
Spec FAIL before approval. The Spec reviewer found one P1 executability gap:
the review ran from `review-input/` but received repository-relative paths and
no exact output schema or dimension identifiers, while the model output was
required to contain thread/turn IDs and artifact checksums that exist only
after the invocation. The synthetic fixture could construct that state, but a
real R4 consumer could not.

The current producer/validator contract closes that gap:

- `prepare_falsification_review_invocation` creates an exact
  workspace-relative prompt, JSON Schema, and invocation ledger in a fresh
  append-only namespace;
- the prompt includes every semantic field, the six dimension identifiers and
  their order, allowed evidence references, outcome consistency rules, and the
  exact local claim boundary;
- `execute_falsification_review` passes the prompt as the final Codex argument,
  performs exactly one read-only default-model invocation, captures its event
  stream and authoritative session/turn identity through the existing runner
  identity seam, and explicitly forbids retry after any failure;
- the model output contains semantic review content only; the runner creates a
  separate schema-v2 receipt envelope containing lane/finding identity,
  thread/turn identity, effective model, and all prompt/schema/context/output/
  event/invocation checksums; and
- an injected `CommandRunner` integration regression exercises the real
  preparation, command, output-schema, event, identity, and receipt boundary
  without invoking a device or external model. It proves one review command,
  one identity observation, and an append-only terminal receipt.

The fourth sealed tree
`bbe65aea917440f8d92decbdddc21491dcf995e8` received Spec PASS and
Standards FAIL before approval. The Standards reviewer found two remaining P1
one-shot accounting gaps:

- a caller-supplied production invocation ID and identity digest were not
  validated against the lane's effective production identity until after the
  only permitted review invocation; and
- nonzero exit, timeout, missing output, identity-capture failure, or final
  binding failure raised an exception after consuming the namespace but did
  not leave durable terminal evidence containing the stage, return code, and
  standard streams.

The current executor closes both gaps before any approval or formal execution:

- it loads and semantically validates the lane's checksum-bound
  `effective-execution-identity.json`, then requires both caller values to
  match its authoritative top-level production invocation and parsed
  invocation set before writing the prompt, schema, or invocation ledger;
- after the runner boundary has been called, every terminal failure creates
  `falsification-review.json` exclusively, with a schema-v2 terminal
  no-retry/no-replacement envelope, validated production binding, exact
  command identity, timeout, return code, stdout/stderr and hashes, UTC start
  and finish timestamps, failure stage/reason, and hashes for every artifact
  that exists;
- runner exceptions, command mismatch, process exit, timeout, event-stream
  persistence, missing semantic output, identity capture, and final binding
  have distinct frozen stages; the receipt is required to enter the
  exhaustive lane `checksums.sha256` ledger; and
- regressions prove that wrong production IDs or hashes cause zero writes and
  zero runner calls, while nonzero, timeout, missing-output, identity-capture,
  and final-binding failures each call the review producer once, preserve the
  terminal receipt, and reject a second call before it reaches the runner.

- The denominator-external contradiction audit is checksum-bound and requires
  its exact packet ID, missing fields, rejection boundary, false denominator,
  empty command list, and false side effects.
- The merged-R2 base tree is searched directly for the new project, behavior,
  and exact commits. The zero-match command/result is stored in
  `freshness-audit.json` and linked from provenance.
- Both external APKs are inspected with `apkanalyzer`; package, launcher,
  command outputs, tool identity, and internally consistent output hashes are
  recorded in `apk-identity.json`.
- External APK and package archive paths, sizes, hashes, reproducibility, and
  reason for remaining outside the repository are explicit in the run record.
- Finding conclusion values now match the frozen oracle vocabulary:
  `locally_supported`, `locally_rejected`, or `inconclusive`.

## Regression evidence

- `tests/bench/test_m9_recovery_qualification.py` covers forged approval,
  frozen-regeneration attempts, deleted/recommitted packet sections, unbalanced
  mappings, admission namespace/tool drift, duplicate or reused review
  identities, cyclic cross-lane review/production reuse, explicit-model event
  forgery, retry evidence, a second hidden ExecutionRecord, minimal
  contradiction assertions, missing runner/admission/raw evidence, incomplete
  admission/provenance, signature-only PNGs, empty ResidualRisk, hidden
  `.bak` records, explicit model/config/profile overrides, resumed reviews,
  reviewer-facing role or expected-result leakage, non-allowlisted review
  files, challenged structured reviews, and missing/tampered on-disk Attempt
  Evidence. It also covers semantic-only review output, workspace-relative
  prompts, schema enforcement, runtime metadata separation, fresh namespaces,
  and the injected one-shot producer boundary. It also covers production
  identity/hash rejection before side effects and checksum-ready terminal
  receipts for all five reproduced post-attempt failure paths.
- Focused set: 195 passed, 0 failed.
- Full repository: 986 passed, 0 failed.
- Package: wheel and sdist both contain the recovery qualification module and
  production admission seam.

Final independent Standards and Spec verdicts are recorded separately in
`standards-review.md` and `spec-review.md`; both are PASS.
