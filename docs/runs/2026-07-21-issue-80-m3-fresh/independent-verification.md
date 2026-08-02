# Independent verification — issue #80

## Review boundary

I am the sole independent Verification Agent for issue #80. I audited committed
revision `e81f2ce461c558aec94aba59c972d26915effddc` in
`/Users/peter/projects/ai_verification-issue-80`. I did not modify implementation
or original evidence and did not rerun device journeys. This report is the only
file I created, and I did not commit it.

The review covered the preregistered manifest, append-only invocation ledger,
all formal attempt directories and checksummed attempt records, final audit,
package and run-root checksum inventories, application/deployment identity,
device/tool/model identity, JUnit records, the fail-closed aggregation changes,
and their focused tests.

## Exact commands and results

```text
git status --short --branch
git rev-parse HEAD
git log --oneline -8
git show --stat --oneline e81f2ce461c558aec94aba59c972d26915effddc

(cd docs/runs/2026-07-21-issue-80-m3-fresh && sha256sum -c checksums.sha256)
# 769/769 entries OK

for pkg in anr oversized query swallowed search; do
  (cd docs/runs/2026-07-21-issue-80-m3-fresh/$pkg &&
    sha256sum -c checksums.sha256)
done
# anr 121/121; oversized 157/157; query 157/157;
# swallowed 157/157; search 151/151; total 743/743 entries OK

PYTHONPATH=src ../ai_verfication/.venv/bin/pytest \
  tests/bench/test_m3_reliability.py -q
# 87 passed

PYTHONPATH=src ../ai_verfication/.venv/bin/pytest -q
# 674 passed

PYTHONPATH=src WIKIPEDIA_SOURCE=/Users/peter/hosts/wikipedia \
  ../ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-issue80.yaml audit \
  --environment docs/runs/2026-07-21-issue-80-m3-fresh/audit-environment.json \
  --json-output /tmp/issue80-independent-audit.json \
  --markdown-output /tmp/issue80-independent-audit.md
# exit 0; all six audit criteria passed

xmllint --xpath 'string(/testsuites/testsuite/@tests)' \
  docs/runs/2026-07-21-issue-80-m3-fresh/focused-junit.xml
xmllint --xpath 'string(/testsuites/testsuite/@failures)' ...
xmllint --xpath 'string(/testsuites/testsuite/@errors)' ...
xmllint --xpath 'string(/testsuites/testsuite/@skipped)' ...
xmllint --xpath 'string(/testsuites/testsuite/@time)' ...
# focused: tests=87, failures=0, errors=0, skipped=0, time=3.364 s
# full: tests=674, failures=0, errors=0, skipped=0, time=17.039 s
```

I also ran a read-only Python reconciliation over the YAML manifest, JSONL
ledger, filesystem attempt inventory, all 30 `verdict.json` files, all 30
`execution-provenance.json` files, and `audit.json`. Its exact aggregate was:

```text
manifest_lanes 30; unique_ids 30; baseline 15; defect 15; seeds 5
ledger_lines 60; starts 30; finishes 30; unique_invocations 30
attempt_number=1 events 60; preserved finishes 30
runner exits: 0 x 15, 1 x 15
attempt_dirs 30; attempt.json 30; execution-record.json 30
attempt_gt1 []; quarantine []; unknown_lanes []; duplicate_lane_ids []
first_attempt_accountable 30; eventual_accountable 30; retries 0
passed_control 15; caught 15; unique_attempt_ids 30
```

The first run-root checksum command was initially issued from the repository
root and failed because entries are intentionally relative to the run-record
directory. Repeating it from the declared directory produced the 769/769 result
above; this was a verifier invocation error, not an artifact mismatch.

## Population and oracle reconciliation

The immutable schema-v3 manifest was committed before execution and declares
exactly five seeds, two roles, three repetitions per role, and 30 distinct lane
IDs. The filesystem has exactly one `attempt-1` directory for each declared
lane. It has no `attempt-2`, quarantine entry, unexpected child within a lane,
unknown lane directory, duplicate attempt ID, missing attempt metadata, or
missing execution record.

