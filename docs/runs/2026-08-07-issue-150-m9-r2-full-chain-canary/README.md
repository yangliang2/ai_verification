# M9-R2 non-holdout full-chain recovery canary

Status: attempt 04 completed the runtime chain, but independent Spec review
invalidated its two Falsification Reviews because reviewer-visible bytes
disclosed the historical defect source. Its emitted `ready_for_r3=true` is
therefore rejected. The attempt remains immutable evidence; bounded
remediation and fresh attempt 05 are in progress.

The run is explicitly `non_holdout_canary=true`,
`formal_qualification_eligible=false`, and `formal_denominator=false`. It does
not change the immutable #137 `Not Supported` aggregate, qualify a fresh
cohort, or support M9 `Supported`.

## Outcome

Attempt 04 traversed the complete production-seam runtime chain on the exact
#148 historical control/defect pair:

- both lanes reset the package, froze the English-US input subtype, installed
  the exact APK with Android CLI, launched the explicit activity, passed the
  live-validation gate, ran the Codex CLI Verification Agent Backend, captured
  Android layout/screenshot/logcat evidence, completed the L1/L2/L3 oracle
  path, and emitted accountable terminal `ExecutionRecord`s;
- all 24 required chain checks passed: 12/12 for the control and 12/12 for the
  defect;
- the control finding was rejected and the defect finding was supported;
- both separately invoked reviewers returned `survived`, but those responses
  are not valid clean-context reviews because the allowlisted fixture receipt
  leaked the historical source assignment;
- the attempt-local reconciliation reported 2/2 accountable lanes, 1/1
  expected control rejection, 1/1 expected defect support, and 2/2 surviving
  reviews, but independent review rejects that readiness result;
- the contradiction packet was rejected before any build, device, agent, or
  runtime command, with zero side effects and no denominator membership.

The invalidated attempt-local aggregate is
[`attempts/attempt-04/canary-reconciliation.json`](attempts/attempt-04/canary-reconciliation.json).
The one-invocation execution result is
[`attempts/attempt-04/canary-execution-summary.json`](attempts/attempt-04/canary-execution-summary.json).

### Independent review invalidation

The Spec reviewer found that `neutral-fixture-binding.json` exposed the
historical `/defect` input path and commit subject. Both Codex review event
ledgers show that the receipt was actually opened. The pre-review audit scanned
only prompt/context strings, not the referenced artifact bytes, and therefore
produced a false-negative leakage result.

Attempt 04 cannot establish R2 readiness. The remediation creates a dedicated
review workspace, replaces full source provenance with a role-blind derivative,
scans every allowlisted file byte-for-byte for historical identities and
assignments, binds every reconciliation to exact terminal/review receipts, and
uses a fresh R2-owned contradiction packet. A complete fresh attempt 05,
including runtime, reviews, and reconciliation, is required.

## Attempt inventory

All attempts are create-only, numbered, preserved, non-formal, and excluded
from every formal denominator. No attempt was retried or replaced in place.

| Attempt | Wall time | Terminal result | First observed failure or outcome |
|---|---:|---|---|
| 01 | 909.89s | failure | The control driver hit its 900.14s bound while repeatedly correcting Compose text entry. The subsequent dirty defect target was independently rejected by admission before side effects. |
| 02 | 447.87s | failure | The control could not bind the transient Android tool-version receipt; the defect then exposed a Chinese-IME/save-overlay journey failure; review schema admission also rejected an invalid JSON Schema. |
| schema smoke | 27.30s | pass, transport only | Codex default `gpt-5.6-sol` accepted the corrected schema and returned six conforming dimensions. This was not a lane review or oracle input. |
| 03 | 1043.30s | failure | Both runtime lanes completed accountably, but the control review cited a context file outside its allowlist. The rejected review also exposed missing peer semantic/provenance context. |
| 04 | 1364.275s | runtime pass, review invalid | Two accountable runtime lanes and expected observed behavior; reviewer inputs were role-contaminated, so independent review rejects `ready_for_r3=true`. |
| 05 | pending | pending | Fresh full-chain remediation attempt; no prior attempt is resumed or overwritten. |

The bounded remediations were limited to future attempts: use a clean defect
commit with the recovered tree, bound text replacement after the first
failure, freeze and receipt English-US input, validate the review schema before
invocation, package complete peer semantics/provenance, and bind every review
reference to the clean-context allowlist. Prior attempts and their receipts
were never rewritten.

Artifact inventories and ledgers:

| Scope | Files including ledger | Bytes | Ledger entries |
|---|---:|---:|---:|
| attempt 01 | 23 | 175,862 | 20/20 |
| attempt 02 | 61 | 2,491,100 | 58/58 |
| review schema smoke | 7 | 7,491 | 6/6 |
| attempt 03 | 112 | 12,275,134 | 109/109 |
| attempt 04 | 171 | 19,173,187 | 168/168 |

## Successful full-chain execution

Exact command:

