# Independent Verification Agent invocation

The authoritative independent audit ran in a separate Codex CLI process with a
read-only sandbox and no model override:

```sh
/usr/bin/time -p codex exec --json \
  --output-schema bench/capability-slices/lifecycle-recovery/independent-conclusion-schema.json \
  --output-last-message docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/independent-verification/conclusion.json \
  --skip-git-repo-check \
  --cd /Users/peter/projects/ai_verification-issue-71 \
  --sandbox read-only \
  - < docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/independent-verification/prompt.md \
  2>&1 | tee docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/independent-verification/events.jsonl
```

- Codex CLI: `0.144.5`
- Successful independent thread: `019f7944-9b71-7bf1-ab39-f777b855f64a`
- Wall/user/system time: `808.92 / 14.65 / 7.28` seconds
- Sandbox: `read-only`
- Authoritative output protocol: `--output-last-message conclusion.json`
- Result: `locally_supported`, `accountable=true`, 11/11 evidence checks passed

The raw JSONL transcript contains progress messages required by the agent
runtime. Those messages explicitly identify themselves as interim and are not
conclusion artifacts. `conclusion.json` is the one authoritative output object;
`validation.txt` proves it is schema-valid, contains exactly one `conclusion`
key, matches the final agent message, and belongs to the single completed turn.

An earlier process, thread `019f7944-0f29-7e81-8968-c45b40375110`, stopped
before any conclusion because the first schema draft omitted the explicit type
for `schema_version`. Its `invalid_json_schema` response is retained as
`events-attempt-0-invalid-schema.jsonl`; it produced no conclusion and is not an
audit attempt.

## Frozen artifact hashes

```text
2b1abb2d4c3e32847b59775adc9805d3af514a921a2c3436a3eff7bd6fce957a  prompt.md
f3be4e8b7a1ee683eaac034f89ca0e0a17a467e2240503c375e7f9a7ae5d0b88  events.jsonl
6cb8d2900c0765fa6b36af7ee34e76c7357a4447a0231746a600bcf8ce630228  conclusion.json
8e6bd9aeeaf2b168dd4ad33c91c7c12be7fd58a53e08a7a4bcfa1e6cd5a0a343  independent-conclusion-schema.json
```
