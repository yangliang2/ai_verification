# Final local verification

Date: 2026-07-19 (America/New_York)

## Python regression

~~~sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -o addopts='' -q --tb=short
~~~

Result: exit 0; 545 passed in 16.48 seconds.

The prior post-review run in tdd/40-post-review-full-suite-green.txt also
records 545 passed in 17.63 seconds, git diff --check exit 0, and compileall
exit 0. That diff check covered the authored code state. After raw host.patch
evidence was staged, an all-path check reported trailing spaces embedded in
captured log lines; those immutable evidence bytes were preserved. The authored
source and documentation paths pass a scoped staged check.

## Durable oracle replay

~~~sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-baseline-oracle-final.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-candidate-oracle-final.json
~~~

Results:

- baseline: exit 0, accountable locally_supported / correct_restoration;
- candidate: exit 1, accountable locally_rejected / stale_state. Exit 1 is the
  expected rejected-product result.

## Lane inventories

~~~sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2
~~~

Result: both checksum inventories verified; 71 baseline entries and 72
candidate entries.

## Evidence review

All ExecutionRecord checkpoint, Journey, system-event, verdict, gate, and
provenance references are run-relative. Both process-death receipts record a
launcher background state, process absence, target foreground state after
relaunch, and disjoint before/after PIDs. Both backup receipts record backup,
clear, restore, post-restore process, and cleanup success.

Each lane has seven screenshots, seven layouts, and seven logcats. The final
baseline/candidate screenshots were inspected visually. A target-package scan
across all fourteen logcats produced no FATAL EXCEPTION, ANR, Process, or Fatal
signal match.

See matched-input-audit.json for the disclosed docs-only host-patch difference:
matched executable inputs are true; strict entire-worktree equality is false.
