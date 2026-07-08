# Run Record - L3 repeatability for ui-rendering-02

> Issue: [#18](https://github.com/yangliang2/ai_verification/issues/18)
> Source seed: [`bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml`](../../../bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml)
> Source evidence: [`docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/`](../2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md)

Repeatability measurement for the `ui-rendering-02` L3 semantic oracle seed. This run
reuses fixed observed evidence from #17 and repeats only the Codex CLI L3 judge call.
No emulator or APK rebuild was involved.

## Result

| Half | Iterations | Valid verdicts | Errors | Outcome distribution | Defect class distribution | Confidence min/median/max | Timing total |
|---|---:|---:|---:|---|---|---|---:|
| baseline | 5 | 5 | 0 | `pass: 5` | `null: 5` | 0.96 / 0.96 / 0.98 | 82.689 s |
| defect | 5 | 5 | 0 | `fail: 5` | `ui_rendering: 5` | 0.96 / 0.97 / 0.98 | 92.855 s |

For this text-layout semantic seed, L3 was stable across 10 independent judge calls:
the clean Search tab card always passed, and the injected history-copy defect always
failed as `ui_rendering`. No schema retries, provider failures, inconclusive verdicts,
or defect class drift were observed.

## Commands

```bash
codex --version
# codex-cli 0.142.5

PYTHONPATH=src .venv/bin/python -m aiverify.bench.l3_repeatability \
  --run-spec bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml \
  --source-run-dir docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch \
  --artifact-dir docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/artifacts \
  --repetitions 5 \
  --workdir /Users/80268204/Projects/ai_verification \
  2>&1 | tee docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/run-output.txt
# baseline: pass 5/5, errors 0
# defect: fail/ui_rendering 5/5, errors 0

.venv/bin/pytest tests/bench/test_l3_repeatability.py
# 5 passed in 0.77s
```

## Chain Under Test

```text
fixed source evidence from #17
  -> bench l3_repeatability runner
  -> L3Oracle
  -> CodexCliProvider (codex exec, read-only sandbox)
  -> per-iteration judge answer + codex event stream
  -> summary.json + l3-repeatability-report.md
```

The judge prompt uses the #17 run spec's `scenario.l3_spec` plus observed layout
evidence. It does not include `expected_behavior`, the injected patch, or frozen judge
answer fixtures.

## Artifact Inventory

- `summary.json` - machine-readable aggregate with per-half counts, per-call timing,
  confidence spread, verdicts, and errors.
- `l3-repeatability-report.md` - human-readable summary table generated from
  `summary.json`.
- `run-output.txt` - stdout from the live repeatability command.
- `checksums.sha256` - SHA-256 checksums for all run artifacts except itself.
- `artifacts/baseline/iteration-01..05/l3-judge/` - final answer and event stream for
  each baseline L3 judge call.
- `artifacts/defect/iteration-01..05/l3-judge/` - final answer and event stream for
  each defect L3 judge call.

## Key Checksums

```text
d896c28f8df1d88714d1d1c0a891a988d78fc9b4bde676d11bc6e9d9fad31a9c  summary.json
63dd8833783cd5faac6ed70dec974ee4dc175f63eee74e11fed2835e986f62ac  l3-repeatability-report.md
477d9982e1289a589cfa1b45f5f1e3a55e0dd2be9e5effce83b5fed73f912c59  run-output.txt
c09872686ebd6df1feb21caf3847e9bd0c1dfd02815cadd4101f6024a00ffd2d  artifacts/baseline/iteration-01/l3-judge/l3-judge-call-1.md
0244b3e3b270e7754db42b0343435a67d9857a7999aab7a638592118d299eb1e  artifacts/defect/iteration-01/l3-judge/l3-judge-call-1.md
```

Full checksum inventory: [`checksums.sha256`](checksums.sha256).

## Implementation and Tests

- `src/aiverify/bench/l3_repeatability.py` now derives default fixed-evidence journey
  result paths from the loaded run spec's `scenario.id`, rather than hard-coding
  `ui-rendering-01`.
- `tests/bench/test_l3_repeatability.py` covers the generalized case discovery.

## Known Gaps

- This measures one text-layout semantic seed only. It supports using
  `ui-rendering-02` under the same M2 repeatability discipline as `ui-rendering-01`,
  but it does not prove visual-only or multimodal L3 reliability.
- No live emulator rerun was performed here; that was intentional because #18 reuses
  fixed observed evidence from #17.
- The judge backend is still Codex CLI / OpenAI-family. Cross-source remains valid for
  the current Claude-authored injected patch shape, but broader calibration still needs
  explicit injector-vs-verifier accounting.
