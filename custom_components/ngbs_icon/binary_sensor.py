"""Binary sensor platform for the NGBS iCON integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IconConfigEntry, IconDataUpdateCoordinator
from .entity import IconIconEntity, IconThermostatEntity

THERMOSTAT_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="demand_a",
        name="A-loop demand",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    BinarySensorEntityDescription(
        key="demand_b",
        name="B-loop demand",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    BinarySensorEntityDescription(
        key="cond",
        name="Condensation",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="eco",
        name="ECO",
    ),
    BinarySensorEntityDescription(
        key="live",
        name="Connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for thermostats, relays and the pump."""
    coordinator = entry.runtime_data
    data = coordinator.data
    master_icon = data["system"]["master_icon"]

    entities: list[BinarySensorEntity] = []
    for icon_key, icon in data["icons"].items():
        for thermostat_id in icon["thermostats"]:
            entities.append(
                IconHvacRequestBinarySensor(coordinator, icon_key, thermostat_id)
            )
            entities.extend(
                IconThermostatBinarySensor(coordinator, icon_key, thermostat_id, desc)
                for desc in THERMOSTAT_BINARY_SENSORS
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


class IconThermostatBinarySensor(IconThermostatEntity, BinarySensorEntity):
    """A per-thermostat status binary sensor."""

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        thermostat_id: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor from its description."""
        super().__init__(coordinator, icon_key, thermostat_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.sysid}_{thermostat_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the status bit."""
        if self._thermostat is None:
            return None
        return self._thermostat[self.entity_description.key]


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
