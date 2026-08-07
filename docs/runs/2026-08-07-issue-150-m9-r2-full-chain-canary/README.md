# M9-R2 non-holdout full-chain recovery canary

Status: attempts 04 and 05 are preserved, immutable, and non-ready. Independent
Spec review invalidated attempt 04 because reviewer-visible bytes disclosed
the historical defect source. Attempt 05 fixed that isolation and completed
both accountable runtime lanes, but both clean-context reviewers challenged
the evidence contract. Its `ready_for_r3=false` result is authoritative.
Attempt 06 then failed non-accountably during static Android CLI identity
capture and is also sealed. Attempt 07 completed both accountable lanes but a
conflicting global keyboard rule discarded the control edit before Save; its
reviewers correctly challenged both lanes. A conditional-save correction is
committed before fresh attempt 08.

The run is explicitly `non_holdout_canary=true`,
`formal_qualification_eligible=false`, and `formal_denominator=false`. It does
not change the immutable #137 `Not Supported` aggregate, qualify a fresh
cohort, or support M9 `Supported`.

## Outcome

Attempt 05 traversed the complete production-seam runtime chain on the exact
#148 historical control/defect pair and correctly blocked progression:

- both lanes reset the package, froze the English-US input subtype, installed
  the exact APK with Android CLI, launched the explicit activity, passed the
  live-validation gate, ran the Codex CLI Verification Agent Backend, captured
  Android layout/screenshot/logcat evidence, completed the L1/L2/L3 oracle
  path, and emitted accountable terminal `ExecutionRecord`s;
- all 24 required chain checks passed: 12/12 for the control and 12/12 for the
  defect;
- the control finding was rejected and the defect finding was supported;
- both 39-file reviewer workspaces passed the byte-level allowlist audit with
  no historical source identity, role assignment, expected result, or #136
  packet disclosure;
- both separately invoked clean-context reviewers returned `challenged`, so
  the attempt-local reconciliation reported 0/2 surviving reviews and
  `ready_for_r3=false`;
- the contradiction packet was rejected before any build, device, agent, or
  runtime command, with zero side effects and no denominator membership.

The authoritative blocked reconciliation is
[`attempts/attempt-05/canary-reconciliation.json`](attempts/attempt-05/canary-reconciliation.json).
The one-invocation execution result is
[`attempts/attempt-05/canary-execution-summary.json`](attempts/attempt-05/canary-execution-summary.json).

### Attempt 05 diagnosis and bounded remediation

The control review identified an exact-source contradiction:
`review-execution-provenance.json` reported
`source_and_installed_apk_match=false` even though the full provenance recorded
the same source and installed APK SHA-256. The role-blind derivative read
`apk.sha256`, while the captured schema stores APKs under
`apk.artifacts[].sha256`.

The defect review found the same false exact-source signal and a separate
causal-evidence gap. The only runner checkpoints were after reopening and
after process death, so no admitted raw checkpoint proved that the edited
title was visible before Save. It could not distinguish the bounded behavioral
claim from missed edit/save or attribute the already-observed reversion to the
later process event.

Attempt 05 was not modified or re-reviewed. Future-only remediation:

- compares the full source and installed APK artifact sets and emits
  role-blind admission, clean-worktree, Run-Spec binding, and exact-byte-match
  booleans without source hashes or roles;
- splits edit and Save into separate actions with non-mutating observation
  boundaries, producing raw pre-save, post-save, reopened, and post-process
  checkpoints;
- narrows the risk to the accepted save path retaining the edited title; it
  does not claim an internal repository mechanism or claim that process death
  caused an earlier reversion.

The structured diagnosis is
[`attempt-05-diagnosis.json`](attempt-05-diagnosis.json).

### Attempt 04 independent review invalidation

The Spec reviewer found that `neutral-fixture-binding.json` exposed the
historical `/defect` input path and commit subject. Both Codex review event
ledgers show that the receipt was actually opened. The pre-review audit scanned
only prompt/context strings, not the referenced artifact bytes, and therefore
produced a false-negative leakage result.

