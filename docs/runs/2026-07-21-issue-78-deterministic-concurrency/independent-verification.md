# Independent verification — issue #78

## Review boundary

I am the same sole independent Verification Agent that performed the initial
audit. I re-audited GitHub issue #78 and its Agent Brief against corrected,
committed state through `51fcc7b` in
`/Users/peter/projects/ai_verification-issue-78`. The reviewed chronology is:

- `669ef68` — initial deterministic concurrency slice;
- `682a1fb` — initial API 35 evidence;
- `d5d1e3b` — bind destruction/cancellation evidence to `onDestroy`;
- `ba84b1b` — rebuild all three lanes and record corrected API 35 evidence;
- `51fcc7b` — refresh the 43-artifact checksum inventory.

The merge base is `bf47ed4`. I inspected source and patch chronology, all three
Run Specs, schedule contract, fixture/controller, oracle and tests, six raw XML
journals, command/install/runtime receipts, evidence and oracle JSON, local and
pulled-installed APK identity, source and patch identity, installed paths,
environment identity, JUnit reports, checksum inventory, and scope claims. I
did not modify implementation code, rerun the device journeys, or commit this
report.

## Commands run

```text
git status --short --branch
git log --oneline --decorate -8
git show --stat --oneline d5d1e3b
git show --stat --oneline 51fcc7b
sha256sum -c docs/runs/2026-07-21-issue-78-deterministic-concurrency/checksums.sha256
wc -l docs/runs/2026-07-21-issue-78-deterministic-concurrency/checksums.sha256
../ai_verfication/.venv/bin/pytest tests/bench/test_concurrency_slice.py -q
../ai_verfication/.venv/bin/pytest -q
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/baseline-evidence.json --output /tmp/issue78-baseline-reaudit.json
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/stale-candidate-evidence.json --output /tmp/issue78-stale-candidate-reaudit.json
PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract bench/capability-slices/deterministic-concurrency/contract.json --evidence docs/runs/2026-07-21-issue-78-deterministic-concurrency/destroy-candidate-evidence.json --output /tmp/issue78-destroy-candidate-reaudit.json
```

Results:

- Focused tests: 8 passed.
- Full tests: 669 passed.
- Checksum inventory: 43 of 43 entries verified.
- Recomputed CLI outputs exactly matched the committed lane outcomes; exit 0
  was produced for the control and exit 1 for each deliberately defective lane.
- Each lane's local APK SHA-256 exactly matches its pulled-installed APK
  SHA-256. The three lane hashes are distinct. All lanes retain package install
  paths, install success, API 35 / `emulator-5554`, fingerprint and tool
  versions, source commit `d5d1e3b`, clean expected source state, patch identity,
  bounded runtime windows, zero crash/ANR counts, and cleanup exit 0.

## Audit findings

The original lifecycle attribution gap is corrected. The `DESTROY` command now
only requests `Activity.finish()`. Android's actual
`ConcurrencyActivity.onDestroy()` calls `onActivityDestroyed`, which changes
the lifecycle/cancellation state, appends `DESTROY` and `CANCEL`, and completes
a dedicated latch. `AWAIT_DESTROY` uses an asynchronous broadcast receiver and
waits up to five seconds on that latch. In every raw destroy receipt the
`DESTROY`, `AWAIT_DESTROY`, and `RELEASE_PENDING` broadcasts all return result
0, while the XML journal orders lifecycle callback events before pending-work
release. Thus the fixture no longer treats the request to finish as proof of
completed destruction.

The work is intentionally allowed to complete after lifecycle cancellation so
the oracle can distinguish safe suppression from the narrow post-destroy
candidate. This is a bounded fixture cancellation boundary, not a claim that a
Java thread was interrupted. The control rejects the late application; the
post-destroy candidate alone records the forbidden application. Separately,
the explicit NEW/OLD latches deterministically release NEW first, the control
rejects OLD as stale, and the stale candidate alone records the overwrite and
final state `old`. There are no arbitrary sleeps or retry-dependent ordering
decisions.

The journals have contiguous monotonic sequences, exact schedule identity,
one required decision and one terminal event, declared partial orders, and
expected terminal state. Missing/duplicate/unknown/out-of-order events,
identity mismatch, unfinished execution, timeout, cleanup failure, and raw
receipt mismatch fail closed in the implementation and focused tests. The lane
aggregate retains both schedule results and promotes any non-accountable
schedule over a detected candidate violation, preventing domain masking.

Raw validation binds each structured journal back to XML, APK hashes to local
and installed receipts, source commit and clean expected tree to source
receipts, candidate names to checksummed frozen patches, and runtime accounting
to bounded receipts. The command receipts and installed-path artifacts are
also present for all lanes. The evidence is therefore sufficient for the
bounded local claims in the Agent Brief.

Known limitations are accurately stated: this is one purpose-built fixture on
one API 35 emulator, not stress/fuzz coverage, a general scheduler, Java-thread
interruption proof, database/multi-process/kernel correctness, detection-rate
or Goldset evidence, or upstream acceptance. No such broader claim is made.

## Current conclusion

`locally_supported`

The control behavior is supported, both narrow injected defects are
independently rejected by their owning schedules, the lifecycle correction is
authoritatively ordered through `onDestroy` and `AWAIT_DESTROY`, and the
committed identity/evidence chain is complete for the stated local scope.
