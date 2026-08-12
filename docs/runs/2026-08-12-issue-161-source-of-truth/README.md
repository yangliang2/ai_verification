# Issue #161 — post-#158 source-of-truth reconciliation

Status: implementation and local verification complete on
`issue-161-source-of-truth-reconciliation`. This run record is durable only after
the branch commit containing it is merged.

## Objective and frozen source

- Issue: `#161` (`bug`, `ready-for-agent`).
- Base revision: `9dfb19e2afa3f4b02a87d9c43a1cd05913174583`.
- Base tree: `8b832def6da1bd54dc1326c025589c7e078c5d1c`.
- Tested implementation/evidence revision:
  `697025168c9c2d73bc475fa8989f9200cb065eef`.
- Tested implementation/evidence tree:
  `51b6b4bf9096bc13ad2349893bbdcdc38d006773`.
- The final evidence commit is the commit that contains this run record and its
  checksum ledger; its exact merged identity is recorded in the Issue #161
  completion comment.
- Source state: PR #160 and #158 were merged/closed, while current guidance still
  described #158 as remaining forward work.
- Claim boundary: documentation and source-of-truth regression only.

## Implemented acceptance criteria

- `CONTEXT.md`, `README.md`, `HANDOFF.md`, and the current capability claim matrix
  now record #158 as completed through PR #160 at `9dfb19e`.
- The documented capability is limited to future target-specific preclaim,
  `terminal_absence_receipt` inventory binding, and separate
  `formal_attempt_reconciled`/`runtime_holdout_executed` semantics.
- Handoff guidance states that, apart from this reconciliation issue, the prior
  capability queue is exhausted and no new formal population or rerun is approved.
  White-box coverage requires separate triage.
- A regression test requires all four current source-of-truth surfaces to retain
  the completion markers and rejects the known stale forward-work phrases.
- Frozen #137, #154, and #157 evidence was not edited, invoked, or reinterpreted.

## Verification

Tools:

- macOS 26.3 (25D125)
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15
- pytest 9.1.1

Commands and results:

```text
/usr/bin/time -p uv run --extra dev python -m pytest tests/bench/test_current_claim_matrix.py -q
EXPECTED RED: 1 failed, 5 passed; README.md lacked the required PR #160 completion marker; real 5.94s.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/bench/test_current_claim_matrix.py
PASS: 7 passed in 0.01s; real 0.10s, user 0.07s, sys 0.02s.

/usr/bin/time -p uv run --extra dev python -m compileall -q src tests
PASS: exit 0; real 0.26s, user 0.18s, sys 0.03s.

git diff --check
PASS: exit 0.

uv run --extra dev python -m pytest --collect-only -q | awk -F': ' '{sum += $2} END {print sum}'
PASS: 1018 tests collected.

/usr/bin/time -p uv run --extra dev python -m pytest -q
ENVIRONMENT FAILURE: 1017 passed and 1 failed; real 89.02s, user 32.64s, sys 15.98s.
The sole failure was test_frozen_target_specific_mismatch_is_side_effect_free.
Its hard-coded external directory /private/tmp/m9-r3-snapshot-b existed, so the
test did not skip, but that directory had no .git entry and source identity failed
before the asserted plan mismatch.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -k 'not frozen_target_specific_mismatch_is_side_effect_free'
PASS: 1017 passed, 1 deselected in 48.07s; real 48.20s, user 32.79s, sys 16.79s.
```

## External/manual execution

No emulator, physical device, Android build/install, model invocation, formal
consumer, namespace claim, mapping release, oracle, Falsification Review, or
manual UI step was performed. The external stale snapshot was inspected read-only
and was not repaired, moved, or deleted.

## Artifact inventory and known gap

- `README.md` — human-readable commands, results, scope, and known gap.
- `verification.json` — machine-readable verification and mutation inventory.
- `checksums.sha256` — checksum ledger for the two record artifacts above.

Known gap: the unmodified external-fixture test uses directory existence as its
skip gate even when the directory is not a Git repository. This issue does not
change that test or the external fixture. All other 1,017 collected tests passed.
