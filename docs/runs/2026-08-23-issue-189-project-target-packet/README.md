# Issue #189 — blind-safe `ProjectTarget` packet verification

Issue: [DIL-M0.5: Compile a blind-safe ProjectTarget packet from a safe pair](https://github.com/yangliang2/ai_verification/issues/189)

Implementation under test: `639e649 feat(injection): compile blind-safe ProjectTarget packets`.

## Scope and implementation

This run verifies the structural M0.5 packet seam only. It does not add a Verification Agent, fake-diff handling, a Discovery Campaign or Run Spec, Android code, or runtime execution.

- `src/aiverify/injection/packets.py` adds the immutable, canonical `ProjectTargetPacket` compiler and parser. It binds a sealed safe pair, source origin/commit/tree identities, a bounded canonical scope, and an explicit discovery budget.
- The compiler scans the complete delivered source tree (paths, symlink targets, and file text) against the declared disclosure tokens before issuing a packet, and uses stable public rejection codes.
- `src/aiverify/injection/__init__.py` exports the new packet surface.
- `tests/injection/test_change_target_packet.py` covers both defect and control variants, determinism, parser round-trips, high-entropy filename/content sentinels, and fail-closed rejection cases.

## Acceptance evidence

| Acceptance criterion | Evidence |
| --- | --- |
| Deterministic, bound ProjectTarget identity | Canonical bytes and identity tests assert stable fields for a sealed pair and prove scope/budget changes alter identity. |
| No verifier-visible hidden material | The compiler disclosure-scans the full delivered tree; tests inject the declared high-entropy sentinel into both an out-of-scope source filename and file content and assert rejection. Packet parsing also avoids reflecting invented hidden field names. |
| Fail closed with stable errors | Tests cover missing pairing, unsealed input, incompatible provenance, materialized-tree drift, unbounded scope/budget, unavailable scope, and policy disclosure rejection. |
| Defect/control separation | Both variants compile and round-trip with distinct deterministic identities; the control assertion guards against a defect-only happy path. |
| No prohibited scope creep | Two-axis code review found no Verification Agent, fake-diff, Discovery Campaign/Run Spec, Android, or runtime additions. |

## Automated verification

| Command | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' tests/injection/test_change_target_packet.py` | `26 passed in 43.94s` |
| `uv run --with ruff ruff check src/aiverify/injection/packets.py src/aiverify/injection/__init__.py tests/injection/test_change_target_packet.py` | Passed (Ruff 0.16.4). |
| `uv run --with mypy mypy --follow-imports=skip src/aiverify/injection/packets.py src/aiverify/injection/__init__.py` | `Success: no issues found in 2 source files` (mypy 2.3.1). |
| `.venv/bin/python -m compileall -q src tests` | Passed. |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q tests/injection --junitxml=docs/runs/2026-08-23-issue-189-project-target-packet/verification/injection-pytest.xml` | `82 passed in 69.47s`; JUnit: 82 tests, 0 failures, 0 errors, 0 skipped. |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q --junitxml=docs/runs/2026-08-23-issue-189-project-target-packet/verification/full-pytest.xml` | `1228 passed, 1 skipped in 122.97s`; JUnit: 1,229 tests, 0 failures, 0 errors, 1 skipped. Wall time: 123.07s. |
| `shasum -a 256 -c SHA256SUMS` (from this run-record directory) | Both JUnit artifacts verified `OK`. |

Environment: `aiverify 0.1.0`, CPython 3.11.15, pytest 9.1.1, Git 2.50.1 (Apple Git-155), macOS host. No emulator, device, Android build, or manual runtime verification was applicable or performed.

## Review results

The standards review found no documented-standard violations. The spec review initially identified that only packet metadata, rather than the whole delivered worktree, was disclosure-scanned. A regression test was added for hidden filename and content sentinels, the compiler was changed to scan the entire tree, and the final re-review reported no remaining findings.

## Evidence artifacts

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/injection-pytest.xml` | Injection Lab JUnit report | `9ea3fcdc145611ffc7f4be52c625f0d8a7241d93ce7fcc1b71139a308a13eb9a` |
| `verification/full-pytest.xml` | Repository-wide JUnit report | `3cf7d0cd3b9c07b63056423b3374a4718e3a8bdc719ef8b1874d382c04624fbc` |
| `SHA256SUMS` | Checksum manifest for the JUnit reports | See manifest. |

There are no screenshots, layout dumps, device logs, or generated JSON artifacts for this structural packet change.

## Known gaps and follow-up risks

- The disclosure gate enforces declared-token separation structurally; it is not a semantic classifier for every possible hidden concept.
- Validation is fixture-local and deliberately does not establish a verifier outcome, discovery workflow, or runtime behavior.
- The adjacent pre-existing `VerifierPacket` name continues to represent a change-target packet; a compatibility-preserving rename or alias may be worth considering separately.
