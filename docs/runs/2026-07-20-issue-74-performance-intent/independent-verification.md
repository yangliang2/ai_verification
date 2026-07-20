# Independent verification for issue #74

Date: 2026-07-20
Verification agent: `issue74_independent_verifier`
Reviewed commit: `7d81c8b19daba8cb5436b2ec123a06b819c39e02`

## Scope

Final bounded re-audit of the blockers from the prior report: lane-bound security,
runtime, and resource receipts; timestamps and exit codes; FrameMetrics derivation;
APK identity; oracle enforcement; checksums; and focused tests. No implementation was
changed and no mutable device scenario was rerun.

## Exact commands and results

```text
git status --short --branch
# clean at reviewed commit

git rev-parse HEAD
# 7d81c8b19daba8cb5436b2ec123a06b819c39e02

git show --stat --oneline 7d81c8b
# 31 files changed, 449 insertions(+), 178 deletions(-)

sha256sum -c docs/runs/2026-07-20-issue-74-performance-intent/checksums.sha256
# all 52 entries: OK

/Users/peter/projects/ai_verfication/.venv/bin/pytest -q tests/bench/test_performance_intent_slice.py
# 8 passed

# Regenerated all three outputs with:
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.performance_intent_slice --contract <contract> \
  --evidence <lane-evidence> --output <temporary-output>
diff -u <committed-output> <temporary-output>
# all three matched byte-for-byte

# Compared local and installed hashes for each lane.
# baseline: cad80a6383a138f76ecc8bc75e3aef903ce6a11c025d55d05d60513104772a98
# performance: 3999b340fce745ea89c54c449651dfe6f202a9d40f3f741d7c049003e2cd17d3
# security: 55ac08cc455750ffd559a95942492a62017798435bdcb16cfa4775c740b86d99
# each pair matched and all three lane hashes were distinct

rg -n "crash|ANR|anr|exit|command|cmd|logcat" \
  docs/runs/2026-07-20-issue-74-performance-intent/lanes/*/runtime-receipts.txt
# no matches
```

## Verified closures

- Every lane now has timestamped, APK-bound security receipts. They show malformed
  rejection, nested rejection or the intended candidate forwarding, exported gateway
  launch, non-exported direct-launch denial with `SecurityException` and exit 255, and
  immutable one-shot PendingIntent state.
- Resource receipts are timestamped and APK-bound and contain setup/cleanup commands,
  exit code zero, and observed storage LOW/NORMAL and battery 10/100 states.
- FrameMetrics preferences now retain `frame_count` and maximum duration. The
  performance candidate records 12 frames and 967 ms maximum; Android gfxinfo also
  contains the frozen-frame violation. Baseline and security candidate retain their
  own counts and sub-threshold maxima.
- Local and pulled installed APK digests match per lane and differ across lanes.
- Both oracles now require matching structured APK identities and named receipt paths;
  the CLI additionally rejects missing receipt files. Tests cover those fail-closed
  checks. The checksum manifest and regenerated oracle outputs are consistent.
- Performance and Intent-security conclusions remain separate, and neither masks a
  non-accountable peer domain.

## Actual remaining blocker

All three `runtime-receipts.txt` files are timestamped and APK-bound and demonstrate
the wakelock state, but none records a crash/ANR observation command, its exit status,
or an explicit zero result. The evidence JSON files nevertheless assert `crashes: 0`
and `anrs: 0`. The oracle checks only that the runtime receipt path exists; it does not
validate receipt content. An empty crash/ANR query cannot be distinguished from a
query that was never run, so the acceptance requirement that crashes and ANRs fail
closed remains unauditable for all three lanes.

To close this, retain per-lane commands and bounded observation windows for fixture
crashes and ANRs, with explicit exit codes and zero/nonzero counts, then make the
oracle validate those structured receipts rather than path existence alone. A smaller
limitation is that slow/frozen counts are asserted in JSON while FrameMetrics stores
only total count and maximum duration; the maximum is sufficient for the registered
700 ms threshold, but not for independently reconstructing every count field.

## Current fail-closed conclusion

`non_accountable`

The security, resource, frame, and APK-identity gaps are materially closed, but the
missing crash/ANR observation evidence leaves a required fail-closed runtime condition
unbound. No broader effectiveness or upstream claim is made.
