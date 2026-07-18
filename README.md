# Home Assistant Integration for NGBS iCON

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://hacs.xyz/)
[![Validate](https://img.shields.io/github/actions/workflow/status/sethyx/ngbs_icon_hacs/validate.yml?branch=master&style=flat-square&label=Validate)](https://github.com/sethyx/ngbs_icon_hacs/actions/workflows/validate.yml)
[![Hassfest](https://img.shields.io/github/actions/workflow/status/sethyx/ngbs_icon_hacs/hassfest.yml?branch=master&style=flat-square&label=Hassfest)](https://github.com/sethyx/ngbs_icon_hacs/actions/workflows/hassfest.yml)
[![Release](https://img.shields.io/github/v/release/sethyx/ngbs_icon_hacs?style=flat-square)](https://github.com/sethyx/ngbs_icon_hacs/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11.0%2B-blue?style=flat-square)](https://www.home-assistant.io/)
![License](https://img.shields.io/github/license/sethyx/ngbs_icon_hacs?style=flat-square)

> **Disclaimer:** This is an independent hobby project with no affiliation to, endorsement by, or support from NGBS Hungary Kft. It was built by reverse-engineering documentation available online and against real hardware, not from any official SDK or vendor cooperation. Use at your own risk — the author accepts no responsibility for any damage, malfunction, or unexpected behavior of your heating/cooling system resulting from its use.

A custom integration for [NGBS iCON](https://www.ngbsh.hu/) heating/cooling controllers.

This integration talks to the controller primarily over **Modbus-TCP** (port 502) instead of the manufacturer's proprietary JSON/TCP protocol. The controller itself kills Modbus-TCP connections after roughly 30 seconds regardless of activity, so rather than fighting that, the integration opens a fresh connection for each poll and closes it again immediately afterward — see [Connection handling](#connection-handling) below. The legacy JSON/TCP protocol (port 7992) is still used, but only at **setup/reconfigure time** — see [Setup protocol](#setup-protocol-legacy-jsontcp) below.

## Features

- Auto-discovers every iCON controller present (master + up to 7 slaves) and every connected thermostat — only entities for hardware that actually responds get created. A controller is considered present when its firmware-version register reads back non-zero; a thermostat is included when its `Live` bit is set and its `NoConn` bit is clear.
- Identifies the **Master** controller from the device's own `ISTATUS` flag rather than assuming it's whichever controller has the lowest address (see [Master detection](#master-detection)).
- One Home Assistant device per iCON controller; each thermostat is its own device, linked to its controller via `via_device`.
- **Climate** entities per thermostat: current temperature/humidity, active setpoint (writable), ECO/Comfort preset (writable), HVAC action. Only the **H/C-master thermostat** can switch the whole system between heating and cooling — this is a different concept from the Master *controller* above; see [Devices & entities](#devices--entities).
- **Sensors**: per-thermostat temperature, humidity, dew point; mixing-valve position, water temperature, outdoor temperature, HC mode, firmware version, and diagnostic voltages/cycle counter on the Master controller.
- **Binary sensors**: water pump, per-thermostat HVAC demand (combined and split A-/B-loop), condensation warning, ECO state, connection status, and configured relay/valve outputs.
- After a setpoint, preset, or H/C-mode write, the whole dataset is re-read and pushed to entities almost immediately instead of waiting for the next scheduled poll — see [Live update behavior](#live-update-behavior-after-writes).
- Options flow to adjust the poll interval without reconfiguring the whole entry.

## Requirements

- An NGBS iCON controller with Modbus-TCP enabled (port 502 reachable from Home Assistant).
- Port 7992 (the legacy JSON/TCP protocol) reachable from Home Assistant during setup/reconfigure only, so the SYSID and naming inventory can be fetched automatically.
- A **fixed IP address** for the controller — either set directly in the iCON's own web UI, or reserved for its MAC address on your DHCP server. The integration connects to a single stored IP; if it changes, Home Assistant will lose connectivity until you run **Reconfigure** with the new address.

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
2. Enter the controller's IP address. The System ID is discovered automatically — you don't need to enter it.
3. Optionally adjust the poll interval (default 60 seconds, minimum 30).

The poll interval can later be changed from the integration's **Configure** option without going through setup again. **Reconfigure** re-discovers the SYSID from the (possibly new) IP address and aborts if it doesn't match the originally configured controller, so you can't accidentally repoint an existing entry at a different physical system.

## Devices & entities

### iCON controller devices

One HA device per physical iCON controller that responds on the bus (model "iCON controller", named `iCON <n>`, firmware version as `sw_version`).

| Entity | Platform | Which controller(s) | Notes |
|---|---|---|---|
| Mixing valve | Sensor (%) | **Master only** | Single physical mixing-valve output; gated to the Master controller's device |
| Water pump | Binary sensor | **Master only** | System-wide water pump, read from the Master's digital-input register |
| `<relay name>` | Binary sensor | Any controller with named relays | One per relay/valve output that has a configured name in the legacy inventory (unnamed relays are skipped) |
| Water temperature | Sensor (°C) | **Master only** | |
| Outdoor temperature | Sensor (°C) | **Master only** | |
| HC mode | Sensor (enum: `heating`/`cooling`/`switchover`) | **Master only** | |
| Firmware version | Sensor (diagnostic) | **Master only** | |
| 15V supply voltage | Sensor (mV, diagnostic) | **Master only** | Ai.5 |
| Thermostat supply voltage | Sensor (mV, diagnostic) | **Master only** | Ai.6 |
| I/O reference voltage | Sensor (mV, diagnostic) | **Master only** | Ai.7 |
| I/O cycle counter | Sensor (diagnostic) | **Master only** | Internal regulation-loop counter, useful for confirming the controller is actively cycling |

Relay outputs are read from whichever controller their terminal block physically belongs to — this is **not necessarily the same controller as the thermostats driving them**. On systems with more water circuits than rooms it's common for relays to be spread across multiple iCON controllers while all thermostats are wired to just one; each relay is still correctly attached to its own controller's device.

Relay state is read from the EffOut registers (the actual physical output), not the raw regulation-demand register — so it stays correct when a relay is forced, has a BMS override active, or is driven cross-unit (e.g. one icon's thermostat demand controlling a relay wired to a different icon).

### Thermostat devices

One HA device per thermostat that is live and configured (model "iCON thermostat", named from the legacy protocol's inventory or `Thermostat <id>` as a fallback), linked to its controller device via `via_device`.

| Entity | Platform | Notes |
|---|---|---|
| *(the device itself)* | Climate | Current temperature/humidity, active setpoint (4-way: heat/cool × normal/ECO, resolved by current mode+preset), ECO/Comfort preset, `hvac_action` (idle/heating/cooling). Only the **H/C-master thermostat** (`CFG.HCMASTER` from the legacy protocol) exposes heating/cooling mode switching — every other thermostat follows the system-wide mode read-only |
| Temperature | Sensor (°C) | |
| Humidity | Sensor (%) | |
| Dewpoint temperature | Sensor (°C) | |
| HVAC request | Binary sensor | On when either the A- or B-loop is demanding energy for this zone |
| A-loop demand | Binary sensor | |
| B-loop demand | Binary sensor | |
| Condensation | Binary sensor (problem) | On when condensation risk is blocking cooling in that zone |
| ECO | Binary sensor | Mirrors the climate entity's ECO preset as a standalone sensor |
| Connection | Binary sensor (connectivity) | On for every thermostat present in a poll (offline thermostats are dropped from the dataset entirely rather than reported "off") |

## Master detection

The register map exposes an `ISTATUS` flag per controller (bit 0 = "this device is the Master") at an absolute, non-offset "extended function" address. On every poll, the integration reads this flag from each present controller's extended block and uses whichever one reports itself as Master for all Master-scoped data (water/outdoor temperature, HC mode, mixing valve, pump, diagnostics). If no controller reports the flag (e.g. older firmware), it falls back to the lowest-addressed present controller, matching the wiring convention where RTU address 1 is always the Master.

## Live update behavior after writes

Home Assistant's normal `DataUpdateCoordinator.async_request_refresh()` can be debounced, which made setpoint/preset/mode changes take up to the full poll interval to show up. To fix this, every climate write (`async_set_temperature`, `async_set_hvac_mode`, `async_set_preset_mode`) instead calls a dedicated `async_refresh_now()` that bypasses that debounce and re-reads the **entire** dataset directly.

A few things drove that design:

- **A write can affect more than the thermostat it targeted.** The H/C-master thermostat's preset can be configured to cascade to every zone, and heating/cooling mode is always system-wide — so a partial, single-controller refresh isn't safe, even though it would be faster.
- **Relays can live on a different controller than the thermostat driving them** (see above), so a full re-read is needed to catch relay/valve changes triggered by a thermostat write.
- **The controller itself needs time to settle.** A write goes to a separate command register from the one entities read back from; the controller's internal regulation cycle takes roughly 1–1.2 seconds (measured against live hardware) to fold a write into its read-only mirror registers. `async_refresh_now()` waits 1.5 seconds before reading back to give margin over that.
- A full re-read of the whole bus is fast in practice (well under a second on top of the settle delay), so none of this meaningfully changes the "quick" experience the fix is meant to deliver.

## Connection handling

The controller kills Modbus-TCP connections after roughly 30 seconds, regardless of whether they're idle or actively being used. Rather than maintaining one persistent connection for the integration's lifetime (which would just mean eating a spurious disconnect on whatever request happened to be in flight when the timer expired), the client opens a connection for each read cycle and closes it again as soon as that cycle finishes.

There's one deliberate exception: a write leaves its connection open on success instead of closing it immediately. Since every climate write is always followed by a quick refresh roughly 1.5 seconds later (see [Live update behavior](#live-update-behavior-after-writes)), that follow-up read reuses the still-open connection instead of paying for a reconnect, then closes it once it's done. If a write isn't followed by a read within that window, the connection is simply picked up (and reconnected if needed) by whatever Modbus operation happens next.

## Setup protocol (legacy JSON/TCP)

Modbus has no way to expose human-readable thermostat/relay names, or the controller's System ID (SYSID), so the legacy JSON/TCP protocol (port 7992) is still used for those two things — **only during config flow setup or reconfigure**, never during normal polling or control:

1. **SYSID auto-discovery**: an unauthenticated `{"RELOAD": 6}` query is sent to port 7992. Unlike a normal request, this variant needs no SYSID up front and the controller replies with its `SYSID` plus per-controller firmware info — so you no longer need to look up or type in the System ID yourself.
2. **Naming inventory**: using the discovered SYSID, a full `{"RELOAD": ""}` query is sent to fetch thermostat names, configured relay/valve names, and the H/C-master thermostat id (`CFG.HCMASTER`). These are stored in the config entry and used purely to label Modbus-driven entities.

Runtime polling and all writes (setpoints, presets, HVAC mode) go over Modbus only.

## Development

This repository also ships CLI tools (`custom_components/ngbs_icon/tools/`) used while migrating from the legacy JSON protocol to Modbus:

- `query_json.py` — fetch and print a normalized dataset via the legacy JSON protocol.
- `query_modbus.py` — fetch and print the same normalized dataset via the new Modbus library.
- `compare.py` — fetch both datasets and report any mismatch, used to verify the Modbus implementation against the legacy protocol on real hardware.

See `iCON_MODBUS_Register_Map.md` for the Modbus register documentation this integration is built against.

## Acknowledgements

Thanks to [molnarg](https://github.com/molnarg) for [ngbs-icon](https://github.com/molnarg/ngbs-icon), which documented the legacy JSON/TCP protocol and was a valuable reference during development of this integration.

## License

See [LICENSE](LICENSE).
