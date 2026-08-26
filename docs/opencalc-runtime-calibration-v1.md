# OpenCalc Runtime Calibration V1 design specification

Status: clarified design; the issue #200 source-of-truth implementation exists,
while runtime evidence does not yet exist.

This document preserves the operational decisions for
`opencalc-runtime-calibration-v1`. Canonical domain terms live in
[`CONTEXT.md`](../CONTEXT.md); the architectural rationale lives in
[ADR-0004](adr/0004-first-class-journey-driver-backends.md) and
[ADR-0005](adr/0005-accountable-runtime-calibration-family.md). This document
is deliberately a version-specific specification rather than glossary content.

## 1. Purpose and claim boundary

The family calibrates the Injection Lab → Discovery Campaign → Android runtime
evidence seams against one known OpenCalc behavior. It is not a Qualification
Cohort, holdout, benchmark population, capability denominator, or Verification
Agent evaluation.

The only primary quality contract is preservation of the unfinished expression
`12+34` across orientation-driven `MainActivity` recreation. Calculation
correctness, history, process death, and general application quality are out of
scope.

The family is model-free. Discovery derivation, Journey execution, L1/L2
evaluation, and reduction are deterministic. It does not run L3, a Verification
Agent conclusion, Finding, Falsification Review, independent model
adjudication, or any other model role. The invocation ledger must prove zero
model calls; an accidental call invalidates the family.

## 2. Frozen host and identities

| Field | Value |
|---|---|
| Upstream origin | `https://github.com/clementwzk/OpenCalc.git` |
| Upstream commit | `0584d61189e916a62a3b402223b35e1d7a3093db` |
| Calibration family | `opencalc-runtime-calibration-v1` |
| Matched pair | `opencalc-input-save-enabled-v1` |
| Quality Contract | `opencalc-unfinished-expression-config-recreation-v1` |
| Package | `com.darkempire78.opencalculator.debug` |
| Launcher Activity | `com.darkempire78.opencalculator.activities.MainActivity` |
| Build variant | `debug` |
| Version | `versionCode=54`, `versionName=3.2.1` |
| SDK | min 21, compile 35, target 35 |
| AVD | `aiverify_api35` |
| Android CLI | `1.0.15498356` |
| Python currently observed | `3.14.4` |
| uv currently observed | `0.11.7` |

The current host checkout is `/Users/peter/hosts/opencalc-calibration`, but
runtime materializations are fresh worktrees and do not reuse it.

Auditor-only catalog entry identities are:

- `opencalc-input-save-enabled-control-v1`
- `opencalc-input-save-enabled-defect-v1`

Driver-visible identities are `ocrc-v1-lane-01` through
`ocrc-v1-lane-04`; corresponding packet and plan identities use the same
opaque ordinal. Runtime paths and process inputs cannot contain target kind,
variant, or catalog meaning.

Checked-in inputs are rooted at
`bench/runtime-calibration/opencalc-input-save-enabled-v1/`. `auditor/` may use
semantic names. `runtime/lanes/lane-01` through `lane-04` have the same depth
and generic file set, including `run-spec.yaml` and `driver-plan.json`. An
admitted identifier cannot be reused with different bytes or meaning; changes
require V2.

The auditor mapping is fixed as:

| Runtime lane | Source target | Variant |
|---|---|---|
| `ocrc-v1-lane-01` | ChangeTarget | control |
| `ocrc-v1-lane-02` | ChangeTarget | defect |
| `ocrc-v1-lane-03` | ProjectTarget | control |
| `ocrc-v1-lane-04` | ProjectTarget | defect |

This table is never supplied to the Journey driver.

## 3. Matched source pair

Both entries are `curated_controlled_injection`, use taxonomy
`config-change-01`, and share the same upstream baseline, mutation operator,
target file, insertion location, patch context, and Upstream Source Anchor.
Their only materialized source difference is the boolean right-hand side of one
inserted line immediately after the uniquely admitted context around:

```kotlin
binding.input.showSoftInputOnFocus = false
```

- control inserts `binding.input.isSaveEnabled = true`
- defect inserts `binding.input.isSaveEnabled = false`

