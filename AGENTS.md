# Agent Guidance

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `yangliang2/ai_verification`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Matt Pocock triage label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. Read root `CONTEXT.md` and relevant ADRs under `docs/adr/`. See `docs/agents/domain.md`.

## Issue evidence discipline

When completing or closing a GitHub issue, do not leave only a summary. Record enough evidence for a later agent or human reviewer to audit what happened without relying on chat history.

For every completed implementation issue, add an issue comment that includes:
- The exact verification commands that were run.
- The important command results, including pass/fail counts, build duration, package/app identifiers, and relevant tool versions when applicable.
- The files, modules, or tests that implement the acceptance criteria.
- Any real-device/emulator/manual verification steps that were performed.
- The evidence artifact location, preferably a durable repo path such as `docs/runs/<date>-<slug>/`; if evidence must remain outside the repo, explain why and include the absolute path.
- Artifact inventory for screenshots, layout dumps, logs, reports, or generated JSON.
- Checksums for important external artifacts when practical.
- Known gaps, skipped checks, or follow-up risks.

For parent PRDs or umbrella issues, add a progress comment that links child issues and points to the run record. Keep open work explicitly labeled as agent-ready or human-required.

Prefer creating a durable run record under `docs/runs/` for non-trivial validation work. The issue comment should link to that run record instead of depending on ephemeral `/tmp` paths or conversation context.

Run records and their evidence artifacts are not complete until they are committed with the code or documentation change they justify. If committing is not possible in the current turn, explicitly say why, keep the issue comment clear that the evidence is local-only, and do not present it as durable GitHub evidence.
