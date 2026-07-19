"""System event injection adapter for runner flows."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from aiverify.harness.device import AdbResult, DeviceController
from aiverify.runner.run_spec import SystemEventSpec


class SystemEventInjectionError(ValueError):
    """Raised when a system event cannot be injected from the provided context."""


@dataclass(frozen=True)
class SystemEventObservation:
    """Auditable requested and observed state for one system event."""

    event: str
    requested: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "requested": self.requested,
            "observed": self.observed,
        }


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

    def inject(self, event: SystemEventSpec) -> SystemEventObservation | None:
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
            return
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
        if event.event == "reset_permission":
            permission = self._required_permission(event)
            self._require_success(
                event.event, self.device.revoke_permission(self.package, permission)
            )
            self._require_success(
                event.event,
                self.device.clear_permission_flags(
                    self.package,
                    permission,
                    "user-set",
                    "user-fixed",
                ),
            )
            return self._permission_observation(
                event=event,
                permission=permission,
                expected_granted=False,
                forbidden_flags={"USER_SET", "USER_FIXED"},
            )
        if event.event == "grant_permission":
            permission = self._required_permission(event)
            self._require_success(
                event.event, self.device.grant_permission(self.package, permission)
            )
            return self._permission_observation(
                event=event,
                permission=permission,
                expected_granted=True,
            )
        if event.event == "observe_permission":
            permission = self._required_permission(event)
            raw_granted = event.args.get("expected_granted")
            if raw_granted not in {"true", "false"}:
                raise SystemEventInjectionError(
                    "observe_permission requires args.expected_granted to be "
                    "'true' or 'false'"
                )
            return self._permission_observation(
                event=event,
                permission=permission,
                expected_granted=raw_granted == "true",
                required_flags=self._permission_flags(
                    event.args.get("required_flags", "")
                ),
                forbidden_flags=self._permission_flags(
                    event.args.get("forbidden_flags", "")
                ),
            )
        if event.event == "revoke_permission":
            permission = self._required_permission(event)
            self._require_success(
                event.event, self.device.revoke_permission(self.package, permission)
            )
            return self._permission_observation(
                event=event,
                permission=permission,
                expected_granted=False,
            )
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
            # 真实进程死亡：后台化 → am kill → launcher 重新拉起。
            # 等待编排在 DeviceController.process_death 内部完成，返回时恢复已就绪，
            # 调用方可立即抓取 after-event checkpoint。args 可覆盖各阶段等待秒数。
            before = self.device.get_pid(self.package)
            self._require_success(event.event, before)
            before_pids = self._parse_running_pids(event.event, before)
            self._require_success(
                event.event,
                self.device.process_death(
                    self.package,
                    self.activity,
                    background_wait=float(event.args.get("background_wait", "2.0")),
                    kill_wait=float(event.args.get("kill_wait", "2.0")),
                    restore_wait=float(event.args.get("restore_wait", "8.0")),
                ),
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
            return
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

    @staticmethod
    def _required_permission(event: SystemEventSpec) -> str:
        permission = event.args.get("permission")
        if not permission:
            raise SystemEventInjectionError(
                f"{event.event} requires args.permission"
            )
        return permission

    @staticmethod
    def _permission_flags(raw: str) -> set[str]:
        return {value.strip() for value in raw.split(",") if value.strip()}

    def _permission_observation(
        self,
        *,
        event: SystemEventSpec,
        permission: str,
        expected_granted: bool,
        expected_flags: set[str] | None = None,
        required_flags: set[str] | None = None,
        forbidden_flags: set[str] | None = None,
    ) -> SystemEventObservation:
        observed = self.device.dump_package_state(self.package)
        self._require_success(event.event, observed)
        grant = re.search(
            rf"^\s*{re.escape(permission)}:\s+granted=(true|false)"
            rf"(?:,\s*flags=\[([^\]]*)\])?(?:,|\s*$)",
            observed.stdout,
            flags=re.MULTILINE,
        )
        if grant is None:
            raise SystemEventInjectionError(
                f"{event.event} postcondition failed: could not find runtime "
                f"permission {permission} in package state"
            )
        granted = grant.group(1) == "true"
        flags = sorted(
            flag.strip()
            for flag in (grant.group(2) or "").split("|")
            if flag.strip()
        )
        if granted != expected_granted:
            state = "granted" if granted else "denied"
            raise SystemEventInjectionError(
                f"{event.event} postcondition failed: {permission} remains {state}"
            )
        if expected_flags is not None and set(flags) != expected_flags:
            raise SystemEventInjectionError(
                f"{event.event} postcondition failed: expected flags "
                f"{sorted(expected_flags)!r}, observed {flags!r}"
            )
        missing_flags = (required_flags or set()) - set(flags)
        present_forbidden_flags = (forbidden_flags or set()) & set(flags)
        if missing_flags or present_forbidden_flags:
            raise SystemEventInjectionError(
                f"{event.event} postcondition failed: missing required flags "
                f"{sorted(missing_flags)!r}, present forbidden flags "
                f"{sorted(present_forbidden_flags)!r}, observed {flags!r}"
            )
        return SystemEventObservation(
            event=event.event,
            requested={"package": self.package, "permission": permission},
            observed={"granted": granted, "flags": flags},
        )

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
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            resumed_package = self._read_resumed_package(event)
            target_is_resumed = resumed_package == self.package
            if resumed_package is not None and target_is_resumed is expect_target:
                return
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
