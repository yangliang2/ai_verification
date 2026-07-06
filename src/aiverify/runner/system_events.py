"""System event injection adapter for runner flows."""

from __future__ import annotations

from dataclasses import dataclass

from aiverify.harness.device import DeviceController
from aiverify.runner.run_spec import SystemEventSpec


class SystemEventInjectionError(ValueError):
    """Raised when a system event cannot be injected from the provided context."""


@dataclass
class DeviceSystemEventInjector:
    """Inject Run Spec system events through DeviceController.

    activity: launcher activity（或 alias）完整类名，process_death 恢复拉起用；
    debug 构建常有多个 LAUNCHER activity，缺省的 monkey 拉起不确定。
    """

    device: DeviceController
    package: str
    activity: str | None = None

    def inject(self, event: SystemEventSpec) -> None:
        """Inject one system event at a Journey Segment Boundary."""
        if event.event == "rotate":
            rotation = int(event.args.get("rotation", "1"))
            self.device.rotate(rotation)
            return
        if event.event == "kill_background":
            self.device.kill_background(self.package)
            return
        if event.event == "revoke_permission":
            permission = event.args.get("permission")
            if not permission:
                raise SystemEventInjectionError("revoke_permission requires args.permission")
            self.device.revoke_permission(self.package, permission)
            return
        if event.event == "network_off":
            self.device.set_wifi(enabled=False)
            self.device.set_mobile_data(enabled=False)
            return
        if event.event == "network_on":
            self.device.set_wifi(enabled=True)
            self.device.set_mobile_data(enabled=True)
            return
        if event.event == "app_to_background":
            self.device.press_home()
            return
        if event.event == "process_death":
            # 真实进程死亡：后台化 → am kill → launcher 重新拉起。
            # 等待编排在 DeviceController.process_death 内部完成，返回时恢复已就绪，
            # 调用方可立即抓取 after-event checkpoint。args 可覆盖各阶段等待秒数。
            self.device.process_death(
                self.package,
                self.activity,
                background_wait=float(event.args.get("background_wait", "2.0")),
                kill_wait=float(event.args.get("kill_wait", "2.0")),
                restore_wait=float(event.args.get("restore_wait", "8.0")),
            )
            return
        if event.event == "app_to_foreground":
            self.device.launch(self.package)
            return
        if event.event == "dark_mode":
            # config-change: toggling uiMode night forces recreation on activities
            # whose configChanges does not declare uiMode (e.g. Wikipedia SearchActivity
            # declares only orientation|screenSize). args.night defaults to "yes".
            enabled = event.args.get("night", "yes") == "yes"
            self.device.set_night_mode(enabled=enabled)
            return
        raise SystemEventInjectionError(f"Unsupported system event for MVP injector: {event.event}")