The target is
`app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt`.
Because the short anchor line occurs more than once upstream, the catalog must
bind sufficiently wide exact context bytes whose occurrence count is exactly
one. The Upstream Source Anchor includes origin, commit, repository-relative
path, complete target-file SHA-256, exact context bytes and SHA-256, and
required occurrence count. Both entries reference the same anchor digest.

Admission verifies the anchor against a pristine upstream checkout before
patching and rejects any missing, duplicate, or drifted context, extra hunk,
operator change, taxonomy change, or source change. A local FixtureAnchor is
supplementary and cannot replace the external anchor. Control equivalence is
not inferred from the spelling `true`; the auditor preflight must demonstrate
equivalence to untouched upstream in all three replays.

## 4. Discovery inputs and projections

Discovery Source Materialization is auditor-private and happens before the
side-effect-free campaign:

- Both ChangeTargets read the same pristine baseline and bind their real
  catalog diffs without applying those diffs to the discovery worktree.
- Each ProjectTarget uses a separate clean deterministic synthetic commit with
  the upstream baseline as parent and the corresponding injected tree. Author,
  committer, message, timestamp, parent, tree, patch, and commit are fixed and
  receipt-bound.
- Materialization may use local Git, but cannot build, access a device, invoke a
  model, or release runtime mapping.
- Discovery worktrees are never reused for preflight or runtime builds.

All four campaigns use the same deterministic Risk Prior, Attack Operator,
neutral Quality Contract, Risk Hypothesis, Attack Plan, and exploration policy.
Each campaign must pass real side-effect-free admission; there is no model.

Context Acquisition has budget nine and must read all of these paths with all
six existing deterministic evidence adapters:

1. `MainActivity.kt`
2. application manifest
3. portrait main layout
4. landscape main layout
5. application build file
6. root build file
7. settings file
8. version catalog
9. Gradle wrapper properties

A missing, unreadable, skipped, or budget-exhausted path rejects the campaign.
An explicitly sourced `unknown` remains legal and cannot be promoted to fact.
ChangeTargets combine the pristine graph with their real Behavior Delta and
Contract Drift; ProjectTargets acquire the scoped graph from their synthetic
commits.

Each admitted Source-Rich Discovery Package retains source provenance, target
kind, catalog entry, paths, mutation bytes, and (for ChangeTarget) the real
diff. It is never driver input. Its Blind Runtime Projection retains only
opaque identities, the neutral contract/hypothesis/plan, outcome-blind Run Spec
and setup/driver-plan commitments. Runtime Run Specs have `diff: null` for all
four lanes. Leakage admission examines every driver-visible byte, path, argv,
and environment value.

After all four admissions and leakage reviews pass, one strict append-only
`mapping-release.json` atomically changes `sealed_blind` to
`mapping_released`. It covers all four lanes and maps each to target kind,
variant, catalog entry, discovery materialization, and runtime source request.
There is no partial, per-lane, replaceable, or post-hoc release. Only Source
Authority consumes it before preparation and the final reducer consumes it
after terminal attempts. Any missing/duplicate lane, digest mismatch,
post-release mutation, or unauthorized consumer aborts the family and requires
a new version.

## 5. Journey backend and capability boundary

Runner policy admits exactly `codex_cli` or `deterministic_android_v1`; the
selection is outside the backend-neutral Run Spec. Deterministic selection
requires a checksum-bound Driver Plan and forbids a Journey model override.
Codex selection forbids the plan. Legacy callers default to Codex and historical
Codex evidence remains read-only verifiable.

Backend-owned raw evidence is separate from runner-owned canonical
`journey-result.normalized.json` and `journey-action-lineage.json`. Effective
Execution Identity records only tools actually invoked. A deterministic role
uses explicit not-applicable model fields and never emits a synthetic Codex
receipt. Journey and L3 identities are independent.

