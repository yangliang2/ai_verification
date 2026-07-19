# Final local verification before code review

Date: 2026-07-19 (America/New_York)

## Focused Python regression

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/peter/projects/ai_verfication/.venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q \
  tests/bench/test_lifecycle_recovery.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_system_events.py \
  tests/runner/test_journey.py \
  tests/runner/test_cli.py \
  tests/runner/test_evidence.py
```

Result: `155 passed in 0.22s`.

## Full Python regression

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/peter/projects/ai_verfication/.venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q
```

Result: `542 passed in 17.86s`.

## Fixture rebuild and archive identity

```sh
bench/fixtures/lifecycle-recovery-app/gradlew \
  -p bench/fixtures/lifecycle-recovery-app \
  :app:assembleDebug --no-daemon
sha256sum \
  bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk
cmp -s \
  bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-1/apk/app-debug.apk
```

Result: `BUILD SUCCESSFUL in 2s`; 33 tasks up to date; SHA-256
`1a8cc170e310417f37447dd68bea1de853b1f8ed2d11d962a3662ba5cef85c0c`;
`cmp` exit 0.

## Durable oracle replay

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.lifecycle_recovery \
  --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-1 \
  --contract bench/capability-slices/lifecycle-recovery/contract.json \
  --output /tmp/issue-71-baseline-oracle-replay.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.lifecycle_recovery \
  --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1 \
  --contract bench/capability-slices/lifecycle-recovery/contract.json \
  --output /tmp/issue-71-candidate-oracle-replay.json
```

Results:

- baseline: exit 0, `locally_supported / correct_restoration`, accountable;
- candidate: exit 1, `locally_rejected / stale_state`, accountable.

## Lane checksum inventories

```sh
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-1
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1
```

Result: both `checksum inventory verified`; baseline 70 entries, candidate 73.

## Candidate and matched-spec identity

```sh
cmp -s \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1/applied-host.patch \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1/identity/host.patch
git apply --numstat \
  bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
git apply --numstat \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1/identity/host.patch
sha256sum bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml
sed '/^diff: /d' \
  bench/capability-slices/lifecycle-recovery/run-specs/candidate.yaml | sha256sum
```

Result: captured/applied candidate patches are byte-identical (`cmp` exit 0);
both patch forms report one insertion and one deletion in `StateStore.java`;
matched Run Spec hashes both equal
`3a23e226c11c68834a47dfae64941e9c5aec5ca896932a44caa98c4083c2c827`.

## Independent conclusion validation

See `../independent-verification/validation.txt`. Result: Draft 2020-12 schema
passed; exactly one authoritative conclusion; `locally_supported` and
accountable; 11 checks passed; final output matches the last agent message; one
completed turn.
