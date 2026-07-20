# Independent verification for issue #74

Date: 2026-07-20
Verification agent: `issue74_independent_verifier`
Reviewed corrective commit: `6e3d8437d356c9f8e8a279662d1088e16ed337d0`

## Scope

This replaces the earlier audit. I reviewed issue #74 and its Agent Brief, the
corrected implementation, candidate patches, three lane records, machine evidence,
oracle outputs, checksums, and repository status. I did not alter implementation code
or perform a new mutable device run.

## Exact commands and results

```text
git status --short --branch
# clean at the reviewed commit

git rev-parse HEAD
# 6e3d8437d356c9f8e8a279662d1088e16ed337d0

git show --stat --oneline 6e3d843
# 33 files changed, 461 insertions(+), 32 deletions(-)

sha256sum -c docs/runs/2026-07-20-issue-74-performance-intent/checksums.sha256
# all 46 committed entries: OK

/Users/peter/projects/ai_verfication/.venv/bin/pytest -q tests/bench/test_performance_intent_slice.py
# 7 passed

# Compared the first field of local-apk.sha256 and installed-apk.sha256 per lane.
# baseline local == installed:
# 8379d3b194dd746638d84c08a29627b83d42585a2fd965dde6c603a046f54c4a
# performance candidate local == installed:
# c762ad2798980dfec6e2716066bc31631bad5c41b9a08d0ed8aa8e6b25be832e
# security candidate local == installed:
# e621ba0ed05792b66dc009c9dde1f8ff1b31531bb1a9831b93c179913abd5e79

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.performance_intent_slice --contract <contract> \
  --evidence <each-lane-evidence> --output <temporary-output>
diff -u <each-committed-oracle> <temporary-output>
# all three regenerated outputs matched byte-for-byte

git apply --check bench/capability-slices/performance-intent-security/patches/frozen-frame.patch
git apply --check bench/capability-slices/performance-intent-security/patches/unsafe-nested-intent.patch
# both exit 0

rg -n "malformed|nested rejected|SecurityException|SAFE_TOKEN|replay|Wake Locks|crash|ANR" \
  docs/runs/2026-07-20-issue-74-performance-intent/lanes
# lane-local hits: PendingIntent preferences in all lanes and wakelocks in the
# security candidate; no lane-local malformed/nested-rejection, component-denial,
# crash, or ANR receipt
```

## Corrected evidence verified

- The performance defect is now demonstrated by Android frame evidence. Candidate
  `gfxinfo.txt` has nonzero 900 ms and 950 ms CPU histogram buckets, with the upper
  percentiles at 950 ms. FrameMetrics preferences independently record a 980 ms total
  frame and 901 ms draw workload. Candidate cold starts are 1126, 1101, and 1110 ms,
  beyond the preregistered 1000 ms boundary.
- Baseline FrameMetrics records a 67 ms maximum and the security candidate records
  140 ms. Their cold-start samples remain below the boundary.
- Each lane has a distinct APK digest, and every lane's local and pulled installed APK
  digests match. Both narrow patches apply cleanly.
- Each lane has startup and storage/battery observations. The security candidate also
  has lane-local wakelock output and a layout proving its package-confined nested
  Intent reached the harmless sensitive marker.
- The manifest is internally valid, focused tests pass, and machine outputs regenerate
  deterministically from their JSON inputs.

## Remaining accountability blockers

1. The unaffected Intent-security domain is not demonstrated per lane. Baseline and
   performance-candidate lane directories contain PendingIntent preferences, but no
   lane-local receipt for malformed-extra rejection, nested-Intent rejection, exported
   gateway access, or non-exported sensitive-component denial. These scenarios are
   marked true in JSON without a raw execution record bound to the corresponding new
   APK digest. Older global files predate the corrected lane identities.
2. The security judge checks only that its hash is a non-empty string. It does not
   compare it with the lane's local and installed APK digests or consume scenario
   receipts. The performance judge likewise does not bind package identity or raw
   artifacts. Regeneration therefore proves JSON processing, not provenance.
3. Wakelock and crash/ANR observations are not retained for every corrected lane. Only
   the security candidate has lane-local wakelock output, while all JSON files assert
   an empty fixture-held list and zero crashes/ANRs.
4. Resource files show the expected LOW/NORMAL and battery 10/100 states, but omit the
   exact commands and individual exit codes asserted in JSON. The baseline receipt
   also lacks the timestamp present in the two candidate receipts.
5. Baseline and security-candidate JSON claim total/slow/frozen frame counts, while
   their lane-local FrameMetrics files retain only maximum duration. The maximum
   supports the threshold observation, but the exact counts are not derivable.

## Required closure

- Retain all six security scenarios separately for every APK lane, with exact command,
  timestamp, exit status, expected/observed result, and APK digest.
- Retain per-lane wakelock and scoped crash/ANR windows.
- Make both judges validate lane identity and artifact checksums and reject missing or
  contradictory bindings.
- Preserve per-command resource receipts and actual FrameMetrics counts when asserted.

## Current fail-closed conclusion

`non_accountable`

The corrective commit closes the frame-timing contradiction and APK hash reuse, but
missing lane-bound unaffected-security and runtime evidence still prevents an
end-to-end audit of both domains. No broader effectiveness or upstream claim is made.
