"""Climate platform for the NGBS iCON integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_COMFORT,
    PRESET_ECO,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IconConfigEntry, IconDataUpdateCoordinator
from .entity import IconThermostatEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for every connected thermostat."""
    coordinator = entry.runtime_data
    entities = [
        IconClimate(coordinator, icon_key, thermostat_id)
        for icon_key, icon in coordinator.data["icons"].items()
        for thermostat_id in icon["thermostats"]
    ]
    async_add_entities(entities)


class IconClimate(IconThermostatEntity, ClimateEntity):
    """A thermostat exposed as a climate entity."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5
    _attr_max_temp = 35
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_ECO, PRESET_COMFORT]

    def __init__(
        self,
        coordinator: IconDataUpdateCoordinator,
        icon_key: str,
        thermostat_id: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, icon_key, thermostat_id)
        self._attr_unique_id = f"{coordinator.sysid}_{thermostat_id}"
        # Only the H/C master thermostat may switch the system mode.
        self._is_master = (
            coordinator.inventory.get("hcmaster") == thermostat_id
        )

    @property
    def _is_cooling(self) -> bool:
        return bool(self._thermostat and self._thermostat["cooling"])

    @property
    def current_temperature(self) -> float | None:
        """Return the measured temperature."""
        return self._thermostat["temp"] if self._thermostat else None

    @property
    def current_humidity(self) -> float | None:
        """Return the measured humidity."""
        return self._thermostat["rh"] if self._thermostat else None

    @property
    def target_temperature(self) -> float | None:
        """Return the active setpoint."""
        return self._thermostat["target"] if self._thermostat else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return HVACMode.COOL if self._is_cooling else HVACMode.HEAT

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return selectable modes (only the master can switch)."""
        if self._is_master:
            return [HVACMode.HEAT, HVACMode.COOL]
        return [self.hvac_mode]

    @property
    def hvac_action(self) -> HVACAction:
        """Return whether the zone is actively heating/cooling."""
        if not self._thermostat or not self._thermostat["demand"]:
            return HVACAction.IDLE
        return HVACAction.COOLING if self._is_cooling else HVACAction.HEATING

    @property
    def preset_mode(self) -> str:
        """Return the current preset."""
        return PRESET_ECO if self._thermostat and self._thermostat["eco"] else PRESET_COMFORT

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        eco = bool(self._thermostat and self._thermostat["eco"])
        await self.coordinator.client.async_set_temperature(
            self._thermostat_id, temperature, self._is_cooling, eco
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch the system between heating and cooling (master only)."""
        if hvac_mode == self.hvac_mode:
            return
        await self.coordinator.client.async_set_hvac_mode(hvac_mode == HVACMode.COOL)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the ECO/comfort preset."""
        if preset_mode == self.preset_mode:
            return
        await self.coordinator.client.async_set_preset_mode(
            self._thermostat_id, preset_mode == PRESET_ECO
        )
        await self.coordinator.async_request_refresh()
