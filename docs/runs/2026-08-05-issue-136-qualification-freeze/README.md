# M9 #136 candidate qualification packet

Status: candidate preparation only. Human approval is required before any
qualification manifest, hidden-mapping commitment, RunSpec admission receipt,
freeze merge, device action, agent invocation, or formal lane.

This record is intentionally not a completed M9 qualification. It records the
side-effect-free candidate work performed against the exact merged
implementation commit available when this branch was created:

- implementation commit: `d3e03dc036a1fb8d0f7f314e7999b58294399242`;
- candidate source: `https://github.com/android/architecture-samples.git`;
- candidate source commit: `ee66e1526b84c026615df032c705842b7d2a521f`;
- candidate source tree: `19455e693ec8c96c37a56aec55059a220826c5a3`;
- candidate source index manifest SHA-256: `66fa95486f2c63e84dbb1ba1dd77a43ad34cdd6ecbd8c659e496e9a204e38585`;
- local candidate checkout used for preflight: `/private/tmp/m9-136-candidate-architecture-samples`.

Three unselected pair mutations were also materialized in separate temporary
worktrees and compiled successfully. Their exact patch, APK, and build-log
hashes are recorded in `candidate-pair-builds.json`; these are candidate
decision artifacts, not frozen lane inputs.

## Human gate status

The human has selected candidate option A for further preparation. This is not
the final freeze approval: the clear lane mapping is absent, no commitment has
been created, and the opaque lane order and remaining freeze contract are not
approved. The packet therefore does not claim that this public project is the
final unfamiliar target or that any formal lane is approved.

The human decision still needs to approve the exact source snapshot, matched
defect/control pair, three defect lanes and three control lanes, lane order,
mapping commitment/release procedure, oracle/evidence/review contracts,
one-attempt/zero-retry/zero-replacement and abort rules, and local-only claim
boundary.

## Candidate preflight

Commands and results:

1. `git ls-remote https://github.com/android/architecture-samples.git HEAD`
   returned `ee66e1526b84c026615df032c705842b7d2a521f`.
2. `git clone --depth 1 --filter=blob:none --no-tags --no-checkout
   https://github.com/android/architecture-samples.git
   /private/tmp/m9-136-candidate-architecture-samples` completed; checkout was
   detached at the commit above.
3. `git rev-parse HEAD^{tree}` returned
   `19455e693ec8c96c37a56aec55059a220826c5a3`.
4. `./gradlew --no-daemon --no-configuration-cache --max-workers=1
   :app:assembleDebug` completed successfully: 43 actionable tasks, Gradle
   reported `BUILD SUCCESSFUL in 2m 52s`.
5. `./gradlew --offline --no-daemon --no-configuration-cache
   --max-workers=1 :app:assembleDebug` was also attempted and failed closed
   because the local cache lacked several candidate dependencies. This does not
   invalidate the online host build; it records the environment limitation.
6. `apkanalyzer manifest application-id app/build/outputs/apk/debug/app-debug.apk`
   returned `com.example.android.architecture.blueprints.main`.
7. `apkanalyzer manifest min-sdk app/build/outputs/apk/debug/app-debug.apk`
   returned `21`; target SDK returned `35`.

No `android`, `adb`, device, install, launch, runtime, Verification Agent
Backend, oracle, or Falsification Review invocation occurred. The successful
build is candidate-only host-side evidence.

## Artifact inventory

The candidate checkout and generated preflight artifacts remain outside the
repository because the source is an immutable public-project candidate, not a
committed project target. Their locations and checksums are recorded in
`candidate-preflight.json`:

- source commit/tree/index identity;
- successful and failed build logs;
- APK metadata and APK SHA-256;
- Gradle, Java, Android CLI, and adb identities.

This external inventory is local-only until a human approves the exact target
and the final freeze packet is committed and merged. No formal denominator or
M9 result may be inferred from it.

## Known gaps and boundary

- Human has not approved the candidate target or unfamiliarity.
- Candidate A has been materialized and built, but the matched pair is not
  frozen until the remaining human contract fields are approved.
- No clear mapping or commitment exists.
- No candidate option has been approved; the three compiled options remain
  mutually exclusive decision material only.
- No six serialized RunSpecs or runner-policy pairs exist yet.
- No admission receipt, contradiction execution, build-on-frozen-variant,
  device action, agent invocation, oracle, Finding, ResidualRisk, Project Risk
  Map, or independent review exists.
- This record makes no production, upstream, OEM/ColorOS, rate, completeness,
  benchmark, or automated-repair claim.
