# Independent verification for issue #74

Date: 2026-07-20  
Verification agent: independent agent `issue74_independent_verifier`  
Reviewed commit: `70de2d1ad1ec82dbe01425bcd6499dc1c0e2fc4c`

## Scope

This audit reviewed issue #74 and its Agent Brief, the committed implementation,
the three Run Specs and two candidate patches, both machine oracles, all committed
raw artifacts, the checksum manifest, and repository status. It did not modify the
implementation or rerun mutable device scenarios.

## Exact commands and results

```text
git status --short --branch
# ## issue-74-performance-intent-security; no tracked or untracked changes

git show --stat --oneline --decorate 70de2d1
# 70de2d1 Add performance and Intent security verification slice
# 38 files changed, 1138 insertions(+)

gh issue view 74 --comments
# Agent Brief retrieved and audited

sha256sum -c docs/runs/2026-07-20-issue-74-performance-intent/checksums.sha256
# all 23 listed files: OK

/Users/peter/projects/ai_verfication/.venv/bin/pytest -q tests/bench/test_performance_intent_slice.py
# 7 passed

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.performance_intent_slice \
  --contract bench/capability-slices/performance-intent-security/contract.json \
  --evidence docs/runs/2026-07-20-issue-74-performance-intent/baseline-evidence.json \
  --output /tmp/issue74-baseline-oracle.json
diff -u docs/runs/2026-07-20-issue-74-performance-intent/baseline-oracle.json \
  /tmp/issue74-baseline-oracle.json
# exit 0; regenerated baseline output matched byte-for-byte

git apply --check bench/capability-slices/performance-intent-security/patches/frozen-frame.patch
git apply --check bench/capability-slices/performance-intent-security/patches/unsafe-nested-intent.patch
# both exit 0

# Parsed the first HISTOGRAM line from each committed framestats artifact.
# baseline: frames >=700 ms = 0; maximum nonzero bucket = 57 ms
# performance candidate: frames >=700 ms = 0; maximum nonzero bucket = 32 ms

git rev-parse HEAD
# 70de2d1ad1ec82dbe01425bcd6499dc1c0e2fc4c
```

An initial attempt using unqualified `pytest` and `python` failed because neither
command was installed on `PATH`; the commands above use the repository's documented
virtual environment. The Python module command additionally required `PYTHONPATH=src`.

## Findings

1. The implementation has two separate domain judges and a fail-closed aggregate.
   Unit tests cover the baseline, each narrow candidate, missing-domain non-masking,
   cleanup failure, wakelock leakage, startup violation, crash handling, scenario-set
   mismatch, and malformed numeric metrics.
2. The two patches are narrow and apply cleanly: one changes the bounded main-thread
   sleep from 0 to 900 ms; the other forwards only a fixture-confined nested Intent.
   The three Run Specs use the same action and assertion lists.
3. The baseline startup artifact supports three cold starts (231, 508, and 253 ms).
   Storage and battery artifacts visibly show LOW-to-NORMAL and level-10-to-level-100
   transitions. The component artifact shows an exported entry launch and a
   `SecurityException` for direct shell launch of the non-exported sensitive Activity.
   PendingIntent preferences show the safe action and denied replay. Layout artifacts
   show baseline nested rejection and the candidate reaching the harmless sensitive
   marker.
4. The performance-candidate machine evidence is contradicted by its named raw frame
   artifact. JSON reports one frozen frame with maximum 902 ms, while committed
   `performance-candidate-framestats.txt` reports no frame in any bucket at or above
   700 ms and a maximum nonzero CPU histogram bucket of 32 ms. The 902 ms value appears
   only as application-measured callback work in shared preferences; it is not a raw
   frame-timing measurement. `performance-candidate-gfxinfo.txt` likewise does not
   report a 902 ms CPU frame. The machine oracle trusts the hand-authored JSON number
   and does not parse or bind the raw frame artifact, so the claimed frozen-frame
   rejection is not auditable against the committed rendering evidence.
5. Effective execution identity is incomplete for candidate lanes. Only one APK
   checksum is committed, and that same checksum is copied into baseline, performance-
   candidate, and security-candidate evidence. Applying either source patch necessarily
   produces a distinct candidate artifact, but no per-lane candidate APK checksum,
   installed-package APK digest, build receipt, or mapping from patch to installed APK
   is retained. The security oracle merely checks that a hash string is present and
   does not compare it with a preregistered or measured lane identity; the performance
   judge does not consume package identity at all.
6. Candidate evidence reuses baseline startup, resource-pressure, wakelock, and
   unaffected-domain scenario values without per-lane raw command receipts. The raw
   resource files concatenate observations but omit the exact commands, timestamps,
   and exit statuses asserted in JSON. Thus the requirement that both domains remain
   independently evaluated for each candidate is not demonstrably bound to those
   executions.
7. The checksum manifest is internally valid, but checksums establish file integrity,
   not truth of the JSON-to-raw-artifact mappings above. The committed empty
   `performance-candidate-logcat.txt` also cannot establish a serial-scoped candidate
   crash/ANR observation window by itself.

## Known gaps required for an accountable rerun

- Capture frame timing that directly demonstrates the candidate threshold violation,
  or change the preregistered metric and oracle to the actual bounded callback metric;
  retain the parser output and raw source together.
- Build, hash, install, and record a distinct APK for every lane, with patch digest,
  installed package identity, device serial, and timestamps bound to each verdict.
- Retain per-lane command receipts for startup, resource setup/cleanup, wakelocks,
  crashes/ANRs, and all security scenarios; derive machine evidence from those receipts
  rather than copying unaffected baseline values.
- Make each oracle validate artifact identity and reject contradictory raw/structured
  evidence.

## Fail-closed conclusion

`non_accountable`

The committed artifacts demonstrate useful local behavior, but the contradictory
performance measurement and missing candidate execution identities prevent an
auditable binding from matched patches and installed APKs to the three machine verdicts.
No broader effectiveness or upstream claim is made.
