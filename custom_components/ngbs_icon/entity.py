"""Base entities and device helpers for the NGBS iCON integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import IconDataUpdateCoordinator


def icon_device_info(
    sysid: str, icon_key: str, firmware: int | None = None
) -> DeviceInfo:
    """Return DeviceInfo for an iCON controller device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{sysid}_icon{icon_key}")},
        manufacturer=MANUFACTURER,
        model="iCON controller",
        name=f"iCON {icon_key}",
        sw_version=str(firmware) if firmware else None,
    )


def thermostat_device_info(
    sysid: str, icon_key: str, thermostat_id: str, name: str | None
) -> DeviceInfo:
    """Return DeviceInfo for a thermostat, nested under its iCON controller."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{sysid}_{thermostat_id}")},
        manufacturer=MANUFACTURER,
        model="iCON thermostat",
        name=name or f"Thermostat {thermostat_id}",
        via_device=(DOMAIN, f"{sysid}_icon{icon_key}"),
    )


class IconIconEntity(CoordinatorEntity[IconDataUpdateCoordinator]):
    """Base entity attached to an iCON controller device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IconDataUpdateCoordinator, icon_key: str) -> None:
        """Initialize with the icon key locator."""
        super().__init__(coordinator)
        self._icon_key = icon_key
        firmware = self._icon.get("firmware") if self._icon else None
        self._attr_device_info = icon_device_info(
            coordinator.sysid, icon_key, firmware
        )

    @property
    def _icon(self) -> dict[str, Any] | None:
        """Return this controller's data, or None if it dropped off the bus."""
        return self.coordinator.data.get("icons", {}).get(self._icon_key)

    @property
    def available(self) -> bool:
        """Return True if the coordinator succeeded and the icon is present."""
        return super().available and self._icon is not None


class IconThermostatEntity(CoordinatorEntity[IconDataUpdateCoordinator]):
    """Base entity attached to a thermostat device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: IconDataUpdateCoordinator, icon_key: str, thermostat_id: str
    ) -> None:
        """Initialize with the icon key and thermostat id locators."""
        super().__init__(coordinator)
        self._icon_key = icon_key
        self._thermostat_id = thermostat_id
        name = coordinator.inventory.get("thermostats", {}).get(thermostat_id)
        self._attr_device_info = thermostat_device_info(
            coordinator.sysid, icon_key, thermostat_id, name
        )

    @property
    def _thermostat(self) -> dict[str, Any] | None:
        """Return this thermostat's data, or None if it is offline."""
        icon = self.coordinator.data.get("icons", {}).get(self._icon_key)
        if icon is None:
            return None
        return icon["thermostats"].get(self._thermostat_id)

    @property
    def available(self) -> bool:
        """Return True if the coordinator succeeded and the thermostat is present."""
        return super().available and self._thermostat is not None