The JSONL ledger has exactly one `started` and one `finished` event for each of
30 unique invocation IDs. Start and finish lane/attempt identities agree; all
finishes are preserved; ledger lane/attempt pairs exactly equal filesystem
lane/attempt pairs. There are no orphan, unfinished, duplicate, unknown, or
unpreserved ledger events and no retry.

All 30 verdicts are execution-complete, accounting-eligible, and have a passed
live-validation gate. For the 15 controls, the raw metric outcome is `missed`,
meaning the expected defect was not reported; all have no failed oracle and are
correctly aggregated as 15 passed controls with zero false positives. For the
15 injected defects, the raw outcome is `caught`, the expected oracle alone
fails, and its defect class matches the manifest:

- L1 / `crash_stability`: 6 controls and 6 defects across ANR and oversized
  saved state.
- L2 / `state_loss`: 6 controls and 6 defects across query duplication and
  swallowed Back.
- L3 / `ui_rendering`: 3 controls and 3 defects for search-card copy.

The independently regenerated audit reports 30/30 first-attempt and eventual
accountability, 15/15 controls, 15/15 defects, complete provenance 30/30, zero
false positives, zero retries, and zero operational interventions.

## Execution identity

Every attempt records `emulator-5554`, AVD `aiverify_api35`, Android 15/API 35,
and fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
All target package `org.wikipedia.dev`, version code 50594, and Wikipedia commit
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`.

The 15 control deployments use baseline APK SHA-256
`7af65b50f282a2204595cb6e7a78a61a7c3370a06da2ee1306eb696982a1c957`.
Each defect seed has its own retained hash: ANR `84729b5b…a35`, oversized
`9a37982d…276`, query `64c359f1…f20`, swallowed `d02ec356…593`, and search
`4ece5be3…0d2`. For every one of the 30 attempts, the selected local APK hash
equals the hash of the APK pulled from the installed device path.

Retained tool identity is Android CLI `1.0.15498356`, adb `1.0.41` /
platform-tools `37.0.0-14910828`, Codex CLI `0.144.6`, Python `3.11.15`, pytest
`9.0.3`, OpenJDK `17.0.19`, and Gradle `9.5.1`. Journey and L3 invocation
receipts bind the effective model to `gpt-5.6-sol`; 24 attempts have a journey
invocation and the six L3 attempts additionally have an L3-judge invocation.

## Fail-closed review

The implementation appends and fsyncs a `started` event before creating the
attempt directory, then appends `finished` for both preserved runner results and
wrapper exceptions. Aggregation validates the ledger before reading outcomes.
It rejects malformed events, unknown lanes, missing/orphan start or finish,
duplicate event or lane-attempt identity, start/finish mismatch, unpreserved
wrapper invocation, and any ledger/filesystem inventory mismatch.

Attempt discovery requires contiguous `attempt-N` directories and rejects any
other child—including a hidden `quarantine` directory—inside a declared lane.
Aggregation verifies every attempt checksum, metadata lineage and globally
unique schema-v2 attempt ID, counts first-attempt accountability before any
retry, rejects retries of accountable results, and applies the bounded retry
limit. Focused tests exercise unledgered filesystem attempts, wrapper failure,
quarantine hiding, invalid lineage, duplicate IDs within a retry and across
lanes, checksum corruption, missing evidence, and preservation of an early
non-accountable first attempt. This closes the identified early-attempt hiding
path for the declared population.

## Deviations and limits

The README accurately discloses two pre-audit deviations:

- A malformed shell build orchestration failed to apply a patch, produced no
  APK, was removed, and never invoked the formal runner. Six clean isolated
  builds produced the retained APKs.
- The first final-audit invocation failed closed because package workspace
  metadata named the issue worktree while the Python executable belonged to the
  original worktree virtual environment. Commit `0dd30dd…` corrected only that
  metadata and regenerated checksums; lane evidence was neither edited nor
  rerun.

The APK binaries remain external because of their size; their paths, byte sizes,
build logs, local hashes, and per-attempt installed hashes are durable. This is
a five-seed Wikipedia result on one API 35 emulator using one Codex backend. It
does not establish physical-device, ColorOS, benchmark-wide, fully unattended,
or general multimodal reliability.

## Sole conclusion

`locally_supported`

The committed evidence supports the preregistered issue-80 gate within that
bounded scope, and the disclosed pre-formal failures do not enter or alter the
30-attempt denominator.
