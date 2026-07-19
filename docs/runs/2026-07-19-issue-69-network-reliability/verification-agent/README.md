# Independent verification-agent audit

## Result

`locally_supported`

The matched baseline passes the bounded network-reliability contract. The injected candidate is independently rejected for both required defects: six retry attempts (`retry_storm`) and a delayed `old-v1` response applied after `new-v2` (`stale_response_overwrite`). This is only a local conclusion for the deterministic issue #69 slice; it is not a detection-rate, Goldset-wide, production-networking, or upstream-acceptance claim.

## Independence and scope

This audit was re-derived from only:

- `bench/goldset/specs/wikipedia-network-reliability-01.md`
- the baseline and candidate run specs under `bench/goldset/run-specs/`
- `baseline/attempt-2` and `candidate/attempt-1` raw `*-layout.json` and `logcat.txt`
- the baseline and candidate `evidence-bundle.json`
- `src/aiverify/bench/network_reliability.py`, invoked through its CLI
- `tests/bench/test_network_reliability.py`, for the final fail-closed regression coverage

Existing `oracle-conclusion*.json` files were not opened, parsed, or relied on. No implementation code was modified.

## Findings

Matched-pair identity and execution contract passed. The run specs share the same Wikipedia origin and commit, package, activity, user-action list, and system-event schedule. The bundles share fixture `issue-69-network-v1`, Journey SHA-256 `d9ff0cdec1734f3c2cf6fba05035b2bc53c579aacf9760bba61fb9c3afd4c415`, emulator/API/AVD identity, package, and normalized system events. The two non-empty APK hashes are valid SHA-256 strings and differ as expected between baseline and candidate.

Bundle-to-raw integrity passed. For each role, the embedded logcat is byte-identical to the raw logcat by SHA-256, extracted `AIVerifyNetwork` events exactly match `network_events`, and sequences strictly increase. Every raw layout has exactly one fixture status node, and reconstructed checkpoint values exactly match the bundle.

Baseline evidence covers the full contract:

- online: network observed on, `online-v1` applied
- offline: network observed off, `cached-v1` shown
- timeout: timed out and cancelled, with timeout UI and retry enabled
- retry: exactly attempts 1, 2, and 3, then `retry-v1`
- cancellation: cancelled request's `late-v1` response ignored, cancelled UI retained
- ordering: `new-v2` applied and delayed `old-v1` ignored, terminal `new-v2`
- recovery: network observed on and `recovered-v3` applied

Candidate defect evidence is direct and internally consistent. It logs retry attempts 1 through 6. In ordering, it applies `new-v2`, then applies delayed `old-v1`; both raw terminal layout and bundle checkpoint show `old-v1`. Recovery still reaches `recovered-v3`.

No target-package `FATAL EXCEPTION`, target `ANR`, target process crash marker, `blank` state, or `error` state was found in either attempt. Each role has eight populated fixture layouts. The specified timeout and cancellation screens intentionally have empty content but remain non-blank because the fixture/scenario/state/retry fields and controls are populated.

## Commands and results

The audit used `jq`/Ruby extraction to reconstruct all layout checkpoints, compare them exactly with bundle checkpoints, and semantically compare YAML system events with bundle system events (normalizing omitted empty `args` to `{}`). Both roles matched.

Structured log events were checked with the equivalent of:

```sh
diff -u \
  <(rg 'AIVerifyNetwork' <raw-logcat> | sed 's/^.*AIVerifyNetwork: //' | jq -s 'map(select(.scenario != "fixture"))') \
  <(jq '.network_events' <evidence-bundle>)
```

Both diffs were empty; both raw event sequences were strictly increasing. Target-package crash/ANR searches returned zero matches. Layout reconstruction reported eight layouts, one fixture status node per layout, exact checkpoint matches, and zero blank/error states for each role.

The oracle CLI was run independently to a temporary file:

```sh
PYTHONPATH=src python3 -m aiverify.bench.network_reliability \
  --baseline docs/runs/2026-07-19-issue-69-network-reliability/baseline/evidence-bundle.json \
  --candidate docs/runs/2026-07-19-issue-69-network-reliability/candidate/evidence-bundle.json \
  --output <temporary-file>
```

It exited `0`, with baseline `pass` and no faults, and candidate `fail` with `retry_storm` and `stale_response_overwrite`.

The final fail-closed hardening was independently rechecked after an initial adversarial review exposed eight fail-open field shapes. The finalized implementation and tests were then rerun with:

```sh
PYTHONPATH=src uv run --no-project \
  --with pytest --with pydantic --with pyyaml \
  python -m pytest tests/bench/test_network_reliability.py -ra
```

Result: `22 passed in 0.08s`.

Two direct CLI adversarial matrices were also run without relying on the tests. The original 12 malformed cases covered invalid JSON, non-object roots, malformed attempt/scenario/kind/request_id/sequence fields, malformed checkpoint fields, and a non-string logcat. All 12 returned exit `2` with `non_accountable`, and none threw an exception.

The eight formerly fail-open shapes were rerun individually: array-valued device identity, numeric fixture identity, numeric Journey hash, object-valued APK package, object-valued APK hash, missing event request ID, object-valued event content, and non-finite (`NaN`) sequence. All eight now return exit `2` with `non_accountable`, with no exception. A final valid-bundle CLI run still exits `0` and preserves `locally_supported`, baseline `pass`, and candidate faults `retry_storm` plus `stale_response_overwrite`.

During finalization, an external concurrent writer replaced `conclusion.json` with an 85-byte `locally_rejected` placeholder containing empty checks, evidence, and commands. The conflict was detected because it contradicted the immediately preceding valid-bundle CLI result and had no audit evidence. The parent verified that no writer remained, removed redundant prompt/schema/event files, and provided an exclusive write window. The evidence-backed result was then restored and revalidated; the placeholder was excluded as write contamination, not treated as oracle evidence.

Key SHA-256 values:

- goldset spec: `2f05aae5e2739993051374916437f52494b27b9422ce420321406bd61cee79bd`
- baseline run spec: `4a8e8cf626db7594c98d5f983018990a2155fe7652c7968696832649b6737aea`
- candidate run spec: `2c353217c85f4afc923eaefc2b1d235f39ed677847c269747a5da6c9267c1b50`
- baseline bundle: `f60120b608470fa7221bff4d127dd282c843e51d611192e4c35e06f29ab42700`
- baseline raw logcat: `8c2350abef913ba07b29e3f1d1f2175a8b170d4aa80e6733a76425d88adc5aea`
- candidate bundle: `9b58895f7e4ba9e874467d420765b1a5043bf1d6c60947d3630ed18821693a25`
- candidate raw logcat: `903f7a64d719356a3d17f6be1eb339ecf0a42cdd2c67a4cae0a38e38527bddf8`
- oracle CLI: `46c5901959f18fa193ee7c4f2ad824e012bf47cabee6f53b315dccd50f9be734`
- oracle tests: `56366a3b5a588cb7f8b1d327bc898dda85a5f3ca6c67742376335bc4ba60947d`

The machine-readable result and detailed check inventory are in `conclusion.json` next to this file.
