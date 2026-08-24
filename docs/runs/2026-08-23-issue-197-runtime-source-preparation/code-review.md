# Issue #197 code review

Review fixed point: `0719a05cee1370849a553b1f9a517b3fcf0fc422`

Review method: two independent read-only reviews of the complete diff, one
against repository Standards and one against issue #197 Spec. Each reviewer
then reran a targeted review after remediation.

## Findings and remediation

The first review found that source authorities could return an unvalidated
mapping, Git-ignored files escaped source identity, packet IDs and patch bytes
were not anchored to the admitted candidate, three correlated runner handoff
parameters could contradict the legacy admission handoff, qualified or
abbreviated Gradle deployment tasks could evade a denylist, and APK bytes could
change during inspection.

The implementation was changed to:

- return immutable `HostAuthority`, `HostWorktreeIdentity`, and
  `SourceAuthorityBinding` values and validate them at the admission boundary;
- require a pristine complete tree before build, bind the complete
  build-visible tree afterward, and recheck it at handoff;
- reload the checked-in curated catalog on every sealed-source admission and
  cross-bind its candidate, patch path/bytes, package, receipt, worktree, packet,
  and canonical packet ID;
- admit only explicit Gradle `clean`/`assemble*` tasks and a bounded safe flag
  set, rejecting full and abbreviated deployment/device tasks;
- re-locate and re-hash the APK after inspection and after the final source
  authority check;
- replace the three preparation parameters with one immutable
  `RuntimePreparationHandoff` and reject contradictory legacy/prepared inputs;
- retain legacy clean-receipt compatibility only when the current complete tree
  is pristine.

The review also caught and corrected two return annotations. A proposed
`InjectedCasePackage` schema-v1 field addition was fully removed; the trusted
patch anchor now comes from the checked-in catalog without changing that schema.

## Final review outcome

- Standards: passed, no final finding. The reviewer confirmed the structured
  authority values, complete-tree binding, catalog anchor, Gradle allowlist,
  pristine-only legacy compatibility, corrected annotations, and unchanged
  `InjectedCasePackage` v1 schema.
- Spec: passed, no final implementation finding. Targeted reproductions rejected
  `:app:instDeb`, a self-consistent replacement packet/admission, ignored-byte
  legacy drift, APK mutation during inspection, and APK mutation during the
  second source-authority check. The pristine legacy receipt remained accepted.
- Scope: no real Android runtime, device/adb/Codex invocation, OpenCalc/Catima
  action, Discovery/oracle work, caching, batching, or public preparation CLI was
  added.

Final regression evidence is recorded in `verification/` and `verification.json`.
