# Invocation record

- Agent role: the exactly one separate Verification Agent required by issue #72
- Collaboration task: `/root/issue72_verification`
- Mode: read-only repository and evidence audit
- Prompt: `prompt.md`
- Output: `conclusion.json`
- Constraint: the agent was instructed not to edit files or post externally

The collaboration interface returns the final structured answer but does not
provide a durable raw internal transcript. The exact prompt and a schema-valid,
format-normalized preservation of the returned conclusion, checks, evidence,
and limitations are retained as the auditable invocation boundary.
