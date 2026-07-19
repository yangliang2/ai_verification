"""System event injection adapter for runner flows."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from aiverify.harness.device import AdbResult, DeviceController
from aiverify.runner.run_spec import SystemEventSpec


class SystemEventInjectionError(ValueError):
    """Raised when a system event cannot be injected from the provided context."""


@dataclass
class DeviceSystemEventInjector:
    """Inject Run Spec system events through DeviceController.

    activity: launcher activity（或 alias）完整类名，process_death 恢复及
    app_to_foreground 显式拉起使用；debug 构建常有多个 LAUNCHER activity，
    缺省的 monkey 拉起不确定。
    """

    device: DeviceController
    package: str
    activity: str | None = None

    def inject(self, event: SystemEventSpec) -> dict[str, Any] | None:
        """Inject one system event at a Journey Segment Boundary."""
        if event.event == "rotate":
            raw_rotation = event.args.get("rotation", "1")
            try:
                rotation = int(raw_rotation)
            except ValueError:
                rotation = -1
            if rotation not in {0, 1, 2, 3}:
                raise SystemEventInjectionError(
                    "rotate requires args.rotation to be one of 0, 1, 2, 3; "
                    f"got {raw_rotation!r}"
                )
            self._require_success(event.event, self.device.rotate(rotation))
            automatic = self.device.get_accelerometer_rotation()
            self._require_success(event.event, automatic)
            automatic_value = automatic.stdout.strip()
            if automatic_value != "0":
                raise SystemEventInjectionError(
                    "rotate postcondition failed: "
                    "expected accelerometer_rotation=0, "
                    f"observed {automatic_value!r}"
                )
            observed = self.device.get_user_rotation()
            self._require_success(event.event, observed)
            actual = observed.stdout.strip()
            if actual != str(rotation):
                raise SystemEventInjectionError(
                    "rotate postcondition failed: "
                    f"expected user_rotation={rotation}, observed {actual!r}"
                )
            return {
                "accelerometer_rotation": automatic_value,
                "user_rotation": actual,
            }
        if event.event == "kill_background":
            before = self.device.get_pid(self.package)
            self._require_success(event.event, before)
            self._parse_running_pids(event.event, before)
            self._require_success(
                event.event, self.device.kill_background(self.package)
            )
            after = self.device.get_pid(self.package)
            if after.returncode == 0:
                remaining = sorted(self._parse_running_pids(event.event, after))
                raise SystemEventInjectionError(
                    "kill_background postcondition failed: process remains running "
                    f"with pid(s) {', '.join(remaining)}"
                )
            if after.returncode != 1 or after.stdout.strip() or after.stderr.strip():
                self._require_success(event.event, after)
            return
        if event.event == "revoke_permission":
            permission = event.args.get("permission")
            if not permission:
                raise SystemEventInjectionError("revoke_permission requires args.permission")
            self._require_success(
                event.event, self.device.revoke_permission(self.package, permission)
            )
            observed = self.device.dump_package_state(self.package)
            self._require_success(event.event, observed)
            grant = re.search(
                rf"^\s*{re.escape(permission)}:\s+granted=(true|false)(?:,|\s*$)",
                observed.stdout,
                flags=re.MULTILINE,
            )
            if grant is None:
                raise SystemEventInjectionError(
                    "revoke_permission postcondition failed: could not find "
                    f"runtime permission {permission} in package state"
                )
            if grant.group(1) != "false":
                raise SystemEventInjectionError(
                    "revoke_permission postcondition failed: "
                    f"{permission} remains granted"
                )
        if event.event == "open_app_settings":
            timeout_seconds, poll_interval_seconds = self._postcondition_polling(
                event
            )
            self._require_success(
                event.event, self.device.open_app_settings(self.package)
            )
            self._wait_for_exact_resumed_package(
                event.event,
                expected_package="com.android.settings",
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
        )
            return
        if event.event == "network_off":
            self._require_success(event.event, self.device.set_wifi(enabled=False))
            self._require_success(
                event.event, self.device.set_mobile_data(enabled=False)
            )
            wifi = self.device.get_wifi_setting()
            self._require_success(event.event, wifi)
            wifi_value = wifi.stdout.strip()
            if wifi_value != "0":
                raise SystemEventInjectionError(
                    "network_off postcondition failed: "
                    f"expected wifi_on=0, observed {wifi_value!r}"
                )
            mobile_data = self.device.get_mobile_data_setting()
            self._require_success(event.event, mobile_data)
            mobile_data_value = mobile_data.stdout.strip()
            if mobile_data_value != "0":
                raise SystemEventInjectionError(
                    "network_off postcondition failed: "
                    f"expected mobile_data=0, observed {mobile_data_value!r}"
                )
            return
        if event.event == "network_on":
            self._require_success(event.event, self.device.set_wifi(enabled=True))
            self._require_success(
                event.event, self.device.set_mobile_data(enabled=True)
            )
            wifi = self.device.get_wifi_setting()
            self._require_success(event.event, wifi)
            wifi_value = wifi.stdout.strip()
            if wifi_value != "1":
                raise SystemEventInjectionError(
                    "network_on postcondition failed: "
                    f"expected wifi_on=1, observed {wifi_value!r}"
                )
            mobile_data = self.device.get_mobile_data_setting()
            self._require_success(event.event, mobile_data)
            mobile_data_value = mobile_data.stdout.strip()
            if mobile_data_value != "1":
                raise SystemEventInjectionError(
                    "network_on postcondition failed: "
                    f"expected mobile_data=1, observed {mobile_data_value!r}"
                )
            return
        if event.event == "wait":
            if not any(
                key in event.args for key in ("expect_network", "expect_resumed")
            ):
                raise SystemEventInjectionError(
                    "wait requires expect_network or expect_resumed postcondition"
                )
            try:
                seconds = float(event.args["seconds"])
            except (KeyError, TypeError, ValueError) as error:
                raise SystemEventInjectionError(
                    "wait requires finite args.seconds between 0 and 60"
                ) from error
            if not math.isfinite(seconds) or not 0 <= seconds <= 60:
                raise SystemEventInjectionError(
                    "wait requires finite args.seconds between 0 and 60"
                )
            expected_network = event.args.get("expect_network")
            if expected_network is not None and expected_network not in {
                "off",
                "on",
            }:
                raise SystemEventInjectionError(
                    "wait args.expect_network must be 'off' or 'on'"
                )
            expected_resumed = event.args.get("expect_resumed")
            if expected_resumed is not None and expected_resumed not in {
                "target",
                "other",
            }:
                raise SystemEventInjectionError(
                    "wait args.expect_resumed must be 'target' or 'other'"
                )

            time.sleep(seconds)

            if expected_network is not None:
                expected_setting = "0" if expected_network == "off" else "1"
                wifi = self.device.get_wifi_setting()
                self._require_success(event.event, wifi)
                mobile_data = self.device.get_mobile_data_setting()
                self._require_success(event.event, mobile_data)
                observed_wifi = wifi.stdout.strip()
                observed_mobile = mobile_data.stdout.strip()
                if (
                    observed_wifi != expected_setting
                    or observed_mobile != expected_setting
                ):
                    raise SystemEventInjectionError(
                        "wait postcondition failed: expected network "
                        f"{expected_network}, observed wifi_on={observed_wifi!r} "
                        f"and mobile_data={observed_mobile!r}"
                    )

            if expected_resumed is not None:
                resumed_package = self._read_resumed_package(event.event)
                is_target = resumed_package == self.package
                if (
                    resumed_package is None
                    or is_target != (expected_resumed == "target")
                ):
                    raise SystemEventInjectionError(
                        "wait postcondition failed: expected resumed="
                        f"{expected_resumed}, observed {resumed_package!r}"
                    )
            return
        if event.event == "app_to_background":
            timeout_seconds, poll_interval_seconds = self._postcondition_polling(
                event
            )
            self._require_success(event.event, self.device.press_home())
            self._wait_for_resumed_package(
                event.event,
                expect_target=False,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            return
        if event.event == "process_death":
            # 真实进程死亡：后台化 → am kill → launcher 重新拉起。每一阶段均
            # 观测后置条件并写入回执，避免仅凭 adb 命令退出码推断生命周期。
            background_wait = self._event_delay(event, "background_wait", 2.0)
            kill_wait = self._event_delay(event, "kill_wait", 2.0)
            restore_wait = self._event_delay(event, "restore_wait", 8.0)
            timeout_seconds, poll_interval_seconds = self._postcondition_polling(
                event
            )
            before = self.device.get_pid(self.package)
            self._require_success(event.event, before)
            before_pids = self._parse_running_pids(event.event, before)

            self._require_success(event.event, self.device.press_home())
            if background_wait > 0:
                time.sleep(background_wait)
            background_resumed_package = self._wait_for_resumed_package(
                event.event,
                expect_target=False,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )

            self._require_success(
                event.event,
                self.device.kill_background(self.package),
            )
            if kill_wait > 0:
                time.sleep(kill_wait)
            self._require_process_absent(
                event.event,
                self.device.get_pid(self.package),
                phase="after kill",
            )

            self._require_success(
                event.event,
                self.device.launch_from_launcher(self.package, self.activity),
            )
            if restore_wait > 0:
                time.sleep(restore_wait)
            foreground_resumed_package = self._wait_for_resumed_package(
                event.event,
                expect_target=True,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            after = self.device.get_pid(self.package)
            self._require_success(event.event, after)
            after_pids = self._parse_running_pids(event.event, after)
            survivors = sorted(before_pids & after_pids)
            if survivors:
                survivor_list = ", ".join(survivors)
                noun = "process" if len(survivors) == 1 else "processes"
                raise SystemEventInjectionError(
                    "process_death postcondition failed: "
                    f"{noun} {survivor_list} survived"
                )
            return {
                "before_pids": sorted(before_pids),
                "background_status": "success",
                "background_resumed_package": background_resumed_package,
                "target_resumed_after_home": False,
                "kill_status": "success",
                "process_absent_after_kill": True,
                "relaunch_status": "success",
                "foreground_resumed_package": foreground_resumed_package,
                "target_resumed_after_relaunch": True,
                "after_pids": sorted(after_pids),
            }
        if event.event == "backup_restore":
            transport = event.args.get(
                "transport", "com.android.localtransport/.LocalTransport"
            )
            if not transport or any(character.isspace() for character in transport):
                raise SystemEventInjectionError(
                    "backup_restore requires a non-empty transport without whitespace"
                )
            raw_restore_wait = event.args.get("restore_wait", "8.0")
            try:
                restore_wait = float(raw_restore_wait)
            except (TypeError, ValueError) as error:
                raise SystemEventInjectionError(
                    "backup_restore requires a finite non-negative restore_wait"
                ) from error
            if not math.isfinite(restore_wait) or restore_wait < 0:
                raise SystemEventInjectionError(
                    "backup_restore requires a finite non-negative restore_wait"
                )

            enabled_result = self.device.get_backup_enabled()
            self._require_success(event.event, enabled_result)
            backup_was_enabled = self._parse_backup_enabled(enabled_result.stdout)

            transports_result = self.device.list_backup_transports()
            self._require_success(event.event, transports_result)
            previous_transport, available = self._parse_backup_transports(
                transports_result.stdout
            )
            if transport not in available:
                raise SystemEventInjectionError(
                    f"backup_restore transport is unavailable: {transport}"
                )

            attempt_evidence: dict[str, Any] | None = None
            attempt_error: Exception | None = None
            try:
                if not backup_was_enabled:
                    self._require_success(
                        event.event, self.device.set_backup_enabled(enabled=True)
                    )
                self._require_success(
                    event.event, self.device.select_backup_transport(transport)
                )
                selected = self.device.list_backup_transports()
                self._require_success(event.event, selected)
                selected_transport, _ = self._parse_backup_transports(selected.stdout)
                if selected_transport != transport:
                    raise SystemEventInjectionError(
                        "backup_restore postcondition failed: requested transport "
                        f"{transport}, observed {selected_transport}"
                    )
                attempt_evidence = self._perform_backup_restore(
                    event=event.event,
                    transport=transport,
                    restore_wait=restore_wait,
                )
            except Exception as error:
                attempt_error = error

            cleanup_evidence: dict[str, Any] | None = None
            cleanup_error: Exception | None = None
            try:
                cleanup_evidence = self._restore_backup_configuration(
                    event=event.event,
                    previous_transport=previous_transport,
                    selected_transport=transport,
                    backup_was_enabled=backup_was_enabled,
                )
            except Exception as error:
                cleanup_error = error

            if attempt_error is not None:
                if cleanup_error is not None:
                    raise SystemEventInjectionError(
                        f"{attempt_error}; backup_restore cleanup also failed: "
                        f"{cleanup_error}"
                    ) from attempt_error
                raise attempt_error
            if cleanup_error is not None:
                raise cleanup_error
            if attempt_evidence is None:
                raise SystemEventInjectionError(
                    "backup_restore completed without attempt evidence"
                )
            if cleanup_evidence is None:
                raise SystemEventInjectionError(
                    "backup_restore completed without cleanup evidence"
                )
            return {
                "transport": transport,
                "previous_transport": previous_transport,
                "backup_was_enabled": backup_was_enabled,
                **attempt_evidence,
                **cleanup_evidence,
            }
        if event.event == "app_to_foreground":
            timeout_seconds, poll_interval_seconds = self._postcondition_polling(
                event
            )
            self._require_success(
                event.event, self.device.launch(self.package, self.activity)
            )
            self._wait_for_resumed_package(
                event.event,
                expect_target=True,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            return
        if event.event == "dark_mode":
            # config-change: toggling uiMode night forces recreation on activities
            # whose configChanges does not declare uiMode (e.g. Wikipedia SearchActivity
            # declares only orientation|screenSize). args.night defaults to "yes".
            night = event.args.get("night", "yes")
            if night not in {"yes", "no"}:
                raise SystemEventInjectionError(
                    "dark_mode requires args.night to be 'yes' or 'no'; "
                    f"got {night!r}"
                )
            enabled = night == "yes"
            self._require_success(
                event.event, self.device.set_night_mode(enabled=enabled)
            )
            observed = self.device.get_night_mode()
            self._require_success(event.event, observed)
            expected = "yes" if enabled else "no"
            actual = observed.stdout.strip()
            if not actual.lower().endswith(expected):
                raise SystemEventInjectionError(
                    "dark_mode postcondition failed: "
                    f"expected night={expected}, observed {actual!r}"
                )
            return
        raise SystemEventInjectionError(f"Unsupported system event for MVP injector: {event.event}")

    def _perform_backup_restore(
        self,
        *,
        event: str,
        transport: str,
        restore_wait: float,
    ) -> dict[str, Any]:
        self._require_success(
            event, self.device.wipe_backup_data(transport, self.package)
        )
        backup = self.device.backup_now(self.package)
        self._require_success(event, backup)
        if re.search(
            rf"Package\s+{re.escape(self.package)}\s+with result:\s*Success",
            backup.stdout,
        ) is None:
            raise SystemEventInjectionError(
                "backup_restore backup postcondition failed: package success "
                f"marker missing from {backup.stdout.strip()!r}"
            )

        restore_sets = self.device.list_restore_sets()
        self._require_success(event, restore_sets)
        restore_token = self._parse_restore_token(restore_sets.stdout)

        cleared = self.device.clear_data(self.package)
        self._require_success(event, cleared)
        if cleared.stdout.strip() != "Success":
            raise SystemEventInjectionError(
                "backup_restore clear-data postcondition failed: "
                f"observed {cleared.stdout.strip()!r}"
            )

        restored = self.device.restore_backup(restore_token, self.package)
        self._require_success(event, restored)
        if re.search(r"restoreFinished:\s*0(?:\s|$)", restored.stdout) is None:
            raise SystemEventInjectionError(
                "backup_restore restore postcondition failed: success marker "
                f"missing from {restored.stdout.strip()!r}"
            )

        self._require_success(event, self.device.launch(self.package, self.activity))
        if restore_wait > 0:
            time.sleep(restore_wait)
        post_restore_pid = self.device.get_pid(self.package)
        self._require_success(event, post_restore_pid)
        post_restore_pids = self._parse_running_pids(event, post_restore_pid)
        return {
            "backup_status": "success",
            "clear_data_status": "success",
            "clear_data_output": cleared.stdout.strip(),
            "restore_status": "success",
            "restore_token": restore_token,
            "post_restore_pids": sorted(post_restore_pids),
            "backup_output": backup.stdout.strip(),
            "restore_output": restored.stdout.strip(),
        }

    def _restore_backup_configuration(
        self,
        *,
        event: str,
        previous_transport: str,
        selected_transport: str,
        backup_was_enabled: bool,
    ) -> dict[str, Any]:
        if previous_transport != selected_transport:
            self._require_success(
                event, self.device.select_backup_transport(previous_transport)
            )
        if not backup_was_enabled:
            self._require_success(
                event, self.device.set_backup_enabled(enabled=False)
            )
        restored_transports = self.device.list_backup_transports()
        self._require_success(event, restored_transports)
        active_after_cleanup, _ = self._parse_backup_transports(
            restored_transports.stdout
        )
        if active_after_cleanup != previous_transport:
            raise SystemEventInjectionError(
                "backup_restore cleanup failed: previous transport was not restored"
            )
        restored_enabled = self.device.get_backup_enabled()
        self._require_success(event, restored_enabled)
        backup_enabled_after_cleanup = self._parse_backup_enabled(
            restored_enabled.stdout
        )
        if backup_enabled_after_cleanup != backup_was_enabled:
            raise SystemEventInjectionError(
                "backup_restore cleanup failed: backup enabled state was not restored"
            )
        return {
            "cleanup_status": "success",
            "cleanup_transport": active_after_cleanup,
            "cleanup_backup_enabled": backup_enabled_after_cleanup,
        }

    @staticmethod
    def _require_success(
        event: str, results: AdbResult | Iterable[AdbResult]
    ) -> None:
        if isinstance(results, AdbResult):
            checked = [results]
        else:
            checked = list(results)
        for result in checked:
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "no output"
                raise SystemEventInjectionError(
                    f"{event} command returned return code {result.returncode}: {detail}"
                )

    @staticmethod
    def _parse_running_pids(event: str, result: AdbResult) -> set[str]:
        pids = set(result.stdout.split())
        if not pids or any(not pid.isdecimal() for pid in pids):
            raise SystemEventInjectionError(
                f"{event} postcondition failed: invalid pidof output "
                f"{result.stdout.strip()!r}"
            )
        return pids

    @classmethod
    def _require_process_absent(
        cls,
        event: str,
        result: AdbResult,
        *,
        phase: str,
    ) -> None:
        if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
            return
        if result.returncode == 0:
            remaining = sorted(cls._parse_running_pids(event, result))
            raise SystemEventInjectionError(
                f"{event} postcondition failed: process remains running {phase} "
                f"with pid(s) {', '.join(remaining)}"
            )
        cls._require_success(event, result)

    @staticmethod
    def _event_delay(event: SystemEventSpec, key: str, default: float) -> float:
        raw_value = event.args.get(key, str(default))
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise SystemEventInjectionError(
                f"{event.event} requires finite non-negative {key}"
            ) from error
        if not math.isfinite(value) or value < 0:
            raise SystemEventInjectionError(
                f"{event.event} requires finite non-negative {key}"
            )
        return value

    @staticmethod
    def _parse_backup_enabled(output: str) -> bool:
        normalized = output.strip().lower()
        if normalized.endswith("currently enabled") or normalized.endswith("now enabled"):
            return True
        if normalized.endswith("currently disabled") or normalized.endswith("now disabled"):
            return False
        raise SystemEventInjectionError(
            "backup_restore postcondition failed: unrecognized bmgr enabled output "
            f"{output.strip()!r}"
        )

    @staticmethod
    def _parse_backup_transports(output: str) -> tuple[str, set[str]]:
        available: set[str] = set()
        active: str | None = None
        for line in output.splitlines():
            match = re.fullmatch(r"\s*(\*)?\s*(\S+)\s*", line)
            if match is None:
                continue
            name = match.group(2)
            available.add(name)
            if match.group(1) == "*":
                if active is not None:
                    raise SystemEventInjectionError(
                        "backup_restore postcondition failed: multiple active transports"
                    )
                active = name
        if active is None or not available:
            raise SystemEventInjectionError(
                "backup_restore postcondition failed: active transport is unobservable"
            )
        return active, available

    @staticmethod
    def _parse_restore_token(output: str) -> str:
        for line in output.splitlines():
            match = re.match(r"^\s*([0-9A-Fa-f]+)\s*:\s*", line)
            if match is not None:
                return match.group(1)
        raise SystemEventInjectionError(
            "backup_restore postcondition failed: restore token is unobservable"
        )

    def _read_resumed_package(self, event: str) -> str | None:
        observed = self.device.get_resumed_activity()
        self._require_success(event, observed)
        for field in (
            "topResumedActivity",
            "mResumedActivity",
            "ResumedActivity",
        ):
            match = re.search(
                rf"^\s*{field}\s*[:=]\s*"
                r"ActivityRecord\{[^}\n]*\bu\d+\s+"
                r"(?P<package>[A-Za-z0-9_.]+)/[^\s}]+",
                observed.stdout,
                flags=re.MULTILINE,
            )
            if match is not None:
                return match.group("package")
        return None

    @staticmethod
    def _postcondition_polling(event: SystemEventSpec) -> tuple[float, float]:
        raw_timeout = event.args.get("postcondition_timeout_seconds", "5.0")
        raw_interval = event.args.get(
            "postcondition_poll_interval_seconds", "0.1"
        )
        try:
            timeout_seconds = float(raw_timeout)
            poll_interval_seconds = float(raw_interval)
        except (TypeError, ValueError) as error:
            raise SystemEventInjectionError(
                f"{event.event} requires finite non-negative "
                "postcondition_timeout_seconds and positive "
                "postcondition_poll_interval_seconds"
            ) from error
        if (
            not math.isfinite(timeout_seconds)
            or timeout_seconds < 0
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds <= 0
        ):
            raise SystemEventInjectionError(
                f"{event.event} requires finite non-negative "
                "postcondition_timeout_seconds and positive "
                "postcondition_poll_interval_seconds"
            )
        return timeout_seconds, poll_interval_seconds

    def _wait_for_resumed_package(
        self,
        event: str,
        *,
        expect_target: bool,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> str:
        deadline = time.monotonic() + timeout_seconds
        while True:
            resumed_package = self._read_resumed_package(event)
            target_is_resumed = resumed_package == self.package
            if resumed_package is not None and target_is_resumed is expect_target:
                return resumed_package
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if resumed_package is None:
                    raise SystemEventInjectionError(
                        f"{event} postcondition timed out: "
                        "resumed activity remained unobservable"
                    )
                expected = (
                    f"resumed package {self.package}"
                    if expect_target
                    else f"a resumed package other than {self.package}"
                )
                raise SystemEventInjectionError(
                    f"{event} postcondition timed out: expected {expected}, "
                    f"observed {resumed_package}"
                )
            time.sleep(min(poll_interval_seconds, remaining))

    def _wait_for_exact_resumed_package(
        self,
        event: str,
        *,
        expected_package: str,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            resumed_package = self._read_resumed_package(event)
            if resumed_package == expected_package:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                observed = resumed_package or "unobservable"
                raise SystemEventInjectionError(
                    f"{event} postcondition failed: expected resumed package "
                    f"{expected_package}, observed {observed}"
                )
            time.sleep(min(poll_interval_seconds, remaining))