Attempt 04 cannot establish R2 readiness. The remediation created a dedicated
review workspace, replaces full source provenance with a role-blind derivative,
scans every allowlisted file byte-for-byte for historical identities and
assignments, binds every reconciliation to exact terminal/review receipts, and
uses a fresh R2-owned contradiction packet. Attempt 05 verifies those isolation
properties but remains non-ready for the independent reasons above.

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
| 05 | 1487.582s | blocked | Two accountable lanes and expected runtime behavior, but both clean-context reviews challenged: the role-blind derivative emitted a false APK mismatch, and the defect lane lacked a raw pre-save checkpoint. |
| 06 | 31.10s | failure | Android CLI printed version `1.0.15498356` but did not exit within the 30-second identity bound; the lane was non-accountable. A secondary packaging path then obscured that reason by requiring absent execution provenance. |
| 07 | 1615.359s | blocked | Both lanes were accountable and all 24 chain checks passed, but the unconditional pre-Save Back rule discarded the control edit. Control and defect both appeared supported; both independent reviews challenged the protocol divergence. |
| 08 | pending | pending | Fresh future-only conditional-save attempt; no prior attempt is resumed, rewritten, or re-reviewed. |

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
| attempt 05 | 202 | 21,350,210 | 199/199 root; 96/96 per lane |
| attempt 06 | 15 | 17,785 | 13/13 root; 9/9 control lane |
| attempt 07 | 374 | 71,612,972 | 371/371 root; 182/182 per lane |

## Protocol-divergent full-chain execution (attempt 07)

Attempt 07 completed one invocation in 1615.359 seconds (wall 1615.54s; user
197.04s; sys 24.66s) with zero troubleshooting retries and zero replacements.
Both lanes were accountable and passed all 12/12 required chain checks.

The new raw evidence boundaries worked: before Save, alpha checkpoints showed
`r2a1` and beta checkpoints showed `r2b1` on Edit Task, with Save untouched.
However, the shared driver prefix still said to press Back before every Save.
At the isolated control Save segment, Back left Edit Task, discarded `r2a1`,
and the driver reopened the editor and saved `r2a0`. The control therefore
failed L3 and emitted a supported finding. The defect driver also left Edit
Task, but restored `r2b1` before Save; its post-save checkpoint correctly
showed `r2b0`.

Both clean-context reviewers challenged. Alpha used typed reasons including
`UNSAVED_EDIT_DISCARDED_BEFORE_SAVE`,
`SAVE_PATH_NOT_TESTED_WITH_EDITED_VALUE`, and
`CONTROL_PROTOCOL_DIVERGENCE`. Beta independently found the paired comparison
invalid because the control did not save its edited value.

This attempt confirms the earlier isolation remediation: both reviewer
workspaces scanned exactly 75/75 allowlisted files with zero forbidden
disclosures, and both role-blind provenance receipts record source admission,
clean worktree, Run-Spec binding, and source/installed APK equality as true.

Future-only remediation makes keyboard dismissal conditional. An isolated
Save action must not press Back, reopen, or re-enter text; it must observe the
expected edited token and tap Save once, or fail without repair. See
[`attempt-07-diagnosis.json`](attempt-07-diagnosis.json).

## Early identity failure (attempt 06)

Exact command:

```text
/usr/bin/time -p uv run python -m aiverify.bench.m9_recovery_canary \
  --artifact-root docs/runs/2026-08-07-issue-150-m9-r2-full-chain-canary/attempts/attempt-06 \
  --fixture-root /private/tmp/m9-r2-canary-fixtures/attempt-06 \
  --first-input /private/tmp/m9-r1-canary-recovery/control \
  --second-input /private/tmp/m9-r1-canary-recovery/defect \
  --device emulator-5554
```

The control lane terminated during `execution-identity-capture` after 30.444
seconds. Android CLI emitted the expected version but timed out with return
code 124, so the runner correctly classified execution as non-accountable.
The R2 wrapper then attempted to derive reviewer provenance that could not
exist for an identity-stage failure, producing a secondary `FileNotFoundError`.
The root terminal receipt records `ready_for_r3=false` and
`rerun_of_this_attempt_permitted=false`.

