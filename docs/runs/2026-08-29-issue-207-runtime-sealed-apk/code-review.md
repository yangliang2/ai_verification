# Issue #207 review record

Review fixed point: `e015604` (final working-tree implementation reviewed
before evidence commit).

## Standards review

The review checked the public preparation, command-runner, CLI, execution
identity, and test seams against the repository guidance, `CONTEXT.md`, the
runtime calibration ADRs, and the existing clean-checkout contract.

Findings and resolutions:

- Test-substitute receipts now carry an explicit `test_substitutes` marker and
  the CLI rejects them before an `ExecutionRecord` is established.
- Strict production preparation and receipt re-verification require the exact
  mapped authority/delegate, isolated `SubprocessCommandRunner`, and exact
  `AaptApkInspector` tool path/signing bindings. Substitute collaborators remain
  available only behind the explicit test flag.
- Sealed execution identity is bound to one canonical, read-only,
  single-link `build/app-debug.apk` under the lane artifact directory, with an
  immediate pre-deployment rehash.
- Parent symlink components, malformed expected metadata, and environment/tool
  classification are checked with stable failures.

The remaining path-based deployment TOCTOU limitation is explicit in the run
record: the runner revalidates immediately before Android invocation and after
deployment, but this slice does not introduce an OS-level file-handle API.

## Specification review

The acceptance review checked the released mapping, candidate inputs, source
authority, vault/signing inventory, exact offline vector, APK inspection,
sealing, rejection paths, runner handoff, and claim boundary.

Findings and resolutions:

- Production mapped preparation requires a full `RuntimeMappingRelease`, its
  candidate root, a sealed-injection delegate, and release family/version
  matching the Runtime Input Vault. Candidate projection, driver plan, recipe,
  and Run Spec bytes are rechecked before build.
- Production tool validation requires recipe-bound identities for the Gradle
  executable, Java executable, `aapt2`, and `apksigner`; the signer certificate
  and apksigner digest are also rechecked through the vault identity.
- Inspector and runner trust checks happen before inspection/build use during
  receipt re-verification. The existing legacy clean-checkout preparation path
  remains compatible, while mapped runtime handoffs require a sealed artifact.
- Vault and private-copy traversal rejects symlink components, extra/missing
  files, mutable files, and hard links; family binding and private-home
  isolation are recorded in the receipt.
- The durable run record, JUnit reports, review record, and checksum inventory
  are included under this directory.

No unresolved acceptance blocker remains within the implemented side-effect-free
handoff. Real Gradle/aapt2/apksigner/device execution is intentionally not
claimed by this issue; the successful public path uses the explicitly recorded
test substitutes.
