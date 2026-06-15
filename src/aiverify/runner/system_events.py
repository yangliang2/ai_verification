"""System event injection adapter for runner flows."""

from __future__ import annotations

from dataclasses import dataclass

from aiverify.harness.device import DeviceController
from aiverify.runner.run_spec import SystemEventSpec


class SystemEventInjectionError(ValueError):
    """Raised when a system event cannot be injected from the provided context."""


@dataclass
class DeviceSystemEventInjector:
    """Inject Run Spec system events through DeviceController."""

    device: DeviceController
    package: str

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
        if event.event == "app_to_foreground":
            self.device.launch(self.package)
            return
        raise SystemEventInjectionError(f"Unsupported system event for MVP injector: {event.event}")
