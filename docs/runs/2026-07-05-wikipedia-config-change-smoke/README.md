# 2026-07-05 Wikipedia config-change baseline Smoke Slice Run Record

Issue: [#8](https://github.com/yangliang2/ai_verification/issues/8) — First Wikipedia config-change Goldset smoke seed.
Parent PRD: [#1](https://github.com/yangliang2/ai_verification/issues/1).

## Scope

First real end-to-end run of the verification chain against a config-change
behavior-layer scenario on a live emulator:

```text
run-spec → Journey Segment Boundary (rotate) → Android CLI layout evidence
→ L1/L2 oracle → schema-validated verdict → run record
```

This is a **baseline (negative control)** — no defect is injected. Wikipedia
correctly retains the search query across a configuration change, so the
verdict must be **L2 pass**. It proves the harness reports PASS when the
behavior is actually correct, before injected-defect FAIL runs are trusted.
It does **not** claim any benchmark detection performance.

- taxonomy pattern: `config-change-01` / `config-change-05` (旋转后 UI 状态丢失)
- verdict symptom axis (if injected): `state_loss`
- real-world analogues: `bench/goldset/candidates.md` C1 (Tusky #45), C3 (Thunderbird #10288)

## Environment

Repository:
- Workspace: `/Users/peter/projects/ai_verfication`
- Host app: `/Users/peter/hosts/wikipedia`
- Host app commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Package: `org.wikipedia.dev`

Tools:
- Android CLI: `1.0.15498356`
- Codex CLI: `codex-cli 0.139.0` (installed; not exercised in this agent-in-the-loop baseline — see Known Gaps)
- ADB: `Android Debug Bridge version 1.0.41`
- Emulator/device: AVD `aiverify_api35`, `emulator-5554`, boot completed in 23936 ms

APK (reused from 2026-06-15 build, not rebuilt):
- Path: `/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- SHA-256: `cf882666ecab7b4ad3362e5580ef3e692062d3958045b103e0c43a6014ee32e9`

## Commands And Results

Deploy + launch:
```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```
```text
Installation completed successfully
Activation completed successfully
```

Navigate to search input (agent-in-the-loop via Android CLI layout + adb tap;
`center` coordinates read from `android layout` JSON):
```bash
adb -s emulator-5554 shell input tap 540 2232    # nav_tab_search
adb -s emulator-5554 shell input tap 1001 1344   # close "Faster way to Search" promo
adb -s emulator-5554 shell input tap 540 313     # search_card -> opens SearchView
adb -s emulator-5554 shell input tap 542 215     # focus search_src_text
adb -s emulator-5554 shell input text "zzsentinelqx"
```

Capture BEFORE checkpoint (portrait), then inject rotation at the boundary,
then capture AFTER checkpoint (landscape):
```bash
android layout --device=emulator-5554 --pretty -o=<before>/layout.json
android screen capture -o=<before>/screen.png
adb -s emulator-5554 logcat -d -t 300 > <before>/logcat.txt

# --- Journey Segment Boundary: inject rotate portrait->landscape ---
adb -s emulator-5554 shell settings put system accelerometer_rotation 0
adb -s emulator-5554 shell settings put system user_rotation 1

android layout --device=emulator-5554 --pretty -o=<after>/layout.json
android screen capture -o=<after>/screen.png
android screen capture --annotate -o=<after>/screen-annotated.png
adb -s emulator-5554 logcat -d -t 300 > <after>/logcat.txt
```

State observed on `search_src_text` (resource-id):
```text
BEFORE (portrait, screen 1080x2400): text = 'zzsentinelqx'
AFTER  (landscape, screen 2400x1080): text = 'zzsentinelqx'   -> retained
```
Screenshot dimensions (1080x2400 → 2400x1080) are the evidence that the
rotation actually took effect at capture time.

Verdict computed by the repo code (`aiverify.runner.verdict.judge_l2_from_android_layout`
+ `aiverify.agent.oracle.L1Oracle`), written to `verdict.json`:
```text
L1 outcome: inconclusive   (no crash/ANR signal in logcat — L1 abstains by design)
L2 outcome: pass           (search_src_text.text retained; defect_class_hypothesis=null)
```

Test verification:
```bash
PYTHONPATH=src .venv/bin/pytest
```
```text
173 passed in 3.15s
```
(was 170; +3 new tests in `tests/bench/test_goldset_config_change_smoke.py`.)

## Implementation Mapping

- Run Spec: `bench/goldset/run-specs/wikipedia-config-change-smoke.yaml`
- Seed spec: `bench/goldset/specs/wikipedia-config-change-smoke.md`
- Frozen layout fixtures: `bench/goldset/fixtures/wikipedia-config-change-smoke/{before,after}-layout.json`
- Regression test: `tests/bench/test_goldset_config_change_smoke.py`
- Verdict: `docs/runs/2026-07-05-wikipedia-config-change-smoke/verdict.json`
- Exercised runner/oracle code: `src/aiverify/runner/verdict.py`, `src/aiverify/runner/run_spec.py`, `src/aiverify/agent/oracle/{l1,l2}.py`, `src/aiverify/agent/oracle/schema.py`

## Artifact Inventory

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/after-segment-0-before-rotate/layout.json` | `c833afd37e96bb7c353b53486dd7fab262c7407763cccdf16909c6f64b67f8ef` |
| `artifacts/after-segment-0-before-rotate/screen.png` | `204e84d4227c7e10d9585f302d5e45ef4bd3147828a0d70fd970c3b34ed78c5b` |
| `artifacts/after-segment-0-before-rotate/logcat.txt` | `5405a71b938c00a460159ca1ea011d30720cfea622025fbc18ff4376ba935c1a` |
| `artifacts/after-event-0-rotate-landscape/layout.json` | `abfbdd260c4ebd227bd394dd11710ec3ce0f4f9c3d7b485e6e7cac4c14ddd311` |
| `artifacts/after-event-0-rotate-landscape/screen.png` | `b7cf8104674b3d2bc7ea1f2c76bb70410ab23ff301d83b65b5f4c4bf6983dc3c` |
| `artifacts/after-event-0-rotate-landscape/screen-annotated.png` | `f2d056a0daa4cd7ac31911de57f0a8fc074ba72e796a1fd7d53b96712ec6e075` |
| `artifacts/after-event-0-rotate-landscape/logcat.txt` | `24a34c6ca4b6589a6678bda03d75af1d9eca9ea65e806cafc8c51a207bac8bb6` |
| `verdict.json` | `d1e275403edc2cd6a086a0f3e89d4bb772563c4cb8667f6d78af116f26feb7bc` |

`before-layout.json` / `after-layout.json` fixtures are byte-identical copies of the
two `layout.json` above (same SHA-256), frozen for the hardware-independent test.

## Known Gaps

- **Baseline only.** This proves the chain executable and the negative control
  (correct behavior → pass). It does **not** prove the verifier can detect a
  config-change defect. That requires injecting an equivalent defect (patch
  `search_src_text` query persistence, rebuild) and observing L2 fail — the
  next step of #8.
- **Codex CLI backend not exercised.** Navigation was agent-in-the-loop
  (Android CLI layout + adb tap/text), matching CONTEXT.md's *Agent-In-The-Loop
  Execution*. Driving segments through `CodexCliBackend` is still pending.
- **Compose nodes have no resource-id.** `android layout` exposes resource-ids
  for classic Views (`search_src_text`) but not for the Compose result list;
  this seed deliberately asserts only on the classic SearchView EditText.
- Rotation injected via `adb settings user_rotation` (the MVP injector path),
  not through a higher-level Android CLI Journey.
