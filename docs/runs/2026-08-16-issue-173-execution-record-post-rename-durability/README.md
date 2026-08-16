# Issue #173 — ExecutionRecord post-rename durability consistency

Status: the production repair and its hermetic regression contracts are complete
on `issue-173-execution-record-post-rename-durability`. The first evidence
commit is bound by a follow-up commit that refreshes this record's checksum
ledger.

## Objective and source identity

- Issue: [#173](https://github.com/yangliang2/ai_verification/issues/173)
  (`bug`, `ready-for-agent`).
- Base revision: `d12ae239ded2450aae3ae7d4b0dc9d26bd851fae`.
- Base tree: `ddd920c5c1a40824520d698355d6a4f4c8452e53`.
- Tested implementation revision:
  `37ef02023392e229e67721780cda9ece39a7cf30`.
- Tested implementation tree:
  `f231368632569ab5e6dfe26fb9e48153465b14fd`.
- The tested implementation contains the production repair and regression
  tests. The implementation-evidence comment and the binding follow-up record
  the pushed evidence head; a final completion comment will add the merged SHA.
- Claim boundary: this is local, hermetic ExecutionRecord persistence-contract
  evidence. It does not establish Verification Agent behavior-layer capability,
  Android/OEM coverage, production outcome, durability across sudden host loss,
  oracle soundness, a formal-run result, or a quality threshold.

## Repaired Quality Contract

The fail-closed accountability Quality Contract distinguishes the irreversible
publication point from a later durability-confirmation attempt:

- Before `os.replace()` publishes the terminal record, a storage error remains
  an `ExecutionRecordStorageError`; the original in-progress ExecutionRecord is
  preserved and no temporary file remains.
- After `os.replace()` has published a terminal record, a directory fsync error
  cannot truthfully be reported as an uncommitted finalization. The store returns
  that exact terminal record and emits a warning-level log identifying
  the unconfirmed directory durability.

This removes the former contradiction where a caller saw terminal storage
failure while a later `load_execution_record()` could load an accountable
`completed` record. It makes no stronger claim that a failed post-publication
directory fsync survives a sudden host or filesystem loss.

The contract uses only temporary local files and controlled `os.replace` /
directory-fsync seams. It exercises both an accountable `completed` terminal
record and a non-accountable `failed` terminal record, then checks that the
returned and loaded values agree. The companion pre-publication case preserves
the original in-progress record under a controlled replace failure.

Issue [#171](https://github.com/yangliang2/ai_verification/issues/171) exposed
this Behavior-Layer Defect during its white-box test-contract review; #173 is
the separate production-semantics repair required by that issue's scope
boundary. No frozen historical evidence was changed.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results:

```text
# Red regression before the repair on the same temporary-filesystem seam.
uv run --extra dev python -m pytest -o addopts='' -q \
  tests/runner/test_execution_record.py
EXPECTED FAIL: 2 failed, 8 passed. Both post-replace directory-fsync cases
raised ExecutionRecordStorageError after the terminal record had been published.

# Focused runner and ExecutionRecord regression suite on tested implementation.
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_cli.py \
  tests/runner/test_execution_identity.py
PASS: 56 passed in 2.10s; real 2.22s, user 0.41s, sys 1.45s.

# Ordinary hermetic repository suite on tested implementation.
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1095 passed, 1 skipped in 85.84s; real 86.04s, user 34.93s,
sys 17.95s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

uv run --extra dev python -m compileall -q src
PASS: exit 0.

git diff --check origin/main...HEAD
PASS: exit 0.
```

## Artifact inventory, side effects, and known gaps

- `README.md` — human-readable contract, revision, command, scope, and gap
  record.
- `verification.json` — machine-readable revision, command-result, scope, and
  claim-boundary record.
- `checksums.sha256` — deterministic SHA-256 inventory for the two artifacts
  above; no screenshots, device traces, external logs, coverage reports, or
  generated formal artifacts exist for this local repair.

No device or emulator, Android build/install, package launch, model, remote
oracle, Verification Agent Backend, formal consumer, external-fixture
admission, external snapshot mutation, cohort/population action, or manual step
occurred. Tests use only pytest temporary directories and controlled local
persistence seams.

Known gaps:

- A failed directory fsync after publication is observable as local durability
  uncertainty; this repair does not prove survival across sudden host or
  filesystem loss.
- The evidence is limited to the ExecutionRecord terminal-accounting boundary;
  it does not establish Verification Agent behavior, Android runtime behavior,
  detection rate, causal validity, oracle soundness, or a quality threshold.
- The repository-external historical fixture remains skipped by default.
  Frozen M8, M9, and M9-R evidence was neither replayed nor changed.
