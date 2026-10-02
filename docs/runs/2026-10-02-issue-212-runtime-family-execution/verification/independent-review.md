# Independent snapshot review — #212

Scope: six SHA-identical source/test/README files supplied to an isolated review
worktree. Read-only static review; no real devices or models, no commits. The
reviewer did not run integration tests because the mapping fixture binds the main
checkout. Test results below were obtained by the main session.

## Finding and resolution

One MEDIUM, high-confidence issue: `_preserve_artifacts` preserved raw bytes only
for `RuntimePreparationReceipt`, although the preparation API also accepts a
Mapping receipt. Accepted mapping-based preparations then lacked the artifact
required by execute-family.

Fix: preserve original bytes for typed receipts, canonical document bytes for
mapping receipts, using the same exclusive write, fsync, read-only mode and
artifact descriptor. A new test prepares mapping receipts, executes all four
lanes, and invokes the existing single-lane verifier for each attempt.

Main-session focused regression: 179 passed, 10 skipped in 42.49s.
The independent reviewer evaluated the supplied exact targeted patch and reported
that this finding is resolved, with no concrete concern about the narrow fix.
This was a targeted follow-up, not a second broad review or a new test run.

No other verified high-confidence blocker was found in the six-file snapshot.
This review does not verify #213 reduction/global verify-record, real devices,
or make a capability claim. Original independent review and targeted resolution
were delivered as agent reports; this file is their faithful summary, not a claim
that the reviewer executed the tests.