```text
/usr/bin/time -p uv run python -m aiverify.bench.m9_recovery_canary \
  --artifact-root docs/runs/2026-08-07-issue-150-m9-r2-full-chain-canary/attempts/attempt-04 \
  --fixture-root /private/tmp/m9-r2-canary-fixtures/attempt-04 \
  --first-input /private/tmp/m9-r1-canary-recovery/control \
  --second-input /private/tmp/m9-r1-canary-recovery/defect \
  --device emulator-5554
```

Result:

```text
{"accountable": 2, "canary_result": "ready_for_fresh_qualification_packet", "ready_for_r3": true}
real 1364.38
user 143.95
sys 18.56
```

The structured invocation duration is 1364.275 seconds. There were zero
troubleshooting retries and zero replacements in that invocation.

### Control lane

`m9-r2-canary-alpha` used clean source commit
`ee66e1526b84c026615df032c705842b7d2a521f`, tree
`19455e693ec8c96c37a56aec55059a220826c5a3`, and the 24,681,606-byte APK
whose source and installed-device SHA-256 were both
`d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66`.

All five agent actions passed. The process changed from PID 7015 to PID 7793
across the forced lifecycle event. L2 and L3 passed, the finding was rejected,
and the final reopened task retained token `r2a1` and description `adesc`.
Total lane time was 388.279 seconds; execution time was 388.133 seconds.

### Defect lane

`m9-r2-canary-beta` used clean historical defect commit
`208575f78d59716669d0733b5ed3e08797b08787`, recovered tree
`34998af23aed59aa17eaf915d848ab1b916a63e2`, and the 24,681,461-byte APK
whose source and installed-device SHA-256 were both
`61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac`.
The recovered input audit retains option-A patch SHA-256
`cc317d74012a83ab6a2e400fbc7442dfcb3bec8464fdbf68a1ba1cdc7974b277`.

All five agent actions passed. The process changed from PID 8111 to PID 8794
across the forced lifecycle event. L2 passed, L3 detected `state_loss`, the
finding was supported, and the final reopened task reverted to token `r2b0`
and description `bdesc`. Total lane time was 355.053 seconds; execution time
was 354.896 seconds.

### Agent and review identity

Every journey driver, L3 judge, and falsification reviewer requested no model
override and selected the Codex CLI default. All six invocations recorded:

```text
requested_model: null
selection_policy: codex_cli_default
model_override_present: false
effective_model: gpt-5.6-sol
codex_version: codex-cli 0.144.6
```

There are six durable identity/invocation receipt pairs with six unique
production invocation IDs. Each falsification reviewer ran separately from
the production roles. Both attempt-local review-input audits record
`mapping_persisted=false`, `known_role_disclosed=false`,
`expected_outcome_disclosed=false`, and an empty forbidden-disclosure list.
Those audit claims are false negatives because they did not inspect referenced
artifact bytes. The auditor mapping was withheld until both reviews completed,
but the fixture receipt independently disclosed the assignment.

Each review returned `outcome=survived`; all six dimensions were supported and
the reason list was empty. These responses are preserved but invalid for R2.
Review briefs, contexts, peer evidence, prompts, events, native identities, and
reconciliations are inside each attempt-04 lane directory.

## Contradiction rejection

Attempt 04 read the immutable #136 contradiction packet as a negative admission
canary. Although it was rejected before any build, device, agent, or runtime
side effect, independent Spec review correctly found that reuse inconsistent
with the declaration that the old population was not invoked.
[`attempts/attempt-04/contradiction-rejection.json`](attempts/attempt-04/contradiction-rejection.json)
records an empty command list, `side_effects=false`, and
`denominator_member=false`. Attempt 05 must instead create and reject its own
fresh R2 packet; it does not read #136/#137.

## Verification

Focused final-state regression:

```text
/usr/bin/time -p uv run pytest -q -o addopts='' \
  tests/bench/test_m9_recovery_canary.py \
  tests/discovery/test_falsification_review.py \
  tests/runner/test_admission.py \
  tests/runner/test_codex_backend.py \
  tests/test_codex_cli_provider.py \
  tests/runner/test_cli.py
→ 91 passed, 0 failed in 1.88s.
→ real 1.98s; user 1.03s; sys 0.79s.
```

Full suite:

```text
/usr/bin/time -p uv run pytest
→ 906 passed, 0 failed in 65.48s.
→ real 65.65s; user 25.33s; sys 6.39s.
```

Static/source checks:

```text
uv run python -m py_compile \
  src/aiverify/bench/m9_recovery_canary.py \
  src/aiverify/discovery/falsification_review.py \
  src/aiverify/providers/codex_cli.py \
  src/aiverify/runner/admission.py \
  src/aiverify/runner/codex_identity.py \
  src/aiverify/runner/execution_identity.py
→ passed.

git diff --check origin/main...HEAD -- bench src tests pyproject.toml
→ passed.
```

The full unscoped diff whitespace check reports trailing spaces emitted by
Android in committed raw `logcat.txt` captures. Those source-faithful evidence
bytes are checksum-bound and were not normalized. No authored source, test,
specification, or package file failed the scoped check.

Package build:

```text
/usr/bin/time -p uv build --out-dir /private/tmp/m9-r2-build.9OQxQD
→ aiverify 0.1.0 built successfully.
→ real 3.07s; user 0.65s; sys 0.24s.
```

