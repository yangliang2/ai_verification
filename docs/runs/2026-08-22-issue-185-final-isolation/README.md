# Issue #185 — final materialization-isolation verification

This is the final local verification record for the M0.1 curated-candidate
materialization change at implementation commits
`472c73bdbb05adf32087a7f72aa57d860afbda0e` and
`02c4f7f030c66d22e777b7333ff26106a41f58c4`
(`fix(injection): bind materialization Git state` and
`fix(injection): synchronize materialized index`). It is a hermetic
temporary-Git-repository validation; it does not build, install, or run an
Android application.

- Issue: [#185](https://github.com/yangliang2/ai_verification/issues/185)
- Branch: `issue-185-curated-candidate-materialization`
- Runtime: CPython 3.11.15
- Test runner: pytest 9.1.1
- Git: `git version 2.50.1 (Apple Git-155)`

## Implemented acceptance boundaries

- `src/aiverify/injection/materialization.py` gives each fresh worktree a
  materializer-private Git index, so concurrent updates to the linked
  worktree's normal index cannot add an undeclared delta or desynchronize the
  result tree from its canonical diff identity. After verification, it
  synchronizes the normal index from the verified private tree, so the owned
  worktree remains a conventional detached Git worktree without making the
  receipt depend on that mutable index.
- Fresh-worktree registration finds the administrative directory through the
  caller common directory's immutable backlink, binds the worktree `.git`
  control-file identity, and makes subsequent Git calls use that explicit
  administrative directory. A replacement `.git` file therefore cannot point
  materialization or cleanup at another linked worktree or the caller index.
- Cleanup clears retained administrative state before source state and records
  each completed phase in memory. If the second descriptor-only clear fails,
  the same receipt can retry the remaining phase without relying on an already
  removed ownership marker.
- `tests/injection/test_materialization.py` adds deterministic temporary-repo
  regression coverage for caller `core.worktree`, default-index injection both
  before patch application and after diff generation, `.git` swaps before and
  after registration, redirected cleanup, and retry after a second clear fails.

## Verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication` at the implementation
commit above.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src
```

Exited 0.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -o addopts='' -q \
  tests/injection/test_materialization.py \
  --junitxml=docs/runs/2026-08-22-issue-185-final-isolation/verification/focused-pytest.xml
```

Result: `35 passed in 21.62s` (JUnit test time: 19.984s).

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -o addopts='' -q \
  --junitxml=docs/runs/2026-08-22-issue-185-final-isolation/verification/full-pytest.xml
```

Result: `1182 passed, 1 skipped in 69.422s` (the single skipped test is recorded
in the JUnit report; there were zero failures and zero errors).

```sh
git diff --check
```

Exited 0 before committing the implementation; the evidence files below are the
only new files in this record.

```sh
(cd docs/runs/2026-08-22-issue-185-final-isolation && shasum -a 256 -c SHA256SUMS)
```

Both JUnit artifacts verified.

## Evidence inventory

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/focused-pytest.xml` | Materialization-focused JUnit result, 35 tests | `96687d33d6dbc73398f9250e883a3a2845ffe5c793aa7b0c313e96cbd331d147` |
| `verification/full-pytest.xml` | Full repository JUnit result, 1,182 tests | `448e7edfcf3f3a46224bd873eeea1d1aed42ce37cf5455276826e59e78225317` |
| `SHA256SUMS` | Machine-readable checksum inventory | See file |

No screenshots, Android builds, emulators, devices, providers, formal admission,
or metrics were used. That is intentional: #185 is limited to safe local source
materialization and must not broaden into execution or benchmark admission.

## Known limits

The receipt remains intentionally process-local: only the creating
`InjectionMaterializer` retains the descriptor authorities required for cleanup.
A serialized receipt or a new materializer instance cannot remove any worktree.
On an authority mismatch, cleanup fails closed and leaves the external state
untouched rather than attempting pathname-based recovery.
