# Issue #212 — recording family execution

Status: recording-only implementation and final verification complete; code and
actual evidence are packaged together for publication. The user explicitly
authorized commit, push, issue comment and issue handling after verification.
GitHub publication and issue state must be checked against the linked commit and
issue history, not inferred from this authorization.

## Scope

Execute and seal four prepared opaque lanes using one recording-device session.
No real Android CLI/adb/emulator/device session or live model invocation is
permitted. The reducer, `reduce-family`, and complete `verify-record` remain
#213 work; this record must not claim a calibration reduction or capability.

## Baseline

- Source revision: `e8de405ff059461dc2e993e6aa1be50d84fa1d29`.
- Python: 3.12.13; pytest: 9.1.1.
- The committed 2026-09-29 Gradle environment-unblock record's five checksums
  were verified from its own directory. Its recorded full suite was 1484 passed,
  52 skipped, zero failures; that is historical evidence, not a current test run.
- Current focused baseline command:

  ```bash
  .venv/bin/python -m pytest tests/bench/test_runtime_calibration.py tests/bench/test_runtime_family_preparation.py tests/bench/test_runtime_attempt.py tests/bench/test_runtime_mapping.py
  ```

  Result: **132 passed, 10 skipped in 25.58s**, exit 0. Raw output:
  `verification/baseline-focused.log`.
- Current full baseline command: `.venv/bin/python -m pytest`.
  Result: **1484 passed, 52 skipped, 3 warnings in 580.59s**, exit 0.
  Raw output: `verification/baseline-full-suite.log`. This confirms the historical
  m7 environment failure is not a current blocker on this host.

## Implementation and focused verification

- `src/aiverify/bench/runtime_family_execution.py`: recording-only session,
  admission, frozen opaque order, boundary probes, failure-scope continuation,
  actual attempt bindings, independent teardown and atomic terminal sealing.
- `runtime_attempt.py`: carry simulated device state between fresh lane adapters;
  counters and probe ordinals remain attempt-local.
- `runtime_family_preparation.py`: preserve original preparation receipt bytes.
- `runtime_calibration.py`: explicit `execute-family` CLI with bounded opaque
  observation JSON; no arbitrary callable provider or live device option.
- `tests/bench/test_runtime_family_execution.py`: 46 cases covering execution,
  surprises, admission, shared health, drift, interruptions, write failures,
  teardown, state carryover, raw probes, forbidden flags and live backend traps.

Commands (exit 0):

```bash
.venv/bin/python -m pytest tests/bench/test_runtime_family_execution.py --color=no
.venv/bin/python -m pytest tests/bench/test_runtime_family_execution.py tests/bench/test_runtime_family_preparation.py tests/bench/test_runtime_attempt.py tests/bench/test_runtime_calibration.py tests/bench/test_runtime_mapping.py --color=no
```

Results: **46 passed in 26.67s** and **178 passed, 10 skipped in 82.33s**.
See `verification/final-family-tests.log` and `verification/final-focused.log`.

Development failures were corrected, not hidden: the first expanded run had
2 failures (a whitespace-only terminal mutation was semantically valid, and a
read-only raw receipt needed chmod before test tampering). A trial canonical
encoding check rejected valid preparation terminals because that stage uses a
different serialization; it was removed, retaining existing predecessor identity
verification. The mutation now changes terminal status. The intermediate failing
run is retained as `verification/expanded-family-tests.log` (25 failed, 21 passed).

## Preserved recording CLI demonstration

```bash
PYTHONPATH=. .venv/bin/python docs/runs/2026-10-02-issue-212-runtime-family-execution/generate_recording.py
```

Exit 0. The helper explicitly creates a successful simulated preparation using
existing test fixture machinery, then invokes the `execute-family` CLI in a
separate Python process. It does not make the CLI auto-chain preparation. The
initial invocation without `PYTHONPATH=.` failed to import `tests` before creating
any artifacts; the corrected command above is the evidence-producing invocation.
`verification/cli-command.json` preserves the exact subprocess argument vector;
stdout, stderr and exit code are alongside it.

