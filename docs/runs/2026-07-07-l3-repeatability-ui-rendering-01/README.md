# Run Record — L3 repeatability for ui-rendering-01

> Issue: [#14](https://github.com/yangliang2/ai_verification/issues/14)
> Source seed: [`bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml`](../../../bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml)
> Source evidence: [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`](../2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)

Repeatability measurement for the existing `ui-rendering-01` L3 semantic oracle seed.
This run reuses fixed observed evidence from the original matched pair and repeats
only the Codex CLI L3 judge call. No emulator or APK rebuild was involved.

## Result

| Half | Iterations | Valid verdicts | Errors | Outcome distribution | Defect class distribution | Confidence min/median/max | Timing total |
|---|---:|---:|---:|---|---|---|---:|
| baseline | 5 | 5 | 0 | `pass: 5` | `null: 5` | 0.97 / 0.97 / 0.98 | 100.079 s |
| defect | 5 | 5 | 0 | `fail: 5` | `ui_rendering: 5` | 0.97 / 0.98 / 0.98 | 86.527 s |

For this text-layout semantic seed, L3 was stable across 10 independent judge calls:
the clean baseline always passed and the injected label-swap defect always failed as
`ui_rendering`. No schema retries, provider failures, inconclusive verdicts, or defect
class drift were observed.

## Commands

```bash
codex --version
# codex-cli 0.142.5

PYTHONPATH=src .venv/bin/python -m aiverify.bench.l3_repeatability \
  --artifact-dir docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/artifacts \
  --repetitions 5 \
  --workdir /Users/80268204/Projects/ai_verification \
  2>&1 | tee docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/run-output.txt
# baseline: pass 5/5, errors 0
# defect: fail/ui_rendering 5/5, errors 0

.venv/bin/pytest tests/bench/test_l3_repeatability.py
# 4 passed in 0.16s
```

## Chain under test

```text
fixed source evidence from #12
  -> bench l3_repeatability runner
  -> L3Oracle
  -> CodexCliProvider (codex exec, read-only sandbox)
  -> per-iteration judge answer + codex event stream
  -> summary.json + l3-repeatability-report.md
```

The judge prompt uses the original run spec's `scenario.l3_spec` plus observed layout
evidence. It does not include `expected_behavior`, the patch, or the original judge
answer fixtures.

## Artifact Inventory

- `summary.json` — machine-readable aggregate with per-half counts, per-call timing,
  confidence spread, verdicts, and errors.
- `l3-repeatability-report.md` — human-readable summary table generated from
  `summary.json`.
- `run-output.txt` — stdout from the live repeatability command.
- `checksums.sha256` — SHA-256 checksums for all run artifacts except itself.
- `artifacts/baseline/iteration-01..05/l3-judge/` — final answer and event stream for
  each baseline L3 judge call.
- `artifacts/defect/iteration-01..05/l3-judge/` — final answer and event stream for
  each defect L3 judge call.

Key checksums:

```text
aec50ea0e577f4603d1ea25cd8795afe23610b6a0577d35e58ca929cf8f609c3  summary.json
1053c521ef2067ce04c67cf7e1771c4d2ba284818f1a114f7cf1b0deb5bb65c7  l3-repeatability-report.md
11d5450dc4871af0a3e0d5b4ca3ac957ed052c68fbdc09a410f6bb0caeaa9d2e  artifacts/baseline/iteration-01/l3-judge/l3-judge-call-1.md
e8f3bfe8515e9c95a438d5ea7bf3177556bc225fa4638ccf4b09b9aeb13ed7a4  artifacts/defect/iteration-01/l3-judge/l3-judge-call-1.md
```

Full checksum inventory: [`checksums.sha256`](checksums.sha256).

## Implementation and Tests

- `src/aiverify/bench/l3_repeatability.py` adds the repeatability runner, aggregation
  logic, Markdown report writer, and CLI.
- `tests/bench/test_l3_repeatability.py` covers confidence statistics, outcome/class
  aggregation, error counting, and fixed-evidence runner wiring with `MockProvider`.

## Known Gaps

- This measures one text-layout semantic seed only. It supports using L3 for M2
  text-layout semantic seeds under repeatability discipline, but it does not prove
  visual-only or multimodal L3 reliability.
- The judge backend is still Codex CLI / OpenAI-family. Cross-source remains valid for
  the current Claude-authored injected patch shape, but broader calibration still needs
  explicit injector-vs-verifier accounting.
- No live emulator rerun was performed here; that was intentional because the issue
  asked to reuse fixed observed evidence where practical.
