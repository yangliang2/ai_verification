# Issue #175 — Reject uncommitted ExecutionRecord temporary authority

Status: implementation and hermetic persistence-contract verification are
complete on `issue-175-execution-record-temp-authority`. This corrected record
supersedes the earlier evidence after the temporary-path policy was centralized
and its domain vocabulary was reconciled with `CONTEXT.md`.

## Objective and source identity

- Issue: [#175](https://github.com/yangliang2/ai_verification/issues/175)
  (`bug`, `ready-for-agent`).
- Base revision: `a59e0e50b63ae8df1dc67df15ccaefacd95721d9`.
- Base tree: `536dc46b9952dfd89f936f338c0ea19508a1d25d`.
- Tested implementation revision:
  `4d8308880c38c55757edfc9d63d7b8dd3b93e366`.
- Tested implementation tree:
  `16703bd1be61bd330567794740805fc713752a86`.
- Tested evidence revision and tree: bound by the checksum-binding follow-up
  commit after this corrected record is committed.
- Evidence correction: the earlier record used a duplicated temporary-path
  convention and stale domain wording. Every command-result claim below was
  rerun against the tested implementation revision above.
- Claim boundary: this is local, hermetic ExecutionRecord persistence-contract
  evidence. It does not establish Verification Agent behavior-layer capability,
  Android or OEM coverage, production outcome, sudden-host-loss durability,
  oracle soundness, a formal-run result, or a quality threshold.

## Repaired Quality Contract

The initially established non-terminal **ExecutionRecord** remains the canonical,
non-accountable durable attempt envelope. Its terminal replacement becomes
authoritative only after the terminal JSON has passed the `os.replace()`
publication point and is loaded through the canonical public record boundary.
The repair enforces the following fail-closed accountability **Quality Contract**:

- If replacement fails before publication, `finalize()` raises
  `ExecutionRecordStorageError` and preserves the canonical in-progress,
  non-accountable record.
- If pre-publication cleanup also fails before deletion, the filesystem can
  retain a structurally valid terminal `.execution-record.json.*.tmp` file.
  Such a file cannot be physically guaranteed absent, so
  `load_execution_record()` explicitly rejects that unpublished temporary
  namespace as non-authoritative.
- Normal canonical records and recovery-audit backup candidates retain their
  existing loader behavior. The published-record directory-fsync and
  post-publication cleanup-warning behavior established by [#173](https://github.com/yangliang2/ai_verification/issues/173)
  remains unchanged.

The regression injects replacement failure and a `Path.unlink()` failure before
deletion. It verifies the original canonical bytes remain, exactly one temporary
file remains, that raw temporary JSON is terminal-looking, and the public loader
rejects the temporary path. This is the fail-closed accountability persistence
defect found while independently reviewing [#172](https://github.com/yangliang2/ai_verification/pull/172).
The repair is separate from #171 coverage evidence, as its issue scope requires.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results, all against the tested implementation revision above:

```text
# Exact regression plus published-record durability contracts; warnings fail.
/usr/bin/time -p uv run --extra dev python -W error -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py
PASS: 13 passed in 0.06s; real 0.15s, user 0.10s, sys 0.04s.

# Focused ExecutionRecord, runner CLI, and execution-identity regression suite.
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_cli.py \
  tests/runner/test_execution_identity.py
PASS: 59 passed in 0.52s; real 0.61s, user 0.31s, sys 0.25s.

# Ordinary hermetic repository suite.
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1098 passed, 1 skipped in 50.76s; real 50.89s, user 31.23s,
sys 15.69s.
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
  above. No screenshots, device traces, external logs, coverage reports, or
  generated formal artifacts exist for this local repair.

No device or emulator, Android build or install, package launch, model, remote
oracle, Verification Agent Backend, formal consumer, external-fixture admission,
external snapshot mutation, cohort or population action, or manual step
occurred. Tests use only pytest temporary directories and controlled local
persistence seams.

Known gaps:

- A failed unlink cannot guarantee physical removal of a local temporary file;
  this repair guarantees only that the public ExecutionRecord loader rejects the
  module-owned unpublished temporary namespace.
- The repair does not claim to protect callers that deliberately parse retained
  temporary JSON outside the public loader or against arbitrary external
  filesystem tampering.
- A directory fsync error after terminal publication remains a local durability
  uncertainty; this repair does not prove survival across sudden host or
  filesystem loss.
- The repository-external historical fixture remains skipped by default. Frozen
  M8, M9, and M9-R evidence was neither replayed nor changed.
