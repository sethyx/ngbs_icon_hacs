"""Legacy JSON-over-TCP access, kept only for setup-time metadata.

Modbus does not expose the human-readable thermostat and relay/valve names, so
the original JSON protocol is retained purely to fetch that inventory once
during config flow. This module is Home Assistant independent so it can also be
used by the CLI tools.

It additionally provides :func:`raw_to_canonical`, which converts a raw JSON
``RELOAD`` response into the shared canonical schema used to compare the legacy
and Modbus datasets.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_JSON_PORT = 7992


class IconJsonError(Exception):
    """Base exception for the legacy JSON client."""


class IconJsonConnectionError(IconJsonError):
    """Raised when the controller cannot be reached over JSON/TCP."""


async def _async_send(
    host: str, port: int, timeout: float, payload: dict[str, Any]
) -> dict[str, Any]:
    """Send a single JSON command over a fresh TCP connection and return the response."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (TimeoutError, OSError) as err:
        raise IconJsonConnectionError(f"Connection failed: {err}") from err

    try:
        writer.write(json.dumps(payload).encode("utf-8"))
        await writer.drain()
        response = await asyncio.wait_for(reader.read(-1), timeout=timeout)
    except (TimeoutError, OSError) as err:
        raise IconJsonConnectionError(f"Communication failed: {err}") from err
    finally:
        if not writer.is_closing():
            writer.close()
            await writer.wait_closed()

    if not response:
        raise IconJsonConnectionError("Empty response from controller")
    try:
        return json.loads(response.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise IconJsonError(f"Invalid JSON response: {err}") from err


async def async_discover_sysid(
    host: str, port: int = DEFAULT_JSON_PORT, timeout: float = 2.0
) -> str:
    """Discover a controller's SYSID via the ``{"RELOAD": 6}`` broadcast query.

    Unlike a normal ``RELOAD`` request, this variant does not require a SYSID
    to be sent and is used during config flow to auto-detect it, e.g.::

        {"SYSID": "500118017047", "DOWNLOAD": 0,
         "ICON1": {"VER:": "621163406", "FIRMWARE": 1079}, ...}
    """
    data = await _async_send(host, port, timeout, {"RELOAD": 6})
    sysid = data.get("SYSID")
    if not sysid:
        raise IconJsonError("Controller did not return a SYSID")
    return sysid


class IconJsonClient:
    """Minimal JSON-over-TCP client (one request per connection)."""

    def __init__(
        self, host: str, system_id: str, port: int = DEFAULT_JSON_PORT, timeout: float = 2.0
    ) -> None:
        """Initialise the client with host, system id (SYSID) and port."""
        self._host = host
        self._port = port
        self._system_id = system_id
        self._timeout = timeout

    async def _async_request(self, command: dict[str, Any]) -> dict[str, Any]:
        """Send a single JSON command and return the decoded response."""
        payload = command | {"SYSID": self._system_id}
        data = await _async_send(self._host, self._port, self._timeout, payload)
        if data.get("ERR") == 1:
            raise IconJsonError("Controller returned an error (bad SYSID?)")
        return data

    async def async_get_raw(self) -> dict[str, Any]:
        """Fetch the full raw state with a single ``RELOAD`` command."""
        return await self._async_request({"RELOAD": ""})

    async def async_fetch_inventory(self) -> dict[str, Any]:
        """Fetch the naming inventory used to label Modbus entities.

        Returns ``{"icons": [int], "thermostats": {id: name},
        "relays": {icon: {R<n>: name}}, "hcmaster": id}``.
        """
        return extract_inventory(await self.async_get_raw())


def _icon_num(thermostat_id: str) -> str:
    """Return the icon-number prefix of an ``"<icon>.<th>"`` id."""
    return thermostat_id.split(".")[0]


def extract_inventory(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract the naming inventory from a raw ``RELOAD`` response."""
    cfg = raw.get("CFG", {})
    dp = raw.get("DP", {})

    thermostats = {
        th_id: therm.get("NAME", f"Thermostat {th_id}")
        for th_id, therm in dp.items()
        if therm.get("NAME")
    }

    icons: set[int] = {int(_icon_num(th_id)) for th_id in thermostats}
    relays: dict[str, dict[str, str]] = {}
    for icon_key, icon_data in cfg.items():
        if not icon_key.startswith("ICON") or not icon_key[4:].isdigit():
            continue
        icon_num = icon_key[4:]  # "ICON1" -> "1"
        icons.add(int(icon_num))
        icon_relays: dict[str, str] = {}
        for relay_id, config in (icon_data.get("RELAY") or {}).items():
            func = (config.get("FUNC") or "").strip()
            # Skip unconfigured relays (blank or still the default "R<icon>." name).
            if not func or func.startswith(f"R{icon_num}."):
                continue
            icon_relays[relay_id] = func
        if icon_relays:
            relays[icon_num] = icon_relays

    hcmaster = (cfg.get("HCMASTER") or "")[1:]  # "H1.1" -> "1.1"

    return {
        "icons": sorted(icons),
        "thermostats": thermostats,
        "relays": relays,
        "hcmaster": hcmaster,
    }


def raw_to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw JSON ``RELOAD`` response into the canonical schema.

    Mirrors the field selection of :meth:`modbus_client.IconModbusClient.async_get_data`
    so the two datasets can be compared directly.
    """
    cfg = raw.get("CFG", {})
    dp = raw.get("DP", {})
    system_cooling = raw.get("HC") == 1

    def _num(value: Any) -> float | None:
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    icons: dict[str, Any] = {}

    def _icon(icon_key: str) -> dict[str, Any]:
        return icons.setdefault(
            icon_key,
            {"firmware": None, "mixing_valve_pct": None, "thermostats": {}, "relays": {}},
        )

    # Thermostats (only connected ones, matching the Modbus live/no-conn gating).
    for th_id, therm in dp.items():
        if not therm.get("ON") or not therm.get("LIVE"):
            continue
        icon = _icon(_icon_num(th_id))
        eco = therm.get("CE") == 1
        sp_heat_normal = _num(therm.get("XAH"))
        sp_cool_normal = _num(therm.get("XAC"))
        sp_heat_eco = _num(therm.get("ECOH"))
        sp_cool_eco = _num(therm.get("ECOC"))
        if eco:
            target = sp_cool_eco if system_cooling else sp_heat_eco
        else:
            target = sp_cool_normal if system_cooling else sp_heat_normal
        icon["thermostats"][th_id] = {
            "name": therm.get("NAME"),
            "temp": _num(therm.get("TEMP")),
            "rh": _num(therm.get("RH")),
            "dew": _num(therm.get("DEW")),
            "eco": eco,
            "demand": therm.get("OUT") == 1,
            "cooling": system_cooling,
            "target": target,
            "sp_heat_normal": sp_heat_normal,
            "sp_cool_normal": sp_cool_normal,
            "sp_heat_eco": sp_heat_eco,
            "sp_cool_eco": sp_cool_eco,
        }

    # Relays and mixing valve, per configured controller.
    for icon_key, icon_data in cfg.items():
        if not icon_key.startswith("ICON") or not icon_key[4:].isdigit():
            continue
        icon_num = icon_key[4:]
        icon = _icon(icon_num)
        status = icon_data.get("STATUS", {})
        icon["mixing_valve_pct"] = _num(status.get("AO"))
        for relay_id, config in (icon_data.get("RELAY") or {}).items():
            func = (config.get("FUNC") or "").strip()
            if not func or func.startswith(f"R{icon_num}."):
                continue
            icon["relays"][relay_id] = {
                "name": func,
                "on": status.get(relay_id) == 1,
            }

    return {
        "system": {
            "cooling": system_cooling,
            "pump": raw.get("PUMP") == 1,
            "water_temp": _num(raw.get("WTEMP")),
            "outdoor_temp": None,
        },
        "icons": icons,
    }
