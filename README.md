# NGBS iCON

Home Assistant custom integration for [NGBS iCON](https://www.ngbsh.hu/) heating/cooling controllers.

This integration talks to the controller over **Modbus-TCP** (port 502) instead of the manufacturer's proprietary JSON/TCP protocol. It opens a single Modbus connection when Home Assistant starts and keeps it alive for as long as the integration is loaded, polling over that connection instead of reconnecting on every request.

## Features

- Discovers connected iCON controllers (master + slaves) and thermostats automatically — only entities for hardware that is actually present get created.
- One Home Assistant device per iCON controller; each thermostat is its own device, linked to its controller via `via_device`.
- **Climate** entities per thermostat: current temperature/humidity, active setpoint, ECO/Comfort preset, HVAC action. Only the H/C master thermostat can switch the system between heating and cooling.
- **Sensors**: per-thermostat temperature, humidity and dew point; mixing valve position; water temperature; outdoor temperature.
- **Binary sensors**: water pump, per-thermostat HVAC demand, configured relay/valve outputs.
- Options flow to adjust the poll interval without reconfiguring the whole entry.

## Requirements

- An NGBS iCON controller with Modbus-TCP enabled (port 502 reachable from Home Assistant).
- The controller's **System ID** (SYSID), used once during setup to fetch human-readable thermostat and relay names over the legacy JSON protocol — Modbus itself has no way to expose these names. Runtime polling and control use Modbus only.

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS (category: Integration), or install it directly if it has been added to the default HACS store.
2. Install "NGBS iCON" from HACS.
3. Restart Home Assistant.

### Manual

1. Copy `custom_components/ngbs_icon` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Configuration is done entirely through the UI:

1. **Settings → Devices & Services → Add Integration → NGBS iCON**.
2. Enter the controller's IP address and System ID (SYSID).
3. Optionally adjust the poll interval (default 60 seconds, minimum 30).

The poll interval can later be changed from the integration's **Configure** option without going through setup again.

## Development

This repository also ships CLI tools (`custom_components/ngbs_icon/tools/`) used while migrating from the legacy JSON protocol to Modbus:

- `query_old.py` — fetch and print a normalized dataset via the legacy JSON protocol.
- `query_new.py` — fetch and print the same normalized dataset via the new Modbus library.
- `compare.py` — fetch both datasets and report any mismatch, used to verify the Modbus implementation against the legacy protocol on real hardware.

See `iCON_MODBUS_Register_Map.md` for the Modbus register documentation this integration is built against.

## License

See [LICENSE](LICENSE).
