# Independent verification for issue #74

Date: 2026-07-20  
Verification agent: `issue74_independent_verifier`  
Reviewed commit: `07c9119da2f5e4affea74e4e77f96f78dd806d5d`

## Scope

Final bounded audit of the performance/resource-pressure and Intent-security slice,
including the last corrective runtime receipts. I reviewed the committed code, three
lane identities and receipts, FrameMetrics/gfxinfo evidence, security scenarios,
machine oracles, checksum manifest, and tests. I did not change implementation code or
rerun mutable device scenarios.

## Exact commands and results

```text
git status --short --branch
# clean at reviewed commit

git rev-parse HEAD
# 07c9119da2f5e4affea74e4e77f96f78dd806d5d

git show --stat --oneline 07c9119
# 7 files changed, 111 insertions(+), 90 deletions(-)

sha256sum -c docs/runs/2026-07-20-issue-74-performance-intent/checksums.sha256
# all 51 manifest entries: OK

/Users/peter/projects/ai_verfication/.venv/bin/pytest -q tests/bench/test_performance_intent_slice.py
# 9 passed

/Users/peter/projects/ai_verfication/.venv/bin/pytest -q
# exit 0; all collected tests passed

/Users/peter/projects/ai_verfication/.venv/bin/pytest --collect-only
# 661 tests collected in 0.11s

# Regenerated each lane output:
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.performance_intent_slice --contract <contract> \
  --evidence <lane-evidence> --output <temporary-output>
diff -u <committed-output> <temporary-output>
# baseline, performance candidate, and security candidate all matched byte-for-byte
```

## Findings

- Each lane has a distinct APK SHA-256, and its local and pulled installed APK hashes
  match: baseline `cad80a63...72a98`, performance candidate
  `3999b340...d17d3`, and security candidate `55ac08cc...6d99`.
- Startup, FrameMetrics, resource, security, and runtime receipts are lane-bound to
  those hashes. FrameMetrics retains frame count and maximum duration. The performance
  candidate has a 967 ms maximum and corresponding Android gfxinfo frozen-frame
  evidence; its cold-start median also exceeds the registered 1000 ms threshold.
  Baseline and security-candidate performance measurements remain below threshold.
- Every lane's security receipt exercises malformed extras, nested Intent behavior,
  the exported gateway, non-exported component denial, and immutable one-shot
  PendingIntent behavior. The security candidate alone reaches the package-confined
  sensitive marker; the security oracle detects that violation while retaining the
  separate performance result.
- Resource receipts contain UTC timestamps, exact setup/cleanup descriptions, exit
  code zero, and observed storage LOW/NORMAL and battery 10/100 states.
- Runtime receipts now contain bounded UTC start/end times, lane APK hashes, the exact
  serial-scoped crash and ANR query descriptions, exit code zero, explicit
  `crash_count=0` and `anr_count=0`, and `Wake Locks: size=0`.
- The validator requires every runtime marker and rejects incomplete receipts. The
  oracles also require matching local/installed/package identities, named receipt
  paths, complete scenario sets, parseable metrics, successful setup/cleanup, and both
  independent domains. Focused tests exercise missing receipt files and incomplete
  runtime receipts.
- All checksum entries verify, all three machine outputs reproduce from committed
  evidence, 9 focused tests pass, and the full 661-test suite passes.

## Limitations

This is bounded evidence from one named API 35 emulator and three fixture APKs.
FrameMetrics maximum duration is the registered frozen-frame decision metric; the
slice is not a fleet benchmark, precise energy-attribution study, general penetration
test, or third-party application assessment. No detection-rate, Goldset, upstream
acceptance, or upstream-impact claim is made.

## Current fail-closed conclusion

`locally_supported`

All previously identified accountability blockers are closed in the reviewed commit.
The baseline is supported, each narrow candidate is rejected by its owning oracle,
the unaffected domain remains separately evaluated, and the retained evidence is
bound to the corresponding local and installed APK identity.
