"""Config flow for the NGBS iCON integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ID, CONF_IP_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import (
    CONF_INVENTORY,
    CONF_SYSID,
    DEFAULT_MODBUS_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IconConfigEntry
from .modbus_client import (
    IconModbusClient,
    IconModbusConnectionError,
    IconModbusError,
)
from .names import (
    IconJsonClient,
    IconJsonConnectionError,
    IconJsonError,
    async_discover_sysid,
)

_LOGGER = logging.getLogger(__name__)


class ValidationFailed(Exception):
    """A setup check failed, carrying the error key and a human-readable reason."""

    def __init__(self, error: str, reason: str) -> None:
        """Store the strings.json error key and the detailed reason."""
        super().__init__(reason)
        self.error = error
        self.reason = reason


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_SYSID, default=""): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)


async def _fetch_inventory(host: str, sysid: str) -> dict[str, Any]:
    """Fetch the naming inventory for a known SYSID.

    Raised failures here are stage-specific (invalid SYSID vs. JSON
    unreachable) and are handled by the caller, which decides whether to
    hard-fail or continue with an empty inventory.
    """
    return await IconJsonClient(host, sysid).async_fetch_inventory()


async def _validate(
    host: str, manual_sysid: str = ""
) -> tuple[str | None, dict[str, Any]]:
    """Validate connectivity and return the best available SYSID and inventory.

    Modbus reachability is mandatory - the integration cannot function
    without it - and is confirmed first. The discovered device indices are
    cached into the inventory so the coordinator doesn't need to re-probe
    every device slot on every poll; only setup/reconfigure does that full
    scan. Re-running Reconfigure after adding or removing a controller
    refreshes this cache.

    The SYSID and the naming inventory come from the legacy JSON protocol,
    which is not required for the integration to work: some firmwares reject
    the unauthenticated ``{"RELOAD": 6}`` discovery query used to auto-detect
    it (observed on PrgVer 1050, returning ``{"ERR": 1}`` to every request
    regardless of shape), and JSON may be unreachable entirely (firewalled,
    wrong port, another client holding the connection). Rather than blocking
    setup on a protocol the device doesn't need for actual operation, JSON
    failures degrade gracefully:

    - If the user supplied a System ID manually, it is used directly for the
      inventory fetch (auto-discovery is skipped).
    - Otherwise auto-discovery is attempted; if it fails, setup continues
      with ``sysid=None`` and an empty inventory rather than hard-failing.
      Thermostats and climate/sensor entities still work either way, since
      they only depend on Modbus. Relay binary sensors are the one visible
      loss: their inventory-derived name is what marks a relay "configured"
      (Modbus has no equivalent signal), so without the inventory no relay
      entities are created. Names otherwise fall back to generic labels like
      "Thermostat 1.1".

    A missing/failed SYSID means the config entry's unique ID falls back to
    the host address (see the callers), which is weaker than the
    controller's real identity but still prevents duplicate entries for the
    same device.
    """
    modbus = IconModbusClient(host)
    try:
        await modbus.async_connect()
        present = await modbus.async_discover()
    except IconModbusConnectionError as err:
        raise ValidationFailed("cannot_connect_modbus", str(err)) from err
    except IconModbusError as err:
        raise ValidationFailed("modbus_error", str(err)) from err
    finally:
        await modbus.async_close()

    if not present:
        raise ValidationFailed(
            "no_devices",
            f"Connected to {host}:{DEFAULT_MODBUS_PORT} over Modbus-TCP, but "
            "none of the device slots returned a firmware version, so no "
            "iCON unit could be identified. Check that the units are "
            "powered and addressed on the bus.",
        )

    sysid: str | None = manual_sysid.strip() or None
    inventory: dict[str, Any] = {}

    if sysid:
        # A manually supplied SYSID is assumed correct; a bad one should
        # still surface as a real error rather than being silently dropped.
        try:
            inventory = await _fetch_inventory(host, sysid)
        except IconJsonConnectionError as err:
            raise ValidationFailed("cannot_connect_json", str(err)) from err
        except IconJsonError as err:
            raise ValidationFailed("invalid_inventory", str(err)) from err
    else:
        try:
            sysid = await async_discover_sysid(host)
        except (IconJsonConnectionError, IconJsonError) as err:
            _LOGGER.warning(
                "NGBS iCON SYSID auto-discovery failed, continuing without "
                "names/SYSID (Modbus-only): %s",
                err,
            )
            sysid = None
        else:
            try:
                inventory = await _fetch_inventory(host, sysid)
            except (IconJsonConnectionError, IconJsonError) as err:
                _LOGGER.warning(
                    "NGBS iCON inventory fetch failed, continuing without "
                    "names (Modbus-only): %s",
                    err,
                )

    inventory["device_indices"] = present
    return sysid, inventory


def _entry_unique_id(host: str, sysid: str | None) -> str:
    """Return the value to use as the config entry's unique ID.

    Prefers the controller's real SYSID; falls back to the host address if
    it could not be determined (see :func:`_validate`).
    """
    return sysid or f"host:{host}"


class NgbsIconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the NGBS iCON config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            try:
                sysid, inventory = await _validate(
                    host, user_input.get(CONF_SYSID, "")
                )
            except ValidationFailed as err:
                _LOGGER.error("NGBS iCON setup failed: %s", err.reason)
                errors["base"] = err.error
                placeholders["reason"] = err.reason
            except Exception as err:  # noqa: BLE001 - surface the real cause
                _LOGGER.exception("Unexpected error during NGBS iCON setup")
                errors["base"] = "unknown"
                placeholders["reason"] = f"{type(err).__name__}: {err}"
            else:
                entry_id = _entry_unique_id(host, sysid)
                await self.async_set_unique_id(entry_id)
                self._abort_if_unique_id_configured()
                data = {
                    **user_input,
                    CONF_ID: sysid or entry_id,
                    CONF_INVENTORY: inventory,
                }
                data.pop(CONF_SYSID, None)
                return self.async_create_entry(title="NGBS iCON", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            try:
                sysid, inventory = await _validate(
                    host, user_input.get(CONF_SYSID, "")
                )
            except ValidationFailed as err:
                _LOGGER.error("NGBS iCON reconfigure failed: %s", err.reason)
                errors["base"] = err.error
                placeholders["reason"] = err.reason
            except Exception as err:  # noqa: BLE001 - surface the real cause
                _LOGGER.exception("Unexpected error during NGBS iCON reconfigure")
                errors["base"] = "unknown"
                placeholders["reason"] = f"{type(err).__name__}: {err}"
            else:
                # If this reconfigure couldn't (re-)discover a SYSID - e.g.
                # JSON is temporarily down - fall back to the entry's
                # existing identity instead of a fresh host-based one, so a
                # transient JSON failure doesn't look like a different device
                # and abort as a mismatch.
                existing_id = self._get_reconfigure_entry().unique_id
                entry_id = sysid or existing_id or _entry_unique_id(host, sysid)
                await self.async_set_unique_id(entry_id)
                self._abort_if_unique_id_mismatch()
                data_updates = {
                    **user_input,
                    CONF_ID: sysid or entry_id,
                    CONF_INVENTORY: inventory,
                }
                data_updates.pop(CONF_SYSID, None)
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=data_updates,
                )

        current_data = dict(self._get_reconfigure_entry().data)
        stored_id = current_data.get(CONF_ID, "")
        # A synthetic host-based fallback ID (no real SYSID was ever found)
        # isn't a SYSID the user could usefully re-enter - leave the field
        # blank rather than prefilling it with something misleading.
        if not stored_id.startswith("host:"):
            current_data.setdefault(CONF_SYSID, stored_id)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, current_data
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IconConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NgbsIconOptionsFlow(config_entry)


class NgbsIconOptionsFlow(OptionsFlow):
    """Handle NGBS iCON options (poll interval)."""

    def __init__(self, config_entry: IconConfigEntry) -> None:
        """Store the config entry being configured."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
