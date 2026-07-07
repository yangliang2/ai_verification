# Run Record — Wikipedia ui-rendering-01 nav label swap (L3 semantic oracle exercise)

> Issue: [#12](https://github.com/yangliang2/ai_verification/issues/12)
> Seed spec: [`bench/goldset/specs/wikipedia-ui-rendering-01-nav-label-swap.md`](../../../bench/goldset/specs/wikipedia-ui-rendering-01-nav-label-swap.md)
> Run spec: [`bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml`](../../../bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml)
> Patch: [`bench/goldset/patches/wikipedia-ui-rendering-01-nav-label-swap.patch`](../../../bench/goldset/patches/wikipedia-ui-rendering-01-nav-label-swap.patch)

First end-to-end exercise of the **L3 (LLM semantic) oracle path**: a matched pair on
`emulator-5554` where the injected defect (swapped `READING_LISTS`/`SEARCH` nav-tab
string resources in `NavTab.kt`) is **invisible to L1** (no crash/ANR) and **to L2**
(no boundary event, no missing node) by construction — only a semantic judge comparing
the observed UI against the product spec can catch it.

## Result

| Half | APK | L1 | L2 | L3 | Exit code | Wall clock |
|---|---|---|---|---|---|---|
| baseline | clean `6ccb8d8` build | inconclusive | inconclusive (no event) | **pass** | **0** | 99.6 s |
| defect | + nav-label-swap patch | inconclusive | inconclusive (no event) | **fail / ui_rendering** (confidence 0.97) | **1** | 111.3 s |

The defect-run judge pinpointed both swapped labels with evidence refs
(`nav_tab_reading_lists` renders "Search", `nav_tab_search` renders "Saved") and cited
the checkpoint screenshot; the baseline judge verified all five labels against the spec
and passed. Verdicts: [`baseline/verdict.json`](baseline/verdict.json),
[`defect/verdict.json`](defect/verdict.json).

## Chain under test

```
run-spec.yaml (scenario.l3_spec = correct-behavior product spec)
  -> JourneySegmentRunner(CodexCliBackend)      # Codex drives onboarding -> main feed
  -> AndroidEvidenceCollector                    # layout/screenshot/logcat checkpoint
  -> L1 (logcat scan)          -> inconclusive
  -> L2 (no boundary event)    -> not applicable
  -> gate opens: l3_spec non-empty AND L1/L2 non-fail
  -> L3Oracle(CodexCliProvider)                  # codex exec, --sandbox read-only
  -> verdict.json (l1/l2/l3 + per-phase timing incl. "l3-judge")
```

- Judge backend: **Codex CLI** via `src/aiverify/providers/codex_cli.py`
  (`CodexCliProvider`, `provider_id="openai"`, read-only sandbox, answer + event
  stream persisted under `artifacts/l3-judge/`).
- Cross-source: defect patch Claude-authored (injector ≈ anthropic) vs judge = openai —
  satisfies the `providers/base.py` injector ≠ verification-side constraint.
- Fairness: the judge receives only `scenario.l3_spec` + observed evidence (journey
  results, final checkpoint layout JSON, screenshot paths). It never sees
  `expected_behavior`, the patch, or any hint that a defect may exist — the baseline
  half ran through the identical prompt path and passed.

## Commands

```bash
# baseline (Wikipedia repo clean at 6ccb8d8)
cd /Users/peter/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon   # BUILD SUCCESSFUL
adb -s emulator-5554 install -r app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell pm clear org.wikipedia.dev
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml \
  --device emulator-5554 --artifact-dir docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/baseline/artifacts
# -> L1: inconclusive (None)  |  L2: inconclusive (None)  |  L3: pass (None)   RUNNER_EXIT=0

# defect
cd /Users/peter/hosts/wikipedia && git apply .../wikipedia-ui-rendering-01-nav-label-swap.patch \
  && ./gradlew assembleDevDebug --no-daemon                                  # BUILD SUCCESSFUL
adb -s emulator-5554 install -r app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell pm clear org.wikipedia.dev
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml \
  --device emulator-5554 --artifact-dir docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/defect/artifacts
# -> L1: inconclusive (None)  |  L2: inconclusive (None)  |  L3: fail (ui_rendering)   RUNNER_EXIT=1
git -C /Users/peter/hosts/wikipedia checkout -- app/src/main/java/org/wikipedia/navtab/NavTab.kt
```

## Environment

| item | value |
|---|---|
| device | `emulator-5554`, AVD `aiverify_api35` (API 35) |
| host repo | `/Users/peter/hosts/wikipedia` @ `6ccb8d8` (clean before/after) |
| package / activity | `org.wikipedia.dev` / `org.wikipedia.DefaultIcon` |
| baseline APK sha256 | `450f97a73b37f419610fbf2677137e93bf78265030fdc07cbf26c7967a435fad` |
| defect APK sha256 | `a94d10e2f9ea9bcad9897aa9230c79d6388ca0206d283ff947cf95184cee35c8` |
| driver + judge | `codex-cli 0.139.0` (driver: bypass sandbox; judge: `--sandbox read-only`) |
| test suite after change | `.venv/bin/pytest` → **219 passed** (was 202) |

## Timing (from verdict.json `timing.phases`)

| phase | baseline | defect |
|---|---|---|
| journey segment (Codex drives onboarding→feed) | 73.6 s | 83.9 s |
| checkpoint capture | 5.4 s | 5.3 s |
| **l3-judge (kind=oracle)** | **20.5 s** | **22.0 s** |
| total | 99.6 s | 111.3 s |

Cost bound held: exactly **1 judge call per half** (no schema retry needed); ≤4 was
the scoped ceiling.

## Artifacts

Per half (`baseline/`, `defect/`):

- `verdict.json` — l1/l2/l3 verdicts + timing.
- `artifacts/after-segment-0/{layout.json,screen.png,screen-annotated.png,logcat.txt,commands.json}` — final checkpoint.
- `artifacts/l3-judge/l3-judge-call-1.md` — the judge's verbatim final answer (verdict JSON).
- `artifacts/l3-judge/l3-judge-call-1.events.jsonl` — full codex event stream of the judge call.
- `artifacts/<scenario>-segment-0/{codex-journey-result.json,codex-events.jsonl}` — driver evidence.

Key checksums (sha256):

```
5c3c01e36f72a91db035eeaa7a55044085a7bc6151237271fd830cdbedbe7ed4  baseline/verdict.json
6a435b871ad78262a5496222a873d43b1b4bb76c547f50affcb212088fe7d1ae  defect/verdict.json
9563525ebf2f279229201dbad2a0c88e532dc1217e8f8033e697849d518b32c7  baseline/artifacts/after-segment-0/layout.json
304b3f13020eef57e62a6db9433182372a5361bc79a6e3427446e8b71a40966f  defect/artifacts/after-segment-0/layout.json
7f36f4c485608372ac91bff015ee77ec5396d4efbe740c1a463b88ca6bf0ba9c  baseline/artifacts/l3-judge/l3-judge-call-1.md
083655ee8a4060041ec03d0ca20904cd62137f9f0edba19311738a12d48ad418  defect/artifacts/l3-judge/l3-judge-call-1.md
```

Frozen fixtures (regression without emulator/LLM):
`bench/goldset/fixtures/wikipedia-ui-rendering-01-nav-label-swap/{baseline,defect}-final-layout.json`
+ `{baseline,defect}-l3-response.md`, replayed via `MockProvider` in
`tests/bench/test_goldset_ui_rendering_01_nav_label_swap.py`.

## Known gaps / notes

- **Single-shot judge**: each half ran the judge once. No repeatability/variance
  measurement for L3 (an LLM judge is nondeterministic in principle); acceptable for
  the first path exercise, should be measured before L3 results feed any benchmark
  number.
- **Text-only judgment**: the layout JSON exposes resource-ids next to labels, so the
  mismatch is inferable without reading the screenshots (paths were provided as refs;
  the judge cited one but did not need multimodal input). A visual-only rendering
  defect (e.g. overlap/clipping) would need a multimodal judge.
- Judge failure degrades to `L3 inconclusive` (verdict_id `L3-error`) rather than
  aborting the run — not exercised live here (no failures), covered by unit tests.
- The L2 layer was inconclusive because the scenario is event-less by design; this
  seed does not prove "L2 checked and missed it", it proves the L1/L2-blind class is
  now catchable at all.
