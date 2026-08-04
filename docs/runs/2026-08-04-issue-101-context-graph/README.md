# M7-2 provenance-bound Quality Context Graph

Date: 2026-08-04

Issue: [#101](https://github.com/yangliang2/ai_verification/issues/101)

Base under test: `origin/main` at `ab06c5be7139ea6f569d6a1e2a566c41139aaeb0`
(M7-0 PR #106 merge)

Scope: bounded descriptor-driven context collection and graph traversal. This
slice does not index a general Kotlin repository, generate risks, execute
Android, or claim anything about private SystemUI, weather-service, or ColorOS
implementations.

## Fixture boundary

`bench/discovery-fixtures/synchronous-weather/` contains a neutral provider/API
boundary and UI-style consumer:

- `WeatherService.kt`: provider component and `WeatherProvider.current` API;
- `SystemUiWeatherConsumer.kt`: synchronous consumer operation;
- `build-metadata.json`: source/build metadata descriptor;
- `context-manifest.json`: provenance-bound facts, nodes, directed edges, and
  explicit unresolved runtime-thread observation;
- `README.md`: fixture scope and no-outcome-leakage statement.

The generic collector binds the same manifest to both `ChangeTarget` and
`ProjectTarget`. It has no fixture identifier, expected verdict, prescribed
Journey, or hidden defect shortcut.

## Verification commands and results

Commands ran from `/Users/peter/projects/ai_verification-m7-99`:

```text
/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q \
  tests/discovery
24 passed in 0.15s

/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q
740 passed in 22.56s

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python - <<'PY'
from aiverify.discovery import self_validate_schema
self_validate_schema()
print('schema self-validation: pass')
PY
schema self-validation: pass

git diff --check
pass
```

Relevant tool versions: `uv 0.11.7`, `git 2.50.1`, Python `3.11.15`, pytest
`9.0.3`, jsonschema `4.26.0`, and PyYAML `6.0.3`.

## Acceptance mapping

- `ContextNode` and `ContextEdge` represent component/API/operation/thread/
  process/quality-contract nodes and directed dependency edges with
  synchronous/asynchronous/unknown semantics.
- Every node/edge points to `ContextFact` IDs; each material fact preserves
  source kind, provenance, source version, confidence, and status.
- `collect_context` and `load_context_manifest` support both target modes without
  requiring a diff in Project Mode.
- `QualityContextGraph.trace_forward` and `.trace_backward` provide deterministic
  paths from service operation to critical consumer and back, while unresolved,
  stale, and contradictory evidence stops traversal and remains visible.
- `ContextCollectionResult` keeps unresolved questions and suggested probes
  separate from collected facts.
- Tests cover round trips/schema validation, missing provenance, explicit
  unknowns, runtime-vs-static source kind, stale/contradictory path evidence,
  dangling references, both target modes, and outcome-leakage shortcuts.

## Artifact inventory and checksums

```text
a97585d1e7ba7ef620205b5c3ec6520a7dea05a35470aa6d045c371e172d1edf  synchronous-weather/README.md
0860238c85757352b9ce2347c37cab5310219234c50e35c92ef2ce561cc9da0d  synchronous-weather/SystemUiWeatherConsumer.kt
5cc6723879b6a3814c13a8aa6e176d55cd8e5e32f8d983dd925bb665ea277dc6  synchronous-weather/WeatherService.kt
b87b4f1a5b60c1a46d89becb483b66de26608c6f201f252b3117bdff1ce31395  synchronous-weather/build-metadata.json
135ba563187993afb40eb9afdf3e202f53ee59d495d7d24f23d50daa40d36c4b  synchronous-weather/context-manifest.json
```

## Known gaps and claim boundary

- The fixture is source/descriptor-level; no Gradle or Android device build is
  claimed in this issue.
- Runtime thread/process evidence is explicitly unknown and produces a suggested
  probe; it is not promoted to a positive fact.
- The graph vocabulary is intentionally limited to the temporal/synchronous
  slice and is not a general compiler index or organization-wide graph.
- No finding, verdict, hidden defect label, or upstream acceptance is produced.
