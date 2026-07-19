# Independent verification-agent audit

## Result

`locally_supported`

The matched baseline passes the bounded issue #69 network-reliability contract. The injected candidate is independently rejected for both expected defects:

- `retry_storm`: retry attempts 1 through 6
- `stale_response_overwrite`: delayed `old-v1` is applied after `new-v2`, and the terminal UI shows `old-v1`

This is a local conclusion for this deterministic slice only. It is not a detection-rate, Goldset-wide, production-networking, or upstream-acceptance claim.

## Evidence basis and independence

The final audit used the Goldset specification, both Run Specs, accepted Journey records, Effective Execution Identity, baseline attempt 2 and candidate attempt 1 raw layouts/logcat, both evidence bundles, oracle source/tests, and direct local verification commands. No live-device observation was performed by this independent role.

Existing oracle result JSON contents were never displayed, parsed, or used to reach the result. One earlier full-manifest `shasum -c` invocation did open those files only to hash their bytes and printed `OK`; this is disclosed as a procedural deviation from the strict no-read instruction. The final selective manifest verification excluded those two files and also excluded the two verification-agent outputs being updated.

## Effective Execution Identity

Identity status is complete and checksum-bound:

- identity SHA-256: `04fa566435a420a28aee0785e0f428b8af5ea3825b9c1c555ec63a8f2c50218c`
- historical selective-manifest snapshot, taken before the final `ordered_response` checkpoint TDD and checksum-log additions: 97 entries total; 93 selectively verified; 4 deliberately skipped; 0 mismatches. These original 93/97 counts are intentionally preserved rather than presented as the later final manifest inventory.
- accepted attempts: baseline 2, candidate 1
- host origin, commit, recorded patch hash, and reverse patch checks match for both roles
- consumed Run Spec hashes match
- local and installed APK copies match their recorded hashes and bundle identities; baseline and candidate APKs are distinct
- emulator/API/AVD/package identity agrees between the Effective Execution Identity and both bundles
- Android CLI and adb paths, versions, and binary hashes match

The accepted Journey records each contain `action-1` through `action-8` in order, all marked `PASSED`, with valid layout/transcript/logcat/screenshot references and the correct role-specific Effective Execution Identity pointer.

Agent identity was checked against local Codex configuration and session metadata:

- operator backend: Codex TUI CLI 0.144.5
- operator session: `019f78f4-dda7-7832-8563-b377d6b51078`
- independent verifier backend: Codex TUI collaboration subagent, CLI 0.144.5
- verifier session: `019f7913-bec5-7772-8b21-ef8101953736`
- requested and effective model for both roles: `gpt-5.6-sol`
- reasoning effort: `high`

The requested model is recorded in `/Users/peter/.codex/config.toml:1`; each role's effective model and effort are recorded in its `turn_context` session metadata.

## Behavioral evidence

The raw/bundle integrity checks passed. Embedded logcat bytes equal the corresponding raw files. The final oracle requires one first and unique `fixture_ready` marker, valid tagged JSON, a finite strictly increasing complete marker sequence, and exact equality between logcat-extracted events and bundle `network_events`. Raw layout fields reconstruct exactly to bundle checkpoints.

Baseline evidence covers:

- online: network on, `online-v1`
- offline: network off, cached `cached-v1`
- timeout: timed out and cancelled, retry enabled
- retry: exactly attempts 1, 2, and 3, then `retry-v1`
- cancellation: delayed `late-v1` ignored after cancellation
- ordering: `new-v2` applied and delayed `old-v1` ignored
- recovery: network on, `recovered-v3`

Candidate evidence records attempts 1 through 6 and applies `old-v1` after `new-v2`. Recovery still reaches `recovered-v3`. Neither role contains a target-package crash/ANR marker or a blank/error terminal layout.

## Oracle verification

The final targeted oracle suite result was:

```text
49 passed in 0.11s
```

The last `ordered_response` checkpoint guard was also verified directly for both roles. Its terminal checkpoint must have `state: content` and `retry_enabled: false`:

- baseline with `state: cached`: exit `1`, `locally_rejected`, baseline `fail` with `scenario_contract_failed`
- baseline with `retry_enabled: true`: exit `1`, `locally_rejected`, baseline `fail` with `scenario_contract_failed`
- candidate with `state: cached`: candidate `fail` including `scenario_contract_failed`
- candidate with `retry_enabled: true`: candidate `fail` including `scenario_contract_failed`

All four direct guard cases were rejected as required.

Iterative adversarial auditing covered malformed provenance, exact checkpoint/scenario/event structure, global scenario ordering, cancellation and ordered-response completion cardinality, stale recovery, missing retry/cancellation/old-response evidence, canonical system events, fixed fixture/Journey/package identity, distinct APK identity, and required fields.

The final raw-consistency matrix contained 12 cases across both roles:

- fixture marker moved after business events
- duplicate fixture marker
- fixture/business sequence gap
- reordered business markers
- malformed tagged JSON
- logcat/bundle content mismatch

All 12 returned exit `2` with `non_accountable`. No remaining hard fail-open was found.

The valid evidence bundles were then run through the oracle CLI. It exited `0` with:

- baseline: `pass`, no faults
- candidate: `fail`, faults `retry_storm` and `stale_response_overwrite`
- final result: `locally_supported`

## Key SHA-256 values

- Goldset specification: `2f05aae5e2739993051374916437f52494b27b9422ce420321406bd61cee79bd`
- baseline Run Spec: `4a8e8cf626db7594c98d5f983018990a2155fe7652c7968696832649b6737aea`
- candidate Run Spec: `2c353217c85f4afc923eaefc2b1d235f39ed677847c269747a5da6c9267c1b50`
- baseline evidence bundle: `f60120b608470fa7221bff4d127dd282c843e51d611192e4c35e06f29ab42700`
- baseline raw logcat: `8c2350abef913ba07b29e3f1d1f2175a8b170d4aa80e6733a76425d88adc5aea`
- candidate evidence bundle: `9b58895f7e4ba9e874467d420765b1a5043bf1d6c60947d3630ed18821693a25`
- candidate raw logcat: `903f7a64d719356a3d17f6be1eb339ecf0a42cdd2c67a4cae0a38e38527bddf8`
- Effective Execution Identity: `04fa566435a420a28aee0785e0f428b8af5ea3825b9c1c555ec63a8f2c50218c`
- oracle source: `8bcfbd8073314fa9b2ae0eaf85daf5ddf31d364e9a544385758b133776e33cae`
- oracle tests: `fa076d296138724de281a7a62959bf5048fd38292d931bb915fcd7081127809e`

The machine-readable result and full check inventory are in `conclusion.json` next to this file.
