#!/bin/zsh
# Run the approved local-only prospective control/candidate repetitions.
set -u

PROJECT_ROOT="${1:-/Users/peter/projects/ai_verification-issue-86}"
SOURCE_ROOT="${2:-/Users/peter/projects/wikipedia-m6-historical}"
RUN_ROOT="${PROJECT_ROOT}/docs/runs/2026-08-03-issue-87-prospective-formal"
DEVICE="emulator-5554"
JAVA_HOME_VALUE="/opt/homebrew/opt/openjdk@17"
BASE_REV=79ef892e5e88dfea705350bbfa1be2ee14458b47

typeset -a SLOTS=(P-01 P-02 P-03)
typeset -A CANDIDATE FIXTURE TEST_CLASS
CANDIDATE[P-01]=bb9a5a5c2c7ae616ee7c560b5688697c09d60f9f
FIXTURE[P-01]=bench/m6/admission-fixtures/prospective/replacement-t425733/M6T425733OnboardingThemeTest.kt
TEST_CLASS[P-01]=org.wikipedia.m6.M6T425733OnboardingThemeTest
CANDIDATE[P-02]=2a957912de43cc43e87f8ed81b34a1755ed0a737
FIXTURE[P-02]=bench/m6/admission-fixtures/prospective/replacement-t426893/M6T426893GalleryMetadataOfflineTest.kt
TEST_CLASS[P-02]=org.wikipedia.m6.M6T426893GalleryMetadataOfflineTest
CANDIDATE[P-03]=a6d33f1479c2a52ff5c4b13bb11242755c614993
FIXTURE[P-03]=bench/m6/admission-fixtures/prospective/replacement-t427224/M6T427224ReadMoreLifecycleTest.kt
TEST_CLASS[P-03]=org.wikipedia.m6.M6T427224ReadMoreLifecycleTest

typeset -a fixture_targets
cleanup_fixtures() {
  for target in $fixture_targets; do
    if [[ -f "$target" ]]; then unlink "$target"; fi
  done
  fixture_targets=()
}
cleanup_generated() {
  find "$SOURCE_ROOT/analytics" -type f -path '*/build/*' -delete 2>/dev/null || true
  find "$SOURCE_ROOT/analytics" -depth -type d -empty -path '*/build*' -delete 2>/dev/null || true
}
cleanup_all() {
  cleanup_fixtures
  cleanup_generated
}
trap cleanup_all EXIT INT TERM

mkdir -p "$RUN_ROOT"
printf 'formal_run_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$RUN_ROOT/run-start.txt"
printf 'project_commit=%s\n' "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" >> "$RUN_ROOT/run-start.txt"
printf 'source_remote=%s\n' "$(git -C "$SOURCE_ROOT" remote get-url origin)" >> "$RUN_ROOT/run-start.txt"
printf 'base_revision=%s\n' "$BASE_REV" >> "$RUN_ROOT/run-start.txt"
printf 'device=%s\n' "$DEVICE" >> "$RUN_ROOT/run-start.txt"

run_lane() {
  local slot="$1"
  local state="$2"
  local revision="$3"
  local lane_root="$RUN_ROOT/lanes/${slot:l}-${state}"
  local fixture_target="$SOURCE_ROOT/app/src/androidTest/java/org/wikipedia/m6/$(basename "${FIXTURE[$slot]}")"
  local build_rc deploy_rc test_rc repetition attempt_dir
  mkdir -p "$lane_root"
  cleanup_fixtures
  git -C "$SOURCE_ROOT" checkout --detach "$revision" > "$lane_root/checkout.txt" 2>&1
  local checkout_rc=$?
  printf 'checkout_exit_code=%s\nrevision=%s\n' "$checkout_rc" "$revision" >> "$lane_root/checkout.txt"
  if (( checkout_rc != 0 )); then return "$checkout_rc"; fi
  mkdir -p "${fixture_target:h}"
  cp "$PROJECT_ROOT/${FIXTURE[$slot]}" "$fixture_target"
  fixture_targets=("$fixture_target")
  printf 'fixture=%s\nfixture_sha256=%s\n' "${FIXTURE[$slot]}" "$(/usr/bin/shasum -a 256 "$fixture_target" | awk '{print $1}')" > "$lane_root/fixture.txt"
  (
    cd "$SOURCE_ROOT" || exit 1
    JAVA_HOME="$JAVA_HOME_VALUE" /usr/bin/time -p ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest --offline --no-daemon
  ) > "$lane_root/build.txt" 2>&1
  build_rc=$?
  printf 'build_exit_code=%s\n' "$build_rc" >> "$lane_root/build.txt"
  if (( build_rc != 0 )); then return "$build_rc"; fi
  local apk="$SOURCE_ROOT/app/build/outputs/apk/dev/debug/app-dev-debug.apk"
  local test_apk="$SOURCE_ROOT/app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk"
  printf 'apk_path=%s\napk_sha256=%s\ntest_apk_path=%s\ntest_apk_sha256=%s\n' \
    "$apk" "$(/usr/bin/shasum -a 256 "$apk" | awk '{print $1}')" \
    "$test_apk" "$(/usr/bin/shasum -a 256 "$test_apk" | awk '{print $1}')" > "$lane_root/apk-receipt.txt"
  adb -s "$DEVICE" shell pm clear org.wikipedia.dev > "$lane_root/deploy.txt" 2>&1
  adb -s "$DEVICE" install -r -d "$apk" >> "$lane_root/deploy.txt" 2>&1
  adb -s "$DEVICE" install -r -d "$test_apk" >> "$lane_root/deploy.txt" 2>&1
  deploy_rc=$?
  printf 'installed_binary=%s\n' "$(adb -s "$DEVICE" shell pm path org.wikipedia.dev 2>&1 | tr -d '\r')" >> "$lane_root/deploy.txt"
  printf 'deploy_exit_code=%s\n' "$deploy_rc" >> "$lane_root/deploy.txt"
  if (( deploy_rc != 0 )); then return "$deploy_rc"; fi
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
  cleanup_fixtures
  return 0
}

