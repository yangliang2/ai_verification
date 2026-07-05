# 2026-07-05 End-to-End CLI Run — Codex CLI backend drives the whole chain

Follow-up to #8: closes the two gaps called out in the #8 run records —
"Codex CLI backend not exercised" and "no assembled end-to-end entrypoint".

## What this proves

The full verification chain now runs from a single command with **no manual
driving** — the Codex CLI Verification Agent Backend drives the app, the runner
injects the config-change event and captures evidence, and the oracle judges:

```
python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-config-change-01-defect.yaml \
  --device emulator-5554 --artifact-dir <run>/artifacts
```

```
run-spec.yaml
  -> JourneySegmentRunner
       -> CodexCliBackend           (codex exec drives via android layout + adb)
       -> AndroidEvidenceCollector  (layout/screenshot/logcat checkpoints)
       -> DeviceSystemEventInjector (dark_mode at the Journey Segment Boundary)
  -> L1/L2 oracle
  -> verdict.json
```

Result on the **injected-defect** build (`isSaveFromParentEnabled=false`):

```
scenario: wikipedia-config-change-01-defect
L1: inconclusive  |  L2: fail  (defect_class=state_loss)
L2 evidence: resource-id='search_src_text' 期望='zzsentinelqx' 实际='Search Wikipedia'
Codex journey results: [PASSED navigate+open search, PASSED type sentinel]
```

The CLI exits non-zero when L2=fail so CI can gate on it.

## Bugs found and fixed to make the backend actually run

The backend had never been exercised live; two real defects blocked it:

1. **`CodexCliBackend` used `--ask-for-approval`**, which `codex exec` 0.139.0
   rejects. Replaced with `--dangerously-bypass-approvals-and-sandbox`
   (+ `--skip-git-repo-check`, empty stdin). `src/aiverify/runner/codex_backend.py`.
2. **`journey_result_schema.json` was not OpenAI-strict** — codex's
   `--output-schema` requires `additionalProperties:false` on every object and all
   properties in `required`; the schema had `additionalProperties:true`, so codex
   returned HTTP 400 `invalid_json_schema`. Made the schema strict.

A third defect was surfaced by the *first* live end-to-end run:

3. **L1 false positive on real-device logcat.** `AndroidEvidenceCollector` dumps
   the whole logcat ring buffer, and L1's bare `java.lang.RuntimeException` pattern
   matched benign lines from other processes — e.g. gRPC/GmsCore
   `E gclu: java.lang.RuntimeException: ManagedChannel allocation site` and a
   *caught* `W Binder: java.lang.NullPointerException`. Fixed by (a) requiring the
   `AndroidRuntime` tag on the exception pattern (real uncaught crashes always have
   it) and (b) clearing logcat at run start so L1 only sees this run's events.
   Before the fix this run reported L1=fail; after, L1=inconclusive (correct).

## New pieces

- `src/aiverify/runner/cli.py` + `__main__.py` — the assembled entrypoint.
- `JourneySegmentRunner.run(..., instruction_prefix=...)` — prepends driver
  guidance (tools, device serial, output contract) to each segment's Journey XML,
  so the backend agent knows how to drive.

## Environment

- Host app @ `6ccb8d8`, defect APK (patch applied), package `org.wikipedia.dev`
- Emulator `emulator-5554` (AVD `aiverify_api35`)
- Codex CLI `codex-cli 0.139.0`, Android CLI `1.0.15498356`, adb `1.0.41`

## Artifact Inventory

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/after-segment-0/layout.json` (post-Codex, sentinel present) | `d09d815a4516963b175fbe75ec76b6c5c029b6ccc040763f41766cb3c4f9ad6b` |
| `artifacts/after-event-0/layout.json` (post dark-mode, sentinel lost) | `1d39f39a871f86dc2ea5610bcc3651ee9db0d898dfba21bacb54dab1c5d474b3` |
| `artifacts/.../codex-journey-result.json` (backend's structured output) | `26888ed981ec8472c8c7e1b295539b0304638a79d4ea3102c15274cd6638221e` |
| `verdict.json` | `a686733164ca5d0eec4b1998f637a3a987fd89db4e80d5c4664acfde14c798a9` |

`artifacts/<segment-id>/codex-events.jsonl` holds the raw codex JSONL event stream.

## Known Gaps

- Single segment, single scenario. Multi-segment journeys and the other taxonomy
  classes are future work (#9).
- Codex drives via `android layout` + `adb` shell commands under
  `--dangerously-bypass-approvals-and-sandbox` (needed because adb/android are
  outside the workspace sandbox).
- The CLI launches the app and assumes onboarding is already completed (data
  persisted); the driver preamble tells the agent how to advance onboarding if seen.