The deterministic backend has its own least-authority request type. It receives
only segment identity, opaque action identities, the admitted plan slice, a
narrow primitive adapter, and an opaque evidence sink. It does not receive the
complete Run Spec, host worktree, source paths, target kind, diff/spec, mapping,
oracle, expected result, or unrestricted command/filesystem interface. Its
adapter exposes only admitted resource-ID waits and taps. This is a type,
admission, and data-flow guarantee, not an OS sandbox claim.

Each strict UTF-8 JSON Driver Plan binds one exact Run Spec SHA-256. Duplicate
keys, unknown fields, invalid types, missing actions, and extra actions reject
admission. V1 has only:

- `wait_for_resource_id`, fixed at a 5-second bound with 350 ms observation
  probes;
- `tap_resource_id`, exactly one dispatch plus a fixed 350 ms settle.

Plans cannot specify coordinates, sleeps, timings, shell, text injection,
launch, reset, rotation, selectors, or fallbacks. Each tap reads a fresh
device-scoped Android CLI layout, requires one clickable node, validates its
on-screen center, and taps that center. Driver `PASSED` means only that admitted
primitives were validated and dispatched; it is not an oracle result.

Each lane has one Journey action with this exact sequence:

1. wait for `oneButton`
2. tap `oneButton`
3. tap `twoButton`
4. tap `addButton`
5. tap `threeButton`
6. tap `fourButton`

The input field resource ID is `input`. No equals action is performed.

## 6. Boundary, lifecycle, logs, and oracle

After the Journey, the Boundary Precondition requires a unique valid `input`
layout node whose text is exactly `12+34`. Failure is non-accountability, not an
oracle failure.

The runner then writes unique lifecycle start/end markers, dispatches rotation
once, and performs a bounded read-only poll for 5 seconds at 100 ms intervals.
The Lifecycle Transition Receipt must prove:

- same task and PID;
- exact `MainActivity` resumed in landscape at rotation 1;
- no target process start, death, or restart;
- the frozen ordered destroy → create → resume and relaunch-tag signature.

The minimal signature is frozen only after all nine auditor cycles agree.
Missing/duplicate markers, contradictory required events, or an unstable
signature make the attempt non-accountable before L2.

L2 evaluates one unique post-event `input` node:

- exact `12+34` → `pass`;
- any other text, including Android CLI's omitted-text representation for empty
  text → `fail` with `state_loss`;
- missing, duplicate, or structurally invalid node → accountable
  `inconclusive` if capture and parsing themselves are valid;
- capture, parse, or checksum failure → non-accountable.

The runner owns one canonical target log window. After setup it clears all
buffers once, writes a unique attempt-bound start marker, and never clears
again. Every runner-reachable terminal path writes one end marker in `finally`
and captures exactly one all-buffer epoch-formatted dump. One ordered marker
pair must exist. The same raw dump yields the target-filtered L1 evidence and
lifecycle slice; checkpoint logs are diagnostic only. Missing/reversed/
duplicate markers, capture failure, or ambiguous crash/ANR attribution are
non-accountable. A failure before the start marker has no fabricated receipt.

Complete attributable logs without a crash/ANR signal produce L1
`inconclusive`, never `pass`. The expected family shape is L1 inconclusive in
all cells, L2 pass for controls, and L2 state-loss failure for defects.

## 7. Build, vault, signing, and sealed APK

All build inputs are held in a family-specific read-only Runtime Input Vault
outside Git. It contains the sealed dependency bundle and non-production family
signing identity. Git records the absolute location, retention reason/status,
relative paths, sizes, per-file SHA-256, and aggregate digest, but not private
key bytes or credentials. No cell copy may be a symlink or hard link. The vault
is verified before and after use and retained at least through evidence review;
loss prevents rebuild/rerun but does not erase auditability of committed
evidence.

The dependency bundle includes the Gradle distribution, plugins, and resolved
artifacts. Each build receives a fresh private copy and uses Gradle dependency
resolution offline. Proxy/network overrides are scrubbed; missing dependencies
fail without online fallback or retry. This is not an OS-level no-network
claim.

One new family signing keystore is generated before freeze and becomes
read-only. Public evidence binds its location, keystore hash, signer
certificate hash, alias, and tool identity. Four builds receive independent
exact copies through private Android homes, with no fallback to an ambient
debug keystore. Loss/drift requires a new family and later families use new
identities.