# One control build contains all three frozen fixtures; its APK is the common
# source/control identity for the three case packages.
for slot in $SLOTS; do
  target="$SOURCE_ROOT/app/src/androidTest/java/org/wikipedia/m6/$(basename "${FIXTURE[$slot]}")"
  mkdir -p "${target:h}"
  cp "$PROJECT_ROOT/${FIXTURE[$slot]}" "$target"
  fixture_targets+=($target)
done
base_root="$RUN_ROOT/lanes/control-base"
mkdir -p "$base_root"
git -C "$SOURCE_ROOT" checkout --detach "$BASE_REV" > "$base_root/checkout.txt" 2>&1
base_checkout_rc=$?
printf 'checkout_exit_code=%s\nrevision=%s\n' "$base_checkout_rc" "$BASE_REV" >> "$base_root/checkout.txt"
if (( base_checkout_rc != 0 )); then exit "$base_checkout_rc"; fi
(
  cd "$SOURCE_ROOT" || exit 1
  JAVA_HOME="$JAVA_HOME_VALUE" /usr/bin/time -p ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest --offline --no-daemon
) > "$base_root/build.txt" 2>&1
base_build_rc=$?
printf 'build_exit_code=%s\n' "$base_build_rc" >> "$base_root/build.txt"
if (( base_build_rc != 0 )); then exit "$base_build_rc"; fi
base_apk="$SOURCE_ROOT/app/build/outputs/apk/dev/debug/app-dev-debug.apk"
base_test_apk="$SOURCE_ROOT/app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk"
printf 'apk_path=%s\napk_sha256=%s\ntest_apk_path=%s\ntest_apk_sha256=%s\n' \
  "$base_apk" "$(/usr/bin/shasum -a 256 "$base_apk" | awk '{print $1}')" \
  "$base_test_apk" "$(/usr/bin/shasum -a 256 "$base_test_apk" | awk '{print $1}')" > "$base_root/apk-receipt.txt"
adb -s "$DEVICE" shell pm clear org.wikipedia.dev > "$base_root/deploy.txt" 2>&1
adb -s "$DEVICE" install -r -d "$base_apk" >> "$base_root/deploy.txt" 2>&1
adb -s "$DEVICE" install -r -d "$base_test_apk" >> "$base_root/deploy.txt" 2>&1
base_deploy_rc=$?
printf 'installed_binary=%s\n' "$(adb -s "$DEVICE" shell pm path org.wikipedia.dev 2>&1 | tr -d '\r')" >> "$base_root/deploy.txt"
printf 'deploy_exit_code=%s\n' "$base_deploy_rc" >> "$base_root/deploy.txt"
if (( base_deploy_rc != 0 )); then exit "$base_deploy_rc"; fi
for slot in $SLOTS; do
  for repetition in 1 2 3; do
    attempt_dir="$RUN_ROOT/lanes/${slot:l}-control/repetition-${repetition}"
    mkdir -p "$attempt_dir"
    printf 'slot=%s\nsource_state=control\nrevision=%s\nrepetition=%s\nlane_id=%s-control-%02d\n' "$slot" "$BASE_REV" "$repetition" "$slot" "$repetition" > "$attempt_dir/metadata.txt"
    adb -s "$DEVICE" shell pm clear org.wikipedia.dev > "$attempt_dir/clear.txt" 2>&1
    (/usr/bin/time -p adb -s "$DEVICE" shell am instrument -w -e class "${TEST_CLASS[$slot]}" org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner) > "$attempt_dir/instrumentation.txt" 2>&1
    test_rc=$?
    printf 'instrumentation_exit_code=%s\n' "$test_rc" >> "$attempt_dir/instrumentation.txt"
  done
done
cleanup_fixtures

for slot in $SLOTS; do
  run_lane "$slot" candidate "${CANDIDATE[$slot]}"
  lane_rc=$?
  if (( lane_rc != 0 )); then exit "$lane_rc"; fi
done

git -C "$SOURCE_ROOT" checkout --detach "$BASE_REV" > "$RUN_ROOT/final-checkout.txt" 2>&1
printf 'formal_run_finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RUN_ROOT/run-start.txt"
