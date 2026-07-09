#!/usr/bin/env python3
"""Query the full iCON dataset via the new Modbus-TCP library.

Opens a single Modbus connection, reads once, closes it, and prints the shared
canonical JSON schema. Pass --sysid to enrich the output with human-readable
names fetched over the legacy JSON protocol.

Usage:
    python tools/query_modbus.py --host 192.168.1.50
    python tools/query_modbus.py --host 192.168.1.50 --sysid ABCD1234
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modbus_client import IconModbusClient, IconModbusError  # noqa: E402
from names import IconJsonClient, IconJsonError  # noqa: E402


async def fetch(host: str, port: int, unit: int, sysid: str | None) -> dict:
    """Fetch the Modbus dataset, optionally enriched with JSON names."""
    inventory = None
    if sysid:
        try:
            inventory = await IconJsonClient(host, sysid).async_fetch_inventory()
        except IconJsonError as err:
            print(f"Warning: could not fetch names: {err}", file=sys.stderr)

    client = IconModbusClient(host, port=port, unit=unit)
    try:
        await client.async_connect()
        return await client.async_get_data(inventory)
    finally:
        await client.async_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Controller IP address")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--unit", type=int, default=0, help="Modbus unit id")
    parser.add_argument("--sysid", help="System ID for JSON name enrichment")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    try:
        data = asyncio.run(fetch(args.host, args.port, args.unit, args.sysid))
    except IconModbusError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