The 410,480-byte wheel SHA-256 is
`8ddfed9769b4f4bdfcdcadd6e545ffed3286d606858b65a828a0063380b5cea4`;
the 373,502-byte sdist SHA-256 is
`909baf7652cf513d466073ea2d30c7ee0030a3120bb1283d6418e6c3cec2d879`.
Both archives contain the new runner and falsification-review schema. Exact
structured results are in [`verification.json`](verification.json) and
[`package-build.json`](package-build.json).

## Implementation and tests

- `src/aiverify/bench/m9_recovery_canary.py` implements create-only attempts,
  neutral fixture binding, contradiction admission, full-chain lane execution,
  blind paired review, reconciliation, and checksums.
- `src/aiverify/bench/m9_falsification_review_schema.json` defines the strict
  six-dimension reviewer response.
- `src/aiverify/providers/codex_cli.py` gives each production/review role a
  separate, schema-capable invocation and durable identity artifacts.
- `src/aiverify/runner/admission.py`,
  `src/aiverify/runner/codex_identity.py`, and
  `src/aiverify/runner/execution_identity.py` represent a null requested model
  as `codex_cli_default` and reject any contradictory hidden `--model`.
- `src/aiverify/discovery/falsification_review.py` validates clean-context
  review identity, evidence references, disclosure exclusions, and
  reconciliation.
- `tests/bench/test_m9_recovery_canary.py` covers the canary boundary, fixture
  identity, blind review release, full-chain reconciliation, and fail-closed
  paths.
- provider, admission, runner, CLI, and discovery tests cover default-model
  identity, schema transport, role separation, and compatibility.
- `bench/m9/recovery-canary/` contains the neutral alpha/beta run specs; the
  canary role is not encoded in reviewer-visible content.

## Environment and artifact inventory

The successful run used `emulator-5554`, AVD `aiverify_api35`, API 35, model
`sdk_gphone64_arm64`, and fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
The package was
`com.example.android.architecture.blueprints.main` and the explicit activity
was
`com.example.android.architecture.blueprints.todoapp.TodoActivity`.

Relevant tools:

- Android CLI `1.0.15498356`;
- ADB `1.0.41`, platform tools `37.0.0-14910828`;
- Codex CLI `0.144.6`, effective default model `gpt-5.6-sol`;
- Git `2.50.1 (Apple Git-155)`;
- uv `0.11.7`;
- uv-managed Python `3.11.15`.

The committed run tree includes every numbered attempt, exact run
declarations, source and package admission, package reset, input-method setup,
Android deployment/launch provenance, driver prompts/events/results, raw
layouts/screenshots/logcats/commands, L3 prompts/events/results, terminal
records, findings, blind-review inputs/audits/prompts/events/results, auditor
mapping release, reconciliation, failure receipts, and nested checksum
ledgers.

Manual verification: both successful final screenshots and their
corresponding layouts were visually inspected for coherent control retention
and defect reversion. The successful captured logcats were checked for fatal
exceptions and ANRs; none were found.

External artifacts:

- `/private/tmp/m9-r1-canary-recovery/control` and
  `/private/tmp/m9-r1-canary-recovery/defect`;
- `/private/tmp/m9-r2-canary-fixtures/attempt-04/`;
- `/private/tmp/m9-r2-build.9OQxQD/`.

The first two paths are historical canary inputs or disposable detached
worktrees, and the build directory contains reproducible package outputs.
Their exact identities and checksums are committed, but they are not claimed
as durable fresh-cohort or formal qualification evidence.

## Worktree and sequencing

R2 began in independent clean worktree
`/Users/peter/projects/ai_verification-m9-r2` at fixed point
`76fb6730f065e6e4087ae0032e3edb780104807e`, the then-current merged
`origin/main` containing #148. The merge base remained that exact commit
through final verification. The original dirty
`/Users/peter/projects/ai_verfication` `issue-73-accessibility-slice`
worktree was not modified.

#136 and #137 were not reopened, rerun, copied into a new denominator, or
rewritten. Their artifacts, checksums, mapping, lane attempts, and `Not
Supported` conclusion remain immutable. The #148 historical pair is exhausted
after R2 and is forbidden from R3, R4, R5, or any future formal conclusion.

## Known gaps and claim boundary

- The canary used one historical matched pair on one local API-35 emulator. It
  establishes chain executability, not a defect rate, completeness rate,
  generalization, production behavior, OEM behavior, ColorOS behavior, or
  upstream behavior.
- The successful lane evidence does not qualify a fresh cohort and may not
  enter a formal denominator.
- The external build archives and canary fixture worktrees are reproducible
  but disposable.
- Raw Android logcat captures preserve device-emitted trailing whitespace.
- R3 must prepare a genuinely fresh hidden 3-control/3-defect packet without
  executing it, record its freeze identities, merge that evidence, and then
  pause for explicit human freeze approval.

R2 supports only that the complete recovery chain is executable and internally
consistent on the recorded historical matched pair and local API-35/Codex
environment. It does not change #137 or support M9 `Supported`.
