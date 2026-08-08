# M9-R3 #152 — fresh blinded 3+3 candidate freeze

Status: **technically admitted and dual-axis reviewed; awaiting explicit human
freeze approval**.

No formal lane, emulator action, Android deployment, Codex invocation, oracle,
Finding, Project Risk Map, or Falsification Review was executed in R3. The
stable approval-bound packet commitment is
`a2ae1d8ca4902a500c67aa6107a0f42fe06a3948ca484305861d2d2670033225`.
The mutable approval envelope and status timestamps are deliberately outside
that commitment. The manifest cannot be consumed by formal execution while its
status is `awaiting_human_approval`.

## Fresh candidate and ProjectTarget

The candidate is the Android-owned
[`android/compose-samples`](https://github.com/android/compose-samples) Jetchat
sample. It is absent from the repository's pre-R3 M9 inputs and differs from
the exhausted architecture-samples task-edit cohort in project, source path,
state primitive, UI flow, and lifecycle boundary.

- Source origin: `https://github.com/android/compose-samples.git`.
- Defect snapshot: `56b59e237b253bc52e2ce1141dce26af07503415`,
  tree `993432fb446913107df1bc0c040a05f8dae1c5b2`.
- Control snapshot:
  `038c8208307508ceedcb5dd07a4fe2794017644c`, tree
  `e658ec4cdbb25d8e75a04879e9e20a0c245832e9`.
- Upstream evidence: [PR #996](https://github.com/android/compose-samples/pull/996),
  merged 2022-10-24. The control is the merge commit and the defect is its
  first parent.
- Focused first-parent diff: one file,
  `Jetchat/app/src/main/java/com/example/compose/jetchat/conversation/UserInput.kt`;
  `remember { mutableStateOf(TextFieldValue()) }` becomes
  `rememberSaveable(stateSaver = TextFieldValue.Saver)`.
- License: Apache-2.0; committed `LICENSE` SHA-256
  `0a3428546fa34277a64d60b372f74f880a1aa9a30b6c96ac76d30740b6ad9326`.
- Application: package `com.example.compose.jetchat`, launcher
  `com.example.compose.jetchat.NavActivity`, min/target/compile SDK 21/33/33.
- APK locator:
  `Jetchat/app/build/outputs/apk/debug/app-debug.apk`.

The upstream report reproduces loss of unsent text during a multi-window
resize. The frozen formal probe uses a portrait-to-landscape rotation because
the manifest declares no `configChanges`, so the controlled event exercises
the same activity recreation/save-restore mechanism. This is an
evidence-grounded inference, not a claim that R3 replayed the upstream UI
gesture. R3 performed no runtime check.

Auditor-only provenance and the focused patch are
`auditor/candidate-provenance.json` and `auditor/matched-pair.patch`.
`freshness-audit.json` records the exact base-tree search:

```text
git grep -n -E \
  'compose-samples|Jetchat|56b59e237b253bc52e2ce1141dce26af07503415|038c8208307508ceedcb5dd07a4fe2794017644c|m9-unsent-draft' \
  099cf64228273ef67bd23c6bad4af6239e580aa1 -- .
→ exit 1, empty stdout/stderr, zero matched paths.
```

That immutable-base search covers the repository state containing merged R2,
including #136/#137 and R1/R2 inputs and artifacts.

## Host-only buildability

Both exact clean source worktrees built with:

```text
./gradlew --no-daemon --no-configuration-cache --max-workers=1 \
  :app:assembleDebug
```

The command ran from each snapshot's `Jetchat/` directory.

- Snapshot A: `BUILD SUCCESSFUL`; 32 actionable tasks, all executed;
  real 621.84s. APK 17,511,239 bytes, SHA-256
  `41d7c3ff47f2f2d2a04942d11ab57c6c76ac7314ff6abf8dad14fd9b3149e55b`.
- Snapshot B: `BUILD SUCCESSFUL`; 32 actionable tasks, 15 executed and 17
  from cache; real 25.50s. APK 17,511,449 bytes, SHA-256
  `a1536cec09a33063f7796dc77e0effdf1847a3ad325dcef707216fa87d78386d`.

`apkanalyzer manifest application-id` and `apkanalyzer manifest print`
independently verified both built APKs as package
`com.example.compose.jetchat` with sole launcher
`com.example.compose.jetchat.NavActivity`. Exact commands, stored output,
output hashes, resolved tool path/hash, and return codes are in
`apk-identity.json`.

The APKs remain outside the repository because they are large, reproducible
host build outputs—not R3 formal evidence:

- defect:
  `/private/tmp/m9-r3-snapshot-a/Jetchat/app/build/outputs/apk/debug/app-debug.apk`,
  17,511,239 bytes, SHA-256
  `41d7c3ff47f2f2d2a04942d11ab57c6c76ac7314ff6abf8dad14fd9b3149e55b`;
- control:
  `/private/tmp/m9-r3-snapshot-b/Jetchat/app/build/outputs/apk/debug/app-debug.apk`,
  17,511,449 bytes, SHA-256
  `a1536cec09a33063f7796dc77e0effdf1847a3ad325dcef707216fa87d78386d`.

The cold build downloaded Gradle 7.5.1 and installed the previously absent
host SDK Platform 33 and Build Tools 30.0.3 after confirming accepted licenses.
Those are disclosed host build-preparation side effects. Neither build
connected to or modified an emulator/device. Full logs are committed under
`build-logs/`. For repository whitespace hygiene, committed log and focused
patch text strips only trailing whitespace per line; `buildability.json` and
`candidate-provenance.json` retain the absolute external source path, raw
source hash, normalized hash, and normalization rule.

## Candidate qualification packet

The authoritative candidate manifest is
`bench/m9/m9-recovery-project-qualification-v2.json`.

- Population: exactly six lanes, three defect and three control.
- Design: three temporal blocks, each containing one lane of each hidden role.
- Lane order: `m9-r4-lane-01` through `m9-r4-lane-06`.
- Auditor mapping canonical SHA-256:
  `d69c0421ed68bf7de020326043fcf787250abbdb9aa0c9a10ecc3a2cc1eba8a4`;
  raw artifact SHA-256
  `4da963ad23e5e8aca18e79328069a23a62a3071eb814d929246675fc7f4b84eb`.
- Mapping release: only after fresh Context Acquisition, top-three Hypothesis
  Portfolio freeze, Attack Plan admission, and leakage audit. Clear roles are
  absent from verifier-facing packets and Run Specs.
- Final reconciliation must verify the released mapping's canonical commitment,
  exact lane order, three balanced blocks, and every lane-to-role assignment;
  post-outcome relabeling is rejected before aggregate counting.
- Each Run Spec uses a distinct neutral unsent-draft token. The driver types
  it exactly once, never taps Send, crosses one admitted rotation boundary,
  then only observes. It must not retype, repair, navigate, or reopen.
- Runner: API-35 `aiverify_api35` / `emulator-5554`, portrait precondition,
  landscape boundary, network disabled, idempotent package reset, Codex CLI
  default model selection (`requested_driver_model=null`,
  `requested_l3_model=null`).
- Live validation uses the pre-deployment environment gate. The app surface is
  verified only after identity-bound deployment by explicit launch and the
  first Journey checkpoint; an `app_smoke` declaration here would incorrectly
  require the fresh package to be installed before deployment.
- Formal accounting: exactly one R4 formal attempt; one terminal attempt per
  lane; zero retries, replacements, discretionary reruns, or denominator
  changes. Reconciliation exhaustively scans the whole formal-attempt root,
  requires exactly the six frozen ExecutionRecord paths and six distinct
  attempt IDs, and binds that inventory to both rows and the persisted
  formal-attempt inventory. A second record anywhere in the attempt root is
  terminal `Not Supported`, even if every self-reported count remains zero.
- Falsification Review: six clean-context, separately identified Codex CLI
  default-model invocations. The only admitted command shape is a fresh
  read-only `codex exec`; resume, explicit model/profile selection, and model
  configuration overrides are rejected. Production and review identities are
  validated from checksum-bound Codex session/turn event receipts; every
  invocation and identity digest is unique, and the complete review and
  production sets must be globally disjoint. Each review receives an exact
  allowlisted, byte-copied context plus a canonical semantic projection of the
  ExecutionRecord. Every file is scanned for role and expected-result leakage.
  The production `execute_falsification_review` boundary permits one invocation
  and no retry. Before creating that invocation's namespace, it binds the
  caller's production invocation ID and identity digest to the lane's parsed
  effective production identity. It passes a complete workspace-relative
  prompt as the final Codex argument, enforces a checksum-bound JSON Schema,
  captures authoritative JSONL/session identity, and writes the receipt
  envelope. Any attempted invocation that exits, times out, omits output,
  fails identity capture, or fails final binding leaves a checksum-ready
  terminal receipt with the command identity, return code, stdout/stderr,
  timestamps, failure stage, and explicit no-retry/no-replacement state. The
  model emits only the six-dimension semantic verdict; runtime IDs and
  checksums are runner-owned.
  Prompt, schema, invocation ledger, events, semantic output, identity, and
  receipt must all agree before `survived=true` can count. No production oracle
  implementation path is used, and the same-provider-family limitation is
  disclosed.
- Attempt Evidence: reconciliation reads real files beneath the clean R4
  repository root. It verifies an exhaustive lane ledger, persisted validation
  receipt, terminal authoritative ExecutionRecord, full execution provenance
  verified by the runner's production validator, fresh R4 production-seam
  admission, exact runner setup/launch order, authoritative production
  identity events, structurally complete before/after PNG and layout evidence,
  filtered logcat, the rotation receipt, token-bound oracle semantics, typed
  Finding and ResidualRisk contracts, a consistent Project Risk Map, the
  local-only claim boundary, and the bound Falsification Review identity,
  prompt, output schema, context, invocation, events, semantic output, and
  runner receipt before a lane can count.

The only `Supported` route is all of:

1. 6/6 terminal lanes accountable;
2. checksum-bound Attempt Evidence validation 6/6;
3. defect support 3/3;
4. control rejection 3/3;
5. Falsification Review survival 6/6 with unique policy-bound review and
   production identities;
6. the committed denominator-external contradiction audit rejected before
   side effects; and
7. one checksum-bound formal-attempt inventory proving one attempt, one
   terminal entry per lane, and zero retry, replacement, or discretionary
   rerun; and
8. exhaustive formal-root enumeration proving exactly six distinct
   ExecutionRecords and no hidden second attempt.

Any other outcome is `Not Supported` and remains terminal evidence.

Four unapproved sealed candidates failed review before any formal lane ran.
The first review reproduced three P1 fail-open paths: absent required
runner/raw/domain evidence, cyclic reuse between review and production
identities, and a hidden second ExecutionRecord outside the self-reported
inventory. The second review then reproduced six additional P1 classes:
explicit model selection through Codex configuration, resumed review sessions
qualifying as clean, a valid hidden `.bak` ExecutionRecord, incomplete
admission/provenance records, signature-only PNGs, and reviewer-facing bytes
that leaked expected results or supplied non-evidentiary review output. The
third seal's review then found that the Falsification Review prompt and
model-output contract were not executable: paths were repository-relative,
the prompt omitted the exact schema/dimension IDs, and the model was expected
to invent post-invocation IDs and checksums. The fourth seal passed Spec review,
but Standards review found that production identity binding occurred after the
single permitted call and that five terminal failure paths discarded their
process evidence after consuming the namespace. The current candidate
supersedes all four failed seals. It supplies the pre-invocation production
binding, one-shot executable producer boundary, CLI schema, semantic-only
output, runner-owned success receipt, and durable terminal failure receipt
described above. The validator and regressions reject every reproduced case.
Exact findings and closures are recorded in
`review-remediation.md`. The independent Standards and Spec verdicts are both
PASS and are recorded in `standards-review.md` and `spec-review.md`.

## Side-effect-free technical admission

`generate_freeze.py` materialized the candidate packet and invoked
`admit_production_seam` with a command runner that permits only read-only Git
identity calls.

Results:

- exact Run Specs serialized: 6/6;
- exact Run Spec/runner pairs admitted: 6/6;
- Git identity calls: 4 per lane, 24 total;
- external/build/device/agent admission side effects: false for all six;
- pre-release neutral packets: 6/6 passed;
- final neutral packets: 6/6 passed;
- serialized Run Spec role/source leakage checks: 6/6 passed;
- contradiction packet: passed rejection audit with zero command calls and
  no build/device/agent/runtime side effects;
- mapping released: false;
- human approval: pending;
- formal execution started: false.

The admission receipts contain auditor-side actual source identities and are
not verifier inputs.

R3 receipts are side-effect-free feasibility receipts, not reusable R4
execution authority: their absolute source/worktree roots are necessarily
local to this R3 worktree. Each receipt nevertheless binds the exact R4-relative
artifact namespace
`docs/runs/2026-08-07-m9-r4-formal-attempt-01/formal-artifacts/<lane-id>/`,
clean source identity, runner policy, default binaries, tool identities, model
selection, and absence of formal outputs. R4 must resolve only the fresh clean
worktree paths, reverify origin/commit/tree, and obtain six new side-effect-free
admissions; every non-path option remains immutable.

## Verification commands and results

Commands ran from the dedicated clean worktree
`/Users/peter/projects/ai_verification-m9-r3`, based on merged #151 commit
`099cf64228273ef67bd23c6bad4af6239e580aa1`.
`worktree-isolation.json` records that the original dirty
`/Users/peter/projects/ai_verfication` worktree retained the same branch, HEAD,
7,077-entry porcelain status hash, and tracked-patch hash before and after R3.

```text
uv run python -m py_compile \
  src/aiverify/bench/m9_recovery_qualification.py \
  tests/bench/test_m9_recovery_qualification.py \
  docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze/generate_freeze.py
→ exit 0.

/usr/bin/time -p uv run python -m pytest -o addopts='' -q \
  tests/bench/test_m9_recovery_qualification.py \
  tests/bench/test_m9_qualification.py \
  tests/runner/test_admission.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_system_events.py \
  tests/runner/test_execution_identity.py \
  tests/runner/test_codex_backend.py \
  tests/test_codex_cli_provider.py
→ 195 passed, 0 failed; real 17.78s, user 8.01s, sys 8.94s.

/usr/bin/time -p uv run python -m pytest -o addopts='' -q
→ 986 passed, 0 failed; real 55.78s, user 37.08s, sys 16.19s.

uv run python \
  docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze/generate_freeze.py
→ technical admission passed; 6 lanes; admissions pass; leakage pass;
  contradiction pass; formal_execution_started=false. The measured internal
  duration is recorded in `preflight.json`.

/usr/bin/time -p uv build --quiet \
  --out-dir /private/tmp/m9-r3-terminal-receipt-final.Ts7xD0
→ package aiverify 0.1.0 built; real 3.41s, user 0.76s, sys 0.32s.

(cd docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze &&
  shasum -a 256 -c checksums.sha256)
→ all final ledger entries passed.

git diff --cached --check
→ exit 0.
```

Package build artifacts are external and disposable, as in R2:

- wheel: 446,275 bytes, SHA-256
  `cb8dd881e988c058430a2407de33d0ef1a1a6db5644f8031f6e4cc8528077323`;
- sdist: 408,205 bytes, SHA-256
  `d55a8cd52b312d069ca38b666abaeba80a1a5057574ebd154df22e611d65da39`.

The wheel contains `aiverify/bench/m9_recovery_qualification.py` and the
production admission seam. Exact external paths and contents are recorded in
`package-build.json`.

Tool identity: CPython 3.11.15, pytest 9.1.1, uv 0.11.7, Git 2.50.1,
OpenJDK 17.0.19, Gradle 7.5.1,
Android CLI 1.0.15498356, adb 1.0.41 / platform 37.0.0-14910828, and Codex CLI
0.144.6. `tool-versions.json` records exact outputs and command-output hashes.
No device was accessed.

## Artifact inventory

- `candidate-decision-packet.json`, `preflight.json`, and
  `manifest-identity.json`: approval-bound packet and technical gate state.
- `admission/*.json` and `admission-audit.json`: six exact Git-only production
  seam admissions.
- `pre-release-*`, `final-*`, and `run-spec-leakage-audit.json`: blinded input
  audits.
- `contradiction-packet.json` and `contradiction-audit.json`: external packet
  rejection evidence.
- `freshness-audit.json`: exact zero-match search against merged-R2 base
  `099cf642...`.
- `worktree-isolation.json`: independent clean R3 worktree identity and
  before/after original dirty-worktree hashes.
- `apk-identity.json`: APK-level package and launcher inspection for both
  external build outputs.
- `source-context-inputs.json`, `operator-registry.json`, and
  `attack-plan-contract.json`: frozen discovery/planning inputs.
- `auditor/`: upstream pair provenance and focused patch.
- `build-logs/`, `buildability.json`, `tool-versions.json`, and
  `package-build.json`: build/tool evidence.
- `verification/`: initial, prior-review remediation, and terminal-receipt
  remediation syntax/test/build logs.
- `checksums.sha256`: complete committed inventory; regenerated after all
  reviews and documentation edits. The generator refuses candidate or ledger
  regeneration after freeze; `--verify-ledger` remains read-only.
- `standards-review.md` and `spec-review.md`: independent PASS verdicts bound
  to the reviewed staged tree, diff, status, ledger, and packet commitment.
- `bench/m9/recovery-v2/`: six Run Specs plus the auditor-only mapping.
- `src/aiverify/bench/m9_recovery_qualification.py`: fail-closed candidate,
  frozen-manifest, admission, and Supported-gate validation.
- `tests/bench/test_m9_recovery_qualification.py`: recovery-v2 regression
  tests.

No screenshot, layout dump, logcat, installed APK, emulator session, manual UI
step, live Codex event, oracle output, Finding, Residual Risk, Project Risk Map,
or Falsification Review artifact exists in R3.

## Known gaps and approval gate

R4 must implement and statically verify the recovery-v2 formal consumer against
this exact merged packet before starting the single formal attempt. It may not
change the packet, mapping, Run Specs, pair, denominator, oracle, review policy,
or accounting rules. Runtime accessibility of the old Jetchat Compose input and
the controlled rotation observation remain deliberately untested holdout facts.
The repository has no installed `ruff` executable, so the attempted Ruff check
could not start; syntax compilation, whitespace checks, focused/full tests,
package build, and both repository review axes are the applicable checks.

Human approval must explicitly affirm the exact ProjectTarget/pair, packet
commitment, hidden mapping commitment, six-lane blocked cohort, probe/boundary,
one-attempt policy, Supported gate, preserved #137 `Not Supported` result, and
local-only claim boundary. Silence and prior M9/R2 approvals do not count.

After approval, the generator's approval-only mode records the issue comment
URL and changes the manifest to `frozen`; it verifies that packet commitment
shown in `candidate-decision-packet.json`
did not change. Finalization accepts only a real-shaped #152 GitHub issue
comment URL, a nonblank reviewer, and a timezone-aware timestamp, with
`frozen_at == approved_at`. Afterward, ordinary candidate generation and
checksum-ledger regeneration fail closed. Until approval, no freeze PR may
merge and R4 may not begin.
