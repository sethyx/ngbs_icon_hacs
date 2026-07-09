"""Binary sensor platform for the NGBS iCON integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IconConfigEntry, IconDataUpdateCoordinator
from .entity import IconIconEntity, IconThermostatEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for thermostats, relays and the pump."""
    coordinator = entry.runtime_data
    data = coordinator.data
    master_icon = str(min(int(k) for k in data["icons"]))

    entities: list[BinarySensorEntity] = []
    for icon_key, icon in data["icons"].items():
        for thermostat_id in icon["thermostats"]:
            entities.append(
                IconHvacRequestBinarySensor(coordinator, icon_key, thermostat_id)
            )
        for relay_id, relay in icon["relays"].items():
            # Only relays configured on the controller carry a name.
            if relay["name"]:
                entities.append(
                    IconRelayBinarySensor(coordinator, icon_key, relay_id)
                )

    if data["system"].get("pump") is not None:
        entities.append(IconPumpBinarySensor(coordinator, master_icon))

    async_add_entities(entities)


class IconHvacRequestBinarySensor(IconThermostatEntity, BinarySensorEntity):
    """Whether a thermostat is currently calling for heating/cooling."""

    _attr_name = "HVAC request"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        thermostat_id: str,
    ) -> None:
        """Initialize the HVAC-request sensor."""
        super().__init__(coordinator, icon_key, thermostat_id)
        self._attr_unique_id = f"{coordinator.sysid}_{thermostat_id}_hvac_request"

    @property
    def is_on(self) -> bool | None:
        """Return True when the zone is demanding energy."""
        return self._thermostat["demand"] if self._thermostat else None


class IconRelayBinarySensor(IconIconEntity, BinarySensorEntity):
    """A configured relay/valve output on a controller."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        relay_id: str,
    ) -> None:
        """Initialize the relay sensor."""
        super().__init__(coordinator, icon_key)
        self._relay_id = relay_id
        self._attr_unique_id = f"{coordinator.sysid}_icon{icon_key}_{relay_id}"
        self._attr_name = (
            coordinator.inventory.get("relays", {})
            .get(icon_key, {})
            .get(relay_id, relay_id)
        )

    @property
    def is_on(self) -> bool | None:
        """Return the relay state."""
        if self._icon is None:
            return None
        return self._icon["relays"][self._relay_id]["on"]


class IconPumpBinarySensor(IconIconEntity, BinarySensorEntity):
    """The system water pump."""

    _attr_name = "Water pump"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self, coordinator: IconDataUpdateCoordinator, icon_key: str
    ) -> None:
        """Initialize the pump sensor."""
        super().__init__(coordinator, icon_key)
        self._attr_unique_id = f"{coordinator.sysid}_pump"

    @property
    def is_on(self) -> bool | None:
        """Return True when the pump is running."""
        return self.coordinator.data["system"].get("pump")
