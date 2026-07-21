# Independent verification — issue #78

## Review boundary

I independently reviewed GitHub issue #78 and its Agent Brief against the
committed implementation and evidence at `682a1fb`. The implementation commit
is `669ef68`; `682a1fb` adds the API 35 run record. The merge base reviewed was
`bf47ed4`. I made no implementation changes and did not rerun or alter the
device evidence.

Reviewed surfaces included the three Run Specs and two frozen candidate
patches, schedule contract, fixture controller and broadcast receiver,
fail-closed oracle and tests, all six XML journals, command/install/runtime
receipts, evidence/oracle JSON, local and installed APK hash receipts,
environment identity, JUnit reports, checksum inventory, and commit chronology.

## Commands run

From `/Users/peter/projects/ai_verification-issue-78`:

```text
git status --short --branch
git log --oneline --decorate -12
gh issue view 78 --json title,body,labels,comments,state,url
git show --stat --oneline 669ef68
git show --stat --oneline 682a1fb
sha256sum -c docs/runs/2026-07-21-issue-78-deterministic-concurrency/checksums.sha256
../ai_verfication/.venv/bin/pytest tests/bench/test_concurrency_slice.py -q
../ai_verfication/.venv/bin/pytest -q
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/baseline-evidence.json --output /tmp/issue78-baseline-audit.json
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/stale-candidate-evidence.json --output /tmp/issue78-stale-candidate-audit.json
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/destroy-candidate-evidence.json --output /tmp/issue78-destroy-candidate-audit.json
rg -n "onDestroy|onStop|CANCEL|finish\\(|destroyed" bench/fixtures/lifecycle-recovery-app/app/src/main/java/dev/aiverify/lifecyclefixture/ConcurrencyActivity.java docs/runs/2026-07-21-issue-78-deterministic-concurrency
```

Results:

- The focused suite passed 8 tests; the full suite passed 669 tests.
- All 35 entries in the committed checksum inventory verified.
- Recomputed oracle output matched the committed output: the control lane was
  accepted, and each narrow candidate was detected only by its owning schedule.
  CLI exits were 0 for control and 1 for each candidate.
- The three Run Specs have identical actions and assertions. The candidate
  patches narrowly replace stale suppression or post-destroy suppression.
- Ordering receipts are deterministic: acknowledged broadcasts release NEW
  before OLD, each release waits on a five-second completion latch, journals
  are contiguous, and the stale candidate uniquely records `APPLY_STALE` with
  final state `old`.
- Each lane records install success, matching local/pulled-installed APK
  SHA-256 values, distinct APK hashes across lanes, API 35 on
  `emulator-5554`, zero bounded crash/ANR counts, and cleanup exit 0.
- The aggregate preserves both schedule results and promotes incomplete
  schedule evidence over a detected defect, so one domain does not mask the
  other in the tested cases.

## Fail-closed finding

The lifecycle schedule is not independently attributable to an Android
lifecycle transition or cancellation observation. `ConcurrencyActivity` has no
`onDestroy` (or other lifecycle callback) that records destruction. Instead,
the exported control receiver invokes `command("DESTROY")`; that method sets
the controller's `destroyed` flag and immediately appends both `DESTROY` and
`CANCEL` before calling `activity.finish()`. No cancellation primitive is
invoked or observed: the worker remains blocked on its latch and is deliberately
released afterward. The raw receipt contains only the successful control
broadcast and the same self-authored SharedPreferences journal; it contains no
Activity lifecycle callback, lifecycle state query, cancellation callback, or
other independent receipt proving that destruction completed before
`RELEASE_PENDING`.

Consequently, the destroy candidate proves that a boolean controlled by the
test command changes the fixture's application decision, but it does not prove
the Agent Brief's required ordering of actual Activity destruction,
cancellation observation, and later work application. The machine oracle cannot
detect this evidence gap because it trusts the fixture-authored `DESTROY` and
`CANCEL` names as authoritative.

Additional limitations reinforce, but are not needed for, the fail-closed
decision: the oracle does not validate `source_commit`, patch identity, package
identity, device fingerprint, tool versions, or command acknowledgement from
the evidence object; candidate lanes also omit an `installed-path.txt` receipt.
The unit suite has no direct timeout-event/deadlock case even though timeout
handling is an explicit acceptance item. Scope claims in the run README are
otherwise appropriately limited and make no detection-rate, Goldset, upstream,
or general concurrency-correctness claim.

## Current conclusion

`non_accountable`

The ordering/stale-result half is locally auditable, but the required lifecycle
and cancellation half lacks authoritative evidence. Because both schedules are
mandatory and missing lifecycle evidence must fail closed, the issue-level run
cannot currently support completion.
