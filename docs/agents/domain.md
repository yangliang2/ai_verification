# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This is a single-context repo.

Read:

- `CONTEXT.md` at the repo root for domain language.
- `docs/adr/` for architectural decisions relevant to the area being changed.
- `.omc/specs/` and `.omc/plans/` when the task concerns product scope, acceptance criteria, or implementation sequencing.
- `HANDOFF.md` when the task concerns current implementation state or next wiring steps.

## Use the glossary's vocabulary

When your output names a domain concept in an issue title, refactor proposal, hypothesis, test name, or PRD, use the term defined in `CONTEXT.md`. Do not drift to synonyms that the glossary explicitly avoids.

If the concept you need is not in the glossary yet, either reconsider whether the language belongs to this project or note it for `grill-with-docs`.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> Contradicts ADR-0001 — worth reopening because...