Future-only remediation leaves strict identity admission unchanged and stops a
non-accountable lane before reviewer-evidence packaging, preserving the
original terminal reason. The structured diagnosis is
[`attempt-06-diagnosis.json`](attempt-06-diagnosis.json).

## Blocked full-chain execution (attempt 05)

Exact command:

```text
/usr/bin/time -p uv run python -m aiverify.bench.m9_recovery_canary \
  --artifact-root docs/runs/2026-08-07-issue-150-m9-r2-full-chain-canary/attempts/attempt-05 \
  --fixture-root /private/tmp/m9-r2-canary-fixtures/attempt-05 \
  --first-input /private/tmp/m9-r1-canary-recovery/control \
  --second-input /private/tmp/m9-r1-canary-recovery/defect \
  --device emulator-5554
```

Result:

```text
{"accountable": 2, "canary_result": "blocked_by_canary_evidence", "ready_for_r3": false}
exit 2
real 1487.76
user 125.41
sys 19.07
```

The structured duration is 1487.582 seconds. There were zero troubleshooting
retries and zero replacements. Both lane and root checksum ledgers pass when
verified from their owning directories. Root ledger SHA-256:
`db5c94c2fe94f7c789537185312619a00eeeaa743e46cb19135e120d7bf7d2ef`.

## Invalidated full-chain execution (attempt 04)

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
`denominator_member=false`. Attempt 05 instead created and rejected its own
fresh R2 packet; it did not read #136/#137. The packet SHA-256 is
`bbb01f576c0c90ccd6bc015df88166454021401f359bc27a284f8b6aac51e8fd`;
the rejection receipt SHA-256 is
`294369ed318ae08d33c4b01fc7f94a9d846e3d579bb807f780f72b53a002fc97`.

## Verification

Focused post-attempt-07 conditional-save regression:

```text
/usr/bin/time -p uv run pytest -q -o addopts='' \
  tests/bench/test_m9_recovery_canary.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_journey.py
→ 71 passed, 0 failed in 0.15s.
→ real 0.27s; user 0.17s; sys 0.05s.
```

Full suite:

```text
/usr/bin/time -p uv run pytest -qq --disable-warnings
→ 917 passed, 0 failed.
→ real 30.74s; user 22.30s; sys 5.06s.
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

Checkpoint package build (before the attempt-06 fail-closed wrapper change;
final rebuild pending):

```text
/usr/bin/time -p uv build --out-dir /private/tmp/m9-r2-build.buror6
→ aiverify 0.1.0 built successfully.
→ real 3.07s; user 0.63s; sys 0.23s.
```

The 413,139-byte wheel SHA-256 is
`24ffdbbacbcd7691b50d9c5660fdc7053bcf5123449699bc27491360dd09767a`;
the 376,193-byte sdist SHA-256 is
`640dea5d9698f37f562108a0e5802b5b03eae0d3b38e5ca0701edecd529583fb`.
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

The accountable runs used `emulator-5554`, AVD `aiverify_api35`, API 35, model
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
- `/private/tmp/m9-r2-canary-fixtures/attempt-05/`;
- `/private/tmp/m9-r2-canary-fixtures/attempt-06/`;
- `/private/tmp/m9-r2-canary-fixtures/attempt-07/`;
- `/private/tmp/m9-r2-build.buror6/`.

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
- Attempt 05 is authoritative non-ready evidence. Its reviews were not rerun,
  and its artifacts were not rewritten after diagnosis.
- Attempt 06 is an authoritative non-accountable failure. It was not rerun or
  replaced; its future-only correction affects attempt 07.
- Attempt 07 is authoritative non-ready evidence. It was not rerun, repaired,
  or re-reviewed; its conditional-save correction affects attempt 08.
- The external build archives and canary fixture worktrees are reproducible
  but disposable.
- Raw Android logcat captures preserve device-emitted trailing whitespace.
- R3 must prepare a genuinely fresh hidden 3-control/3-defect packet without
  executing it, record its freeze identities, merge that evidence, and then
  pause for explicit human freeze approval.

R2 supports only that the complete recovery chain is executable and internally
consistent on the recorded historical matched pair and local API-35/Codex
environment. It does not change #137 or support M9 `Supported`.