Every runtime build runs once, without a shell, with a 900-second timeout and
exact argv:

```text
./gradlew --offline --no-daemon --no-build-cache --no-configuration-cache --max-workers=1 --console=plain clean :app:assembleDebug
```

The recipe binds the resolved OpenJDK 17.0.19 installation, SDK root
`/opt/homebrew/share/android-commandlinetools`, platform 35, C.UTF-8 locale,
UTC, `SOURCE_DATE_EPOCH=1783693058`, private Gradle/Android/temp/user homes, and
a blank allowlisted environment with fixed PATH/JVM options. There is no retry.
The sole accepted output is the regular, non-symlink
`app/build/outputs/apk/debug/app-debug.apk`; extra, missing, escaped, timed-out,
nonzero, or uncertain output rejects preparation.

Fixed build-tools 36.0.0 `aapt2` and `apksigner` must prove the declared
package, launcher, version, SDK values, debuggable flag, exactly one family
signer, and successful V1/V2 verification. Warnings remain evidence. The APK is
hashed before/after inspection, atomically copied to lane-local
`build/app-debug.apk`, rehashed, and made read-only. The handoff binds that path
and digest. The new path rejects `AIVERIFY_DEPLOYED_APK`; deployment uses only
the sealed copy and verifies the installed device APK hash. Every actually
built APK, including one implicated in a failed equality gate, is committed to
its lane record.

## 8. Verifier identity, freeze, and auditor preflight

One `calibration_implementation_commit` contains implementation, schemas,
public inputs, plans, recipes, manifests, and discovery/mapping commitments.
Preflight and family execution use a clean detached verifier worktree at that
commit plus one external venv created from `uv.lock` with frozen/no-dev
semantics. Commands invoke that venv's Python module directly, without ambient
`PYTHONPATH` or bytecode writes, and write evidence outside the worktree.

Verifier Runtime Identity binds origin, commit/tree/clean state, tracked and
loaded source/schema manifests, lock bytes, uv/Python binaries, installed
distribution files, argv, cwd, and allowlisted environment. It is checked
before preflight and before/after every cell. Generated evidence may be copied
and committed in the main worktree, but the detached verifier never imports or
executes it.

The candidate state progression is:

`candidate_frozen` → `preflight_qualified` → `family_admitted` →
`family_prepared` → `family_executed` → `family_reduced`.

Successful preflight creates a checksum-bound `family-admission.json` that
binds candidate commit, frozen-input digest, mapping receipt, and preflight
receipt without modifying candidate bytes. Implementation/frozen-input changes
require V2 and complete preflight; append-only evidence does not.

Auditor Runtime Preflight runs on a dedicated non-family cold boot using three
labeled APKs and this Latin square:

1. upstream → control → defect
2. defect → upstream → control
3. control → defect → upstream

Every cycle redeploys, resets, launches, drives, rotates, and evaluates through
the candidate production seams. Required results are:

- upstream: 3/3 accountable, L1 inconclusive, L2 pass;
- control: 3/3 accountable, L1 inconclusive, L2 pass;
- defect: 3/3 accountable, L1 inconclusive, L2 fail/state_loss;
- one stable lifecycle signature across all nine.

Any cycle failure or later frozen code/input drift invalidates all nine. There
is no selective rerun; repair requires a new version. The auditor emulator is
stopped and observed absent before the separate family boot.

## 9. Family preparation and device session

Runtime Family Preparation occurs before any cell ExecutionRecord. It creates
four fresh source worktrees and four independent builds in opaque execution
order. A lane-local failure may allow later planned builds only after shared
verifier/vault/tool/source health is reproven; shared or unknown-scope failure
marks later lanes `not_prepared_due_to_family_abort`.

Device execution is admitted only after all four sealed APKs exist and prove:

- Change/Project APK byte equality within each variant;
- defect/control APK byte inequality;
- closed source, metadata, signing, handoff, and receipt identity.

Failure preserves all real artifacts, creates no placeholder or cell
ExecutionRecord, starts no family emulator, and requires V2.

