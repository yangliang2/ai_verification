#!/bin/zsh
# Reproduce the approved, local-only M6 historical qualification lanes.
# The source checkout is detached and receives only temporary fixture copies.
set -u

PROJECT_ROOT="${1:-/Users/peter/projects/ai_verification-issue-86}"
SOURCE_ROOT="${2:-/Users/peter/projects/wikipedia-m6-historical}"
RUN_ROOT="${PROJECT_ROOT}/docs/runs/2026-08-03-issue-86-historical-formal"
DEVICE="emulator-5554"
JAVA_HOME_VALUE="/opt/homebrew/opt/openjdk@17"

typeset -a SLOTS=(H-01 H-02 H-03)
typeset -A PRE_REV FIX_REV FIXTURE TEST_CLASS
PRE_REV[H-01]=b88c6a672e18167727fcc9d913c9ed57e50e03ce
FIX_REV[H-01]=996ad8592fbd41e59ea195da72a3e9a728181006
FIXTURE[H-01]=bench/m6/admission-fixtures/historical/h-01/M6H01WiktionaryStyleTagsTest.kt
TEST_CLASS[H-01]=org.wikipedia.m6.M6H01WiktionaryStyleTagsTest
PRE_REV[H-02]=675b930624c80498b3d3881592ac1c3f179a2709
FIX_REV[H-02]=c7250ce14feaa24e52d3a2468fb86b15fa56cfff
FIXTURE[H-02]=bench/m6/admission-fixtures/historical/h-02/M6H02LocalSearchLanguageTest.kt
TEST_CLASS[H-02]=org.wikipedia.m6.M6H02LocalSearchLanguageTest
PRE_REV[H-03]=d67ec44adc1d8c4d8dc7dcb736c0faa9f1b6934c
FIX_REV[H-03]=fdc4ffb9ef3be93a96500bf630057c1e66ac7b8f
FIXTURE[H-03]=bench/m6/admission-fixtures/historical/h-03/M6H03ActivityResultCodesTest.kt
TEST_CLASS[H-03]=org.wikipedia.m6.M6H03ActivityResultCodesTest

fixture_target=""
cleanup() {
  if [[ -n "$fixture_target" && -f "$fixture_target" ]]; then
    unlink "$fixture_target"
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "$RUN_ROOT"
printf 'formal_run_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$RUN_ROOT/run-start.txt"
printf 'project_commit=%s\n' "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" >> "$RUN_ROOT/run-start.txt"
printf 'source_remote=%s\n' "$(git -C "$SOURCE_ROOT" remote get-url origin)" >> "$RUN_ROOT/run-start.txt"
printf 'device=%s\n' "$DEVICE" >> "$RUN_ROOT/run-start.txt"

for slot in $SLOTS; do
  for state in pre-fix fixed; do
    revision="${PRE_REV[$slot]}"
    [[ "$state" == fixed ]] && revision="${FIX_REV[$slot]}"
    slot_key="${slot:l}"
    state_key="${state//-/_}"
    lane_root="$RUN_ROOT/lanes/${slot_key}-${state_key}"
    mkdir -p "$lane_root"

    fixture_target="$SOURCE_ROOT/app/src/androidTest/java/org/wikipedia/m6/$(basename "${FIXTURE[$slot]}")"
    if [[ -f "$fixture_target" ]]; then unlink "$fixture_target"; fi
    git -C "$SOURCE_ROOT" checkout --detach "$revision" > "$lane_root/checkout.txt" 2>&1
    checkout_rc=$?
    printf 'checkout_exit_code=%s\nrevision=%s\n' "$checkout_rc" "$revision" >> "$lane_root/checkout.txt"
    if (( checkout_rc != 0 )); then exit "$checkout_rc"; fi
    mkdir -p "${fixture_target:h}"
    cp "$PROJECT_ROOT/${FIXTURE[$slot]}" "$fixture_target"
    printf 'fixture=%s\nfixture_sha256=%s\n' "${FIXTURE[$slot]}" "$(shasum -a 256 "$fixture_target" | awk '{print $1}')" > "$lane_root/fixture.txt"

    (
      cd "$SOURCE_ROOT" || exit 1
      JAVA_HOME="$JAVA_HOME_VALUE" /usr/bin/time -p ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest --offline --no-daemon
    ) > "$lane_root/build.txt" 2>&1
    build_rc=$?
    printf 'build_exit_code=%s\n' "$build_rc" >> "$lane_root/build.txt"
    if (( build_rc != 0 )); then exit "$build_rc"; fi

    apk="$SOURCE_ROOT/app/build/outputs/apk/dev/debug/app-dev-debug.apk"
    test_apk="$SOURCE_ROOT/app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk"
    printf 'apk_path=%s\napk_sha256=%s\ntest_apk_path=%s\ntest_apk_sha256=%s\n' \
      "$apk" "$(shasum -a 256 "$apk" | awk '{print $1}')" \
      "$test_apk" "$(shasum -a 256 "$test_apk" | awk '{print $1}')" > "$lane_root/apk-receipt.txt"

    adb -s "$DEVICE" shell pm clear org.wikipedia.dev > "$lane_root/deploy.txt" 2>&1
    adb -s "$DEVICE" install -r -d "$apk" >> "$lane_root/deploy.txt" 2>&1
    adb -s "$DEVICE" install -r -d "$test_apk" >> "$lane_root/deploy.txt" 2>&1
    deploy_rc=$?
    printf 'installed_binary=%s\n' "$(adb -s "$DEVICE" shell pm path org.wikipedia.dev 2>&1 | tr -d '\r')" >> "$lane_root/deploy.txt"
    printf 'deploy_exit_code=%s\n' "$deploy_rc" >> "$lane_root/deploy.txt"
    if (( deploy_rc != 0 )); then exit "$deploy_rc"; fi

    for repetition in 1 2 3; do
      attempt_dir="$lane_root/repetition-${repetition}"
      mkdir -p "$attempt_dir"
      printf 'slot=%s\nsource_state=%s\nrevision=%s\nrepetition=%s\nlane_id=%s-%s-%02d\n' \
        "$slot" "$state" "$revision" "$repetition" "$slot" "$state" "$repetition" > "$attempt_dir/metadata.txt"
      adb -s "$DEVICE" shell pm clear org.wikipedia.dev > "$attempt_dir/clear.txt" 2>&1
      (
        /usr/bin/time -p adb -s "$DEVICE" shell am instrument -w \
          -e class "${TEST_CLASS[$slot]}" \
          org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
      ) > "$attempt_dir/instrumentation.txt" 2>&1
      test_rc=$?
      printf 'instrumentation_exit_code=%s\n' "$test_rc" >> "$attempt_dir/instrumentation.txt"
    done
    cleanup
    fixture_target=""
  done
done

git -C "$SOURCE_ROOT" checkout --detach "${FIX_REV[H-03]}" > "$RUN_ROOT/final-checkout.txt" 2>&1
printf 'formal_run_finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RUN_ROOT/run-start.txt"
