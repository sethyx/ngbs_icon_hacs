"""Sensor platform for the NGBS iCON integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IconConfigEntry, IconDataUpdateCoordinator
from .entity import IconIconEntity, IconThermostatEntity

THERMOSTAT_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="temp",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rh",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dew",
        name="Dewpoint temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

SYSTEM_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="water_temp",
        name="Water temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outdoor_temp",
        name="Outdoor temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for connected thermostats and controllers."""
    coordinator = entry.runtime_data
    data = coordinator.data
    master_icon = str(min(int(k) for k in data["icons"]))

    entities: list[SensorEntity] = []
    for icon_key, icon in data["icons"].items():
        if icon["mixing_valve_pct"] is not None:
            entities.append(IconMixingValveSensor(coordinator, icon_key))
        for thermostat_id in icon["thermostats"]:
            entities.extend(
                IconThermostatSensor(coordinator, icon_key, thermostat_id, desc)
                for desc in THERMOSTAT_SENSORS
            )

    entities.extend(
        IconSystemSensor(coordinator, master_icon, desc)
        for desc in SYSTEM_SENSORS
        if data["system"].get(desc.key) is not None
    )

    async_add_entities(entities)


class IconThermostatSensor(IconThermostatEntity, SensorEntity):
    """A per-thermostat measurement sensor."""

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        thermostat_id: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor from its description."""
        super().__init__(coordinator, icon_key, thermostat_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.sysid}_{thermostat_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the measured value."""
        if self._thermostat is None:
            return None
        return self._thermostat[self.entity_description.key]


class IconMixingValveSensor(IconIconEntity, SensorEntity):
    """Mixing-valve position sensor on a controller device."""

    _attr_name = "Mixing valve"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: IconDataUpdateCoordinator, icon_key: str
    ) -> None:
        """Initialize the mixing-valve sensor."""
        super().__init__(coordinator, icon_key)
        self._attr_unique_id = f"{coordinator.sysid}_icon{icon_key}_mixing_valve"

    @property
    def native_value(self) -> float | None:
        """Return the mixing-valve position."""
        return self._icon["mixing_valve_pct"] if self._icon else None


class IconSystemSensor(IconIconEntity, SensorEntity):
    """A system-wide sensor attached to the master controller device."""

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the system sensor."""
        super().__init__(coordinator, icon_key)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.sysid}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the system value."""
        return self.coordinator.data["system"].get(self.entity_description.key)
