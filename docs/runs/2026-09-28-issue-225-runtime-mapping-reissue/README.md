# Issue #225 — Reissued Runtime Mapping with per-lane ChangeTarget materializations

Status: passed; evidence is committed with the implementation.

This run fixes the defect recorded by #208/#206: the committed v1 mapping
recorded one shared host checkout path for both ChangeTarget lanes. Strict
family preparation rejects that shape (`family_worktree_not_independent`) and
the post-materialization mapping comparison would reject it again
(`family_worktree_mapping_mismatch`). The reissued v2 release materializes one
private pristine clone per ChangeTarget variant, leaves the four-lane delivery
contract unchanged, and keeps v1 loadable and verifiable byte-identically.
This proves the mapping release boundary only. No Gradle build, APK
preparation, Android CLI, adb, device/emulator, runtime attempt, model, or
oracle work was performed.

## Scope and identities

- Issue: [#225](https://github.com/yangliang2/ai_verification/issues/225)
  (DIL-M1.10a), parent
  [#199](https://github.com/yangliang2/ai_verification/issues/199); blocked by
  nothing; unblocks [#216](https://github.com/yangliang2/ai_verification/issues/216).
- Family: `opencalc-runtime-calibration-v1` / `v1`
- Superseded release: `opencalc-runtime-mapping-release-v1` as committed by
  [#206](docs/runs/2026-08-29-issue-206-runtime-mapping-release/README.md)
  (stays loadable and verifiable byte-identically; not modified)
- Reissued release: `opencalc-runtime-mapping-release-v2`
- Release identity: `cd2c36ec0ac994d03a3118f44542f5114a3c9b61129e19bb110caf658d0b1cad`
- Release file SHA-256: `8e5e652c4c5c8fff8018b33cb7a4d6e43518e4714a68510e443608b8c40e6d68`
- Candidate: `bench/runtime-calibration/opencalc-input-save-enabled-v1`
- Candidate identity: `1e247a243e2d9fcfc9704a641c5f1174b1f4cbceee7f2af28ad494d32c68bfd5`
- Candidate manifest SHA-256: `cda8a8946ea77720f2fb473517559fc2c65f7c56ed3b71fd329fec322147b04b`
- Candidate artifact inventory SHA-256: `393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`
- Pinned source: the documented checkout path is
  `/Users/peter/hosts/opencalc-calibration`; on the machine that produced this
  evidence the same pinned checkout lives at
  `/Users/80268204/hosts/opencalc-calibration`
- Pinned source commit: `0584d61189e916a62a3b402223b35e1d7a3093db`
- Repository HEAD at capture: `3365b82c0a247ef52fd7b59926a0d6f41d871292`;
  the six files implementing this issue were intentionally dirty
  (uncommitted) while the release was issued, because the release must be
  produced by the new code. See `verification/release-verification.json`
  (`repository_dirty_entries`) for the exact working-tree state.

The reissued release keeps the frozen opaque lane order. Each lane now records
its own worktree:

| Lane | Auditor meaning | Materialization kind | Worktree |
|---|---|---|---|
| `ocrc-v1-lane-01` | ChangeTarget/control | `change_target_pristine_source` | `/private/tmp/opencalc-issue-225-change-materializations/opencalc-input-save-enabled-v1-control` |
| `ocrc-v1-lane-02` | ChangeTarget/defect | `change_target_pristine_source` | `/private/tmp/opencalc-issue-225-change-materializations/opencalc-input-save-enabled-v1-defect` |
| `ocrc-v1-lane-03` | ProjectTarget/control | `project_target_synthetic_commit` | `/private/tmp/opencalc-issue-225-project-materializations/opencalc-input-save-enabled-v1-control` |
| `ocrc-v1-lane-04` | ProjectTarget/defect | `project_target_synthetic_commit` | `/private/tmp/opencalc-issue-225-project-materializations/opencalc-input-save-enabled-v1-defect` |

The temporary materialization roots are not committed; their identities, clean
status, canonical origin, and detached baseline commits are preserved in
`verification/family-stage-final/mapping-release.json` and summarized in
`verification/release-verification.json`.

## Defect and fix

Defect (v1): `admit_change_target_pair` recorded the single shared host
checkout path for both ChangeTarget lanes. `runtime_family_preparation`
rejects ancestor/equal worktree roots through its `_is_overlapping` predicate
(`family_worktree_not_independent`), and even past that gate the materialized
worktree path would not equal the mapped `worktree_path`
(`family_worktree_mapping_mismatch`). The committed v1 release could therefore
never pass strict family preparation on any machine, including the one that
produced it.

Fix, in `src/aiverify/bench/opencalc_discovery.py`:

- `admit_change_target_pair(candidate_root, source_root, materialization_root=None)`
  materializes one private pristine clone per variant:
  `git clone --no-local --no-hardlinks <source_root> <root>/<source_id>`,
  re-points `origin` at the canonical URL, checks out
  `pair.baseline.commit` detached, and re-runs `_verify_pristine_source` on the
  clone. Without an explicit root the same layout is created under a private
  temporary root (`opencalc-change-target-*`).
- Root validation fails closed with typed codes before any clone:
  `source_materialization_root_unavailable`, `..._symlink`, `..._unsafe`
  (overlaps candidate root, source root, or an ancestor/descendant of either),
  `..._not_empty`; per-variant failures are `source_materialization_failed`
  and `source_materialization_path_exists`.
- Cleanup fails closed: every worktree the admission created is tracked and
  removed when later context acquisition, cloning, or verification rejects,
  leaving the materialization root empty; the host checkout is never written.
- The delivery contract for lanes 01/02 is unchanged:
  `materialization_kind == "change_target_pristine_source"`,
  `source_commit == baseline_commit`, `materialized_tree_sha256` equal to the
  committed baseline tree `8793c063c6a990ff3448fece38e62bc103952610`,
  `materialization_receipt_identity_sha256` and `result_diff_sha256` empty, no
  patch applied, no synthetic commit.

Fix, in `src/aiverify/bench/runtime_mapping.py` and
`src/aiverify/bench/runtime_calibration.py`:

- Release identity is versioned: `RUNTIME_MAPPING_RELEASE_ID_V1`,
  `RUNTIME_MAPPING_RELEASE_ID_V2` (now default), and
  `RUNTIME_MAPPING_RELEASE_IDS` accepted by all four release validators.
  `release_id` is threaded through release building so request IDs read
  `<release_id>:<lane_id>:source-request`, and
  `verify_runtime_mapping_release` re-derives each discovery with the release's
  own `release_id` — which is what keeps the committed v1 artifact verifiable
  byte-identically.
- `admit_family` accepts `change_materialization_root` and passes it to the
  ChangeTarget admission, so the two ChangeTarget clones and the two
  ProjectTarget materializations live under separate explicit roots. The CLI
  exposes `admit-family --change-materialization-root`.

Tests (`tests/bench/test_opencalc_discovery.py`,
`tests/bench/test_runtime_mapping.py`,
`tests/bench/test_runtime_family_preparation.py`):

- Seven new discovery tests (11 parametrized cases) cover non-empty,
  overlapping, symlinked/unusable, and pre-claimed materialization roots,
  unusable source roots, and fail-closed cleanup after context rejection and
  after clone/verification failure.
- The mapping suite now asserts four distinct worktrees, pairwise independence
  through the production `runtime_family_preparation._is_overlapping`
  predicate, the unchanged lane 01/02 delivery contract, unchanged lane 03/04
  kinds, `admit_family` worktree placement under both roots, byte-identical
  re-derivation and re-verification of the committed v1 release, dual
  acceptance of v1 and v2 identities, and fail-closed rejection of unknown
  release IDs.
- The family-preparation suite now binds each lane to the mapped release's own
  `release_id`/`identity_sha256` instead of the module-level constant.

## Acceptance evidence

- AC1 materialization: `admit_change_target_pair` clones per variant, verifies
  pristine state, and rejects non-empty/overlapping/symlinked roots — see
  `test_change_admission_rejects_*` and `test_change_materialization_refuses_a_pre_claimed_child_path`.
- AC2 per-lane worktree: every package records its own clone in
  `context_acquisition.source_root`, `context_acquisition.target.worktree`, and
  `RuntimeSourceRequest.worktree_path`; four distinct pairwise-independent
  worktrees in `test_release_runtime_mapping_binds_the_four_frozen_lanes` and
  in `verification/release-verification.json`
  (`distinct_worktree_count: 4`, `v2_pairwise_independent_under_family_gate: true`).
- AC3 delivery contract unchanged: per-lane assertions for lanes 01/02 in the
  mapping suite and `verification/release-verification.json` lane entries
  (kind, equal source/baseline commits, baseline tree, empty receipt and diff
  digests).
- AC4 pristine-source immutability: the host checkout is never written; unit
  tests cover dirty/non-initialized/drifted rejection via existing codes and
  assert the host checkout stays clean; `documented_host_checkout_status` is
  empty in the verification JSON.
- AC5 fail-closed cleanup: `test_change_admission_removes_created_worktrees_after_context_rejection`
  and `test_change_admission_failure_removes_every_worktree_it_created` assert
  the materialization root is empty and the source untouched after rejection
  and after clone/verify failure.
- AC6 release identity versioning: `test_committed_v1_release_stays_loadable_and_byte_identical`
  loads and verifies the committed #206 artifact and re-derives identical
  bytes; `test_versioned_release_ids_reverify_with_their_own_discoveries`
  proves both identities verify against the same discoveries;
  `test_unknown_release_ids_fail_closed` rejects unlisted IDs.
- AC7 separate change-materialization root: `admit_family(change_materialization_root=...)`
  and CLI `admit-family --change-materialization-root`; the staged end-to-end
  test asserts worktree roots `[:2]` under the change root and `[2:]` under the
  project root.
- AC8 fresh end-to-end release: the v2 release was issued against the real
  pinned source into this run directory (tables and JSON above); lanes 03/04
  remain `project_target_synthetic_commit`; #206 artifacts were not modified
  (v1 contrast in the verification JSON still shows the original shared-path
  lanes).
- AC9 tests and lint: focused suites pass (results below); changed files are
  clean under Ruff; mypy shows zero introduced errors and four resolved.
- AC10 run record and issue comment: this directory plus the evidence comment
  on #225.

## Verification commands and results

Tool versions: CPython `3.12.13`, pytest `9.1.1`, Ruff `0.16.9`, mypy `2.3.1`,
Git `2.50.1 (Apple Git-155)`, macOS `26.1` arm64.

Release commands (exact script: `verification/run-commands.sh`):

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration verify-candidate --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --output-root docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/candidate-stage

/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration admit-family --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --source-root "$HOME/hosts/opencalc-calibration" --predecessor-root docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/candidate-stage --output-root docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/family-stage-final --materialization-root /tmp/opencalc-issue-225-project-materializations --change-materialization-root /tmp/opencalc-issue-225-change-materializations
```

Results: candidate stage `accepted`, 28 artifacts, real `0.25s`; family stage
exit `0`, `accepted`, real `15.53s`; release and stage terminal identities in
`verification/family-stage-final/`; the ProjectTarget stage re-materialized
both of its lanes as before.

Independent release verification, fresh process (script committed as
`verification/verify_release.py`; output `verification/release-verification.json`):

```text
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/verify_release.py
```

Results: `stage_status: accepted`;
`verify_runtime_mapping_release_against_candidate: true`;
`distinct_worktree_count: 4`; `v2_pairwise_independent_under_family_gate:
true`; v1 contrast: both ChangeTarget lanes of the committed v1 release record
`/Users/peter/hosts/opencalc-calibration` and
`v1_lane_01_02_overlapping_under_family_gate: true` — the defect and its fix
side by side; every lane's `head`/`tree`/`origin`/`status` captured through
Git from the materialized tree; canonical origin
`https://github.com/clementwzk/OpenCalc.git`; clean statuses; empty
`documented_host_checkout_status`.

Focused suites:

```text
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AIVERIFY_OPENCALC_SOURCE_ROOT=$HOME/hosts/opencalc-calibration .venv/bin/python -m pytest tests/bench/test_opencalc_discovery.py tests/bench/test_runtime_mapping.py -q -p no:cacheprovider --junitxml=docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/focused-pytest.xml
```

Result: **51 passed**, 0 failed/errors/skipped, exit `0`; pytest `622.061s`.

```text
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_sealed_apk.py -q -p no:cacheprovider
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest tests/bench/test_runtime_calibration.py -q -p no:cacheprovider
```

Results: **12 passed** (`47.273s`) and **21 passed** (`9.968s`), exit `0`.

```text
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AIVERIFY_OPENCALC_SOURCE_ROOT=$HOME/hosts/opencalc-calibration .venv/bin/python -m pytest tests/bench/test_runtime_family_preparation.py -q -p no:cacheprovider --junitxml=.../family-preparation-pytest.xml
```

Result: **17 failed of 17 collected** — pre-existing and environmental, not a
#225 regression. Both sides of this issue (fresh HEAD worktree
`3365b82c0a247ef52fd7b59926a0d6f41d871292` and the working tree) produce the
identical sorted FAILED list; the module cannot run green on this machine for
any codebase state because the committed #206 stage receipts record a foreign
`candidate_root` (`/Users/peter/projects/ai_verfication/...`) and every test
trips `mapping_predecessor_input_mismatch`. Details and the compare command
are in `verification/baseline-family-preparation-delta.txt`; the two FAILED
lists are `verification/baseline-head-failed-tests.txt` and
`verification/baseline-worktree-failed-tests.txt`. The #225-specific gate
behaviour is instead exercised through the production predicate and the real
staged `admit_family` run in the focused suites.

Lint and types:

```text
uvx ruff check src/aiverify/bench/opencalc_discovery.py src/aiverify/bench/runtime_calibration.py src/aiverify/bench/runtime_mapping.py tests/bench/test_opencalc_discovery.py tests/bench/test_runtime_family_preparation.py tests/bench/test_runtime_mapping.py
```

Result: `All checks passed!` under the Ruff default rule set of `0.16.9`
(`verification/changed-files-ruff-default-rules.txt`). The same command over
the surrounding tree (`uvx ruff check src/aiverify/bench tests/bench`) reports
186 pre-existing findings in 49 untouched files and none in the six changed
files (`verification/baseline-ruff-bench-default-rules.txt`). One import-ordering
finding introduced while editing `tests/bench/test_runtime_mapping.py` was
auto-fixed before capture.

```text
uvx mypy --ignore-missing-imports src/aiverify/bench/opencalc_discovery.py src/aiverify/bench/runtime_calibration.py src/aiverify/bench/runtime_mapping.py
```

Result: `78` errors at HEAD vs `74` on the working tree, both in 17 files;
normalized error-set comparison (path + message, line numbers dropped):
**0 introduced, 4 resolved** (`verification/baseline-mypy-delta.txt`,
`baseline-mypy-head.txt`, `baseline-mypy-worktree.txt`).

## Evidence inventory

- `verification/run-commands.sh` — exact release commands.
- `verification/candidate-stage/{stage-start.json,stage-terminal.json}` —
  accepted candidate predecessor receipts; `candidate-stage.stdout`.
- `verification/family-stage-final/{stage-start.json,mapping-release.json,stage-terminal.json}` —
  accepted reissued v2 release; `family-stage-final.stdout`.
- `verification/verify_release.py`, `verification/release-verification.json` —
  independent verification of the release against the candidate, plus the
  v1/v2 gate contrast.
- `verification/focused-pytest.{xml,stdout}` — 51-test focused JUnit report.
- `verification/family-preparation-pytest.{xml,stdout}` — 17-test JUnit report,
  all failing environmentally.
- `verification/sealed-apk-pytest.{xml,stdout}` — 12-test JUnit report.
- `verification/runtime-calibration-pytest.{xml,stdout}` — 21-test JUnit report.
- `verification/changed-files-ruff-default-rules.txt`,
  `verification/baseline-ruff-bench-default-rules.txt` — Ruff results.
- `verification/baseline-mypy-head.txt`,
  `baseline-mypy-worktree.txt`, `baseline-mypy-delta.txt` — mypy results.
- `verification/baseline-head-failed-tests.txt`,
  `baseline-worktree-failed-tests.txt`,
  `baseline-family-preparation-delta.txt` — family-preparation failure-set
  comparison.
- `checksums.sha256` — checksum inventory for every committed run artifact.

No screenshots, layout dumps, logcat, APKs, device receipts, or manual UI
artifacts exist because runtime execution is outside this issue's claim
boundary. Temporary materializations under `/tmp/opencalc-issue-225-*` are not
committed; their identities and clean receipts are preserved in the committed
mapping release and in `release-verification.json`.

## Claim boundary and known gaps

This proves only the model-free, side-effect-free reissued four-lane Runtime
Mapping Release with per-lane ChangeTarget materializations. It does not prove
source build preparation, APK identity, device behavior, lifecycle evidence,
oracle outcomes, or a formal benchmark result, and it creates no runtime
attempt record. The pinned source is consumed read-only; the host checkout was
never written.

Known gaps: the family-preparation test module cannot run green on this
machine for the pre-existing environmental reason recorded above, so AC9's
"full bench suite" is evidenced as focused green suites plus failure-set
identity against a HEAD worktree rather than an all-green repository run.
The materialization roots remain under `/tmp` per the staged CLI's contract;
durable re-materialization can be reproduced from the committed release
identities and the pinned source commit.