The fixture APK files and signing material are explicitly simulated test bytes,
not real APK builds or credentials. Actual recording-generated artifacts are
retained under `recording/`: preparation receipts, sealed fixture APKs, four
ExecutionRecords, layouts, logs, command observations, family/start/terminal
receipts and separate teardown. No missing artifact is filled with a placeholder.
The execution inventory contains 40 files; every recorded size/SHA-256 was checked.

Existing `verify_runtime_attempt` independently verified each of four lanes:
L1 = inconclusive throughout; L2 = pass, fail, pass, fail. The family stage is
accepted with one simulated start/stop and zero model calls/retries/replacements.
These are observations, **not a reducer result**. See
`verification/cli-artifact-check.json`. This verification is not #213 `verify-record`.

## Evidence limits and pending closure

- Full run `.venv/bin/python -m pytest --color=no` returned exit 1:
  **1529 passed, 52 skipped, 1 failed, 3 warnings in 769.06s**.
  `test_default_run_skips_external_fixture` expected plain subprocess summary
  text but received ANSI colors. No test/product code outside #212 was changed.
  `env -u FORCE_COLOR -u PY_COLORS NO_COLOR=1 .venv/bin/python -m pytest tests/test_external_fixture_gate.py --color=no`
  then passed **4 tests in 6.95s**. Final command:
  `env -u FORCE_COLOR -u PY_COLORS NO_COLOR=1 .venv/bin/python -m pytest --color=no`
  passed **1530 tests, 52 skipped, 3 warnings in 709.33s**, exit 0.
  See `verification/final-full-suite-no-color.log`; warnings are the existing
  element-truth-value deprecations in `agent/oracle/l2.py:123`.
  Both failure and recheck logs are retained.
  An earlier post-change full run was
  interrupted with process exit -1 before a pytest summary; its partial output
  remains in `verification/post-change-full-suite.log`, not a passing result.
- Independent review found and rechecked fixes for interruption accounting,
  raw probe consistency and shared simulated log health. Its follow-up reported
  no remaining high-confidence blocking production defect, while requesting
  failure-path tests; those tests were subsequently expanded to 46 passing cases.
  A supplemental review initially could not access the main checkout from its
  isolated environment. A subsequent independent review used six SHA-identical
  source/test/documentation files copied into its own clean worktree. It found
  one medium compatibility defect: supported Mapping-based preparation receipts
  were not preserved for execution. The implementation now saves their canonical
  bytes while retaining exact original bytes for typed receipts. A new regression
  prepares Mapping receipts, executes four lanes and verifies each attempt.
  Post-fix focused command (same five test modules as above, with
  `env -u FORCE_COLOR -u PY_COLORS NO_COLOR=1`) passed **179 tests, 10 skipped in
  42.49s**. See `verification/mapping-receipt-focused.log`.
  The earlier 46/178/1530 counts remain historical pre-fix results. Final post-fix
  command `env -u FORCE_COLOR -u PY_COLORS NO_COLOR=1 .venv/bin/python -m pytest --color=no`
  passed **1531 tests, 52 skipped, 3 warnings in 482.23s**, exit 0
  (`verification/mapping-receipt-full-suite.log`). The reviewer confirmed that
  the supplied targeted patch resolves the finding; see
  `verification/independent-review.md`. The family suite now contains 47 cases.
- Source/tool health observations are explicitly session-owned simulations;
  neither host source trees nor real Android tool health were probed by execution.
- Receipts retain absolute paths and bind this checkout/output root. Do not rewrite
  them to claim portable replay; moving the directory can invalidate path checks.
- The generator refuses an existing `recording/` directory. Do not overwrite or
  repair sealed evidence to rerun it; use a separate fresh run directory.
- No real device, formal population, model, reducer or ADR promotion was performed.
- This run record and its complete actual artifact inventory accompany the code
  commit. The final source snapshot binds the five tested source/test files;
  documentation-only publication updates do not change those tested bytes.
- `checksums.sha256` covers every run file except itself, including historical
  failures and the final successful logs. GitHub issue #212 records publication
  links and acceptance disposition; #213 remains separate work.
