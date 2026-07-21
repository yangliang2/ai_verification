# Issue #78 deterministic concurrency run

This run binds source commit `d5d1e3b` to three matched API 35 lanes on
`emulator-5554`. Each lane executes two explicit-barrier schedules. Control
broadcasts return only after the released worker reaches its completion latch,
with a five-second bound; sleeps and retries do not determine the event order.

Results:

- Baseline: `locally_supported`. NEW completed and applied before OLD; OLD was
  rejected stale. Pending work released after DESTROY/CANCEL was rejected.
- Stale candidate: `locally_rejected`. The complete ordering journal ended in
  `APPLY_STALE` and final state `old`; the lifecycle schedule remained supported.
- Destroy candidate: `locally_rejected`. The complete lifecycle journal ended in
  `APPLY_AFTER_DESTROY`; the ordering schedule remained supported.

All six schedules have contiguous monotonic journals, exactly one decision and
terminal event, result-code-0 barrier broadcasts, zero bounded crash/ANR counts,
and cleanup exit 0. Local and pulled-installed APK hashes match within each lane
and are distinct across lanes. The device fingerprint, API, adb, Java, Python,
source identity, raw commands, journals, evidence JSON, oracle JSON, and checksum
inventory are retained here.

Verification commands:

- `../ai_verfication/.venv/bin/pytest tests/bench/test_concurrency_slice.py -q`
  — 8 passed.
- `../ai_verfication/.venv/bin/pytest -q`
  — 669 passed.
- `cd bench/fixtures/lifecycle-recovery-app && ./gradlew :app:assembleDebug`
- `PYTHONPATH=src ../ai_verfication/.venv/bin/python -m aiverify.bench.concurrency_slice --contract ... --evidence ... --output ...`
- Serial-scoped `adb shell am start`, acknowledged `adb shell am broadcast`,
  `run-as ... cat shared_prefs/issue78.xml`, bounded logcat queries, APK pull,
  and SHA-256 commands recorded under each lane.

This is a bounded local result for one fixture and one API 35 emulator. It does
not establish stress/fuzz coverage, general Android concurrency correctness,
multi-process/database/kernel correctness, a detection rate, Goldset status, or
upstream acceptance.

The checksum inventory contains 35 artifacts. Exactly one independent
Verification Agent audit is added only after this evidence commit so its review
can name an immutable source/evidence revision.