The family requires no existing target AVD process and starts exactly one
`android emulator start --cold aiverify_api35` session. It does not wipe AVD
data; `--cold` means no snapshot was loaded for this boot. The session receipt
binds Android CLI, emulator/QEMU, adb, AVD config, system-image manifest,
wrapper/actual argv, boot ID, serial, API/fingerprint/ABI/model, hardware,
density/resolution, and observed settings. Identity is checked around every
cell. Restart, disconnect, or identity drift aborts remaining cells. One
evidenced stop follows execution; teardown-only failure cannot rewrite closed
oracle outcomes.

The only permitted device mutations are target-package clear and one write each
of `accelerometer_rotation=0` and `user_rotation=0` per lane. Read-only
identity-critical state comprises fingerprint/API/ABI/model, display size and
density, locale list, timezone ID, font scale, all animation scales, night mode,
navigation mode, default IME, and enabled accessibility services. It must match
preflight and remain invariant at lane boundaries except for intentional
rotation. Clock, battery, thermal/load, and network connectivity are recorded
but ordinary variation does not fail calibration. No other setting or network
state is modified and no network-isolation claim is made.

## 10. Attempt setup and phase order

One strict JSON Attempt Setup Plan is byte-identical across all lanes. It binds
family/package but contains no serial or raw argv. Its only high-level
operations are `clear_package_data` and `force_portrait`.

After deployment and installed-byte verification, package clear runs once and
must return exit zero plus exact `Success`; one read must then prove no target
PID. Rotation settings are each written once, followed by a fixed 350 ms settle
and one settings/display read proving portrait/rotation 0. There is no poll,
rewrite, retry, compensation, or use of pre-deployment package absence as the
reset proof.

Every started lane has exactly one ExecutionRecord and follows this order:

1. establish the ExecutionRecord;
2. verify frozen inputs and static identity;
3. perform device/tool preflight without launching the app;
4. deploy through Android CLI and verify installed APK bytes;
5. execute the Attempt Setup Plan;
6. clear all logs and write the target-window start marker;
7. perform one canonical application launch;
8. verify the foreground component once;
9. execute the Journey;
10. prove Boundary Precondition;
11. mark and dispatch lifecycle rotation once;
12. collect post-event observations;
13. finalize markers/log window, post-cell identity, receipts, and oracle.

Deployment may launch the app; subsequent package clear treats that as setup
contamination. A pre-deployment app smoke is prohibited because it could
observe a stale APK.

Canonical launch is one serial-scoped `am start -W` with MAIN, LAUNCHER, and
the exact package/activity component. It requires exit zero, `Status: ok`, and
the exact reported component. After one 350 ms settle, one foreground read must
match. There is no monkey fallback, relaunch, or launch-owned layout poll; the
Journey's first wait owns surface readiness.

## 11. Terminal states and reduction

Preparation records one row per lane:

- `prepared`
- `preparation_rejected`
- `not_prepared_due_to_family_abort`
- `prepared_but_family_not_admitted`

A started attempt finalizes once as:

- `accountable_concluded` when identity, log window, Journey, precondition,
  lifecycle, and oracle all close; or
- `non_accountable` with one canonical reason and no authoritative oracle.

An unstarted runtime lane has no fabricated ExecutionRecord and appears only as
`not_attempted_due_to_family_abort` in reduction. An accountable unexpected
oracle does not stop later lanes. Lane-local non-accountability allows
continuation only after prescribed shared-health checks close again; shared or
unknown verifier/device/log failure aborts the rest. No result is retried.

The no-I/O pure reducer consumes only frozen inputs, mapping, four preparation
rows, and existing terminal attempt evidence. It emits:

- `expected_split_observed`: 4/4 accountable with the exact expected L1/L2
  shape;
- `unexpected_runtime_result`: 4/4 accountable but a different oracle shape;
- `not_calibrated`: any preparation rejection, unattempted lane, or
  non-accountable attempt.

These are local calibration states, not rates or capability claims.

## 12. Evidence record

The durable record root is
`docs/runs/<date>-opencalc-runtime-calibration-v1/` and contains:

- `README.md`;
- family manifest and frozen public inputs;
- discovery admission, leakage, and mapping receipts;
- preflight and family-admission evidence;
- family preparation and device-session evidence;
- opaque lane directories containing only artifacts that actually exist;
- pure reduction and independent verification;
- external-vault inventory;
- `SHA256SUMS` covering every committed file except itself.

Every actual lane build preserves its signed APK. No placeholder attempt or APK
is created. The record is durable only after commit and a GitHub issue comment
links its commit/path and lists exact commands, tool versions, results/counts,
durations, artifact inventory, device/manual checks, checksums, and gaps.
Before commit it must be labeled local-only.

## 13. Stage interface and interruption

The sole orchestration entry point is:

```text
python -m aiverify.bench.runtime_calibration <subcommand>
```

Fixed subcommands are:

- `verify-candidate`
- `run-preflight`
- `admit-family`
- `prepare-family`
- `execute-family`
- `reduce-family`
- `verify-record`

Every mutating/side-effecting stage requires a new empty staging root and its
predecessor's checksum-bound terminal receipt. There is no `--force`,
`--resume`, `--retry`, automatic stage chaining, or one-shot command. Before
the first side effect the stage atomically writes `stage-start.json`; every
runner-reachable finalization writes `stage-terminal.json`.

A start without terminal is `abandoned`. Unless evidence proves no side effect
started, that version is consumed. Teardown/recovery may append cleanup evidence
and stop an orphaned emulator but cannot restore attempt eligibility or alter
reduction. A structurally complete `unexpected_runtime_result` is a successful
command result; contract, accountability, or infrastructure-closure failure is
an unsuccessful command.

## 14. Validation ladder and ADR promotion

Validation layers cannot substitute for one another:

1. Strict contract tests cover schemas/digests, backend selection,
   least-authority requests, source/mapping/leakage, build/APK/signing,
   state/reducer, all rejection branches, and legacy Codex fixtures.
2. Recording-fake command/device integration tests cover success and every
   phase failure, zero retries, forbidden-command unreachability, log-window
   finalization, no preparation ExecutionRecords, shared-failure stopping, and
   the zero-model ledger.
3. Real nine-cycle Auditor Runtime Preflight runs on its dedicated cold boot.
4. Real four-cell family runs on a separate cold boot, followed by independent
   read-only recomputation without a live device.

Each layer records exact commands, versions, pass/fail counts, durations,
artifacts, and gaps. Structured layouts, marker-bounded logs, and APK/identity
receipts are authoritative; screenshots are supporting evidence.

ADR-0004 may move to `accepted` after layers 1–2 pass. ADR-0005 remains
`proposed` until layer 3 succeeds; its promotion does not depend on the family
later producing the expected split rather than another structurally valid
terminal reducer state.

## 15. Implementation slicing

Track delivery under one umbrella PRD with these ordered child scopes:

1. Journey backend seam and backend-neutral normalized evidence.
2. Deterministic Driver Plan, least-authority request, and Android primitive
   adapter.
3. OpenCalc catalog/source anchor, Discovery materialization, blind projection,
   and mapping release.
4. Runtime vault/signing, offline build, and Sealed APK preparation.
5. Device session, setup, canonical launch, log/lifecycle/oracle receipts.
6. Stage orchestrator, terminal states, pure reducer, and read-only verifier.
7. Complete contract and recording-fake integration validation, followed by the
   immutable candidate commit.
8. One complete 9/9 Auditor Runtime Preflight and its committed evidence.
9. Four-cell preparation/execution, reduction, independent verification, and
   committed evidence.

Scopes 1→2 are sequential. Scopes 3 and 4 may progress independently while the
backend work is underway; scopes 5→6→7→8→9 then close the critical path.

A run-scoped child may finish once its one authorized execution and all real
terminal evidence are preserved, including a failed terminal outcome. The
umbrella closes only on a fully accountable `expected_split_observed` or
`unexpected_runtime_result`. A `not_calibrated` V1 remains immutable evidence,
but requires a linked repaired version and leaves the umbrella open.
