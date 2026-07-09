#!/usr/bin/env python3
"""Query the full iCON dataset via the legacy JSON/TCP protocol.

Outputs the shared canonical JSON schema so it can be diffed against the
Modbus output (see compare.py).

Usage:
    python tools/query_old.py --host 192.168.1.50 --sysid ABCD1234
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from names import (  # noqa: E402
    DEFAULT_JSON_PORT,
    IconJsonClient,
    IconJsonError,
    raw_to_canonical,
)


async def fetch(host: str, sysid: str, port: int) -> dict:
    """Fetch and normalise the legacy dataset."""
    client = IconJsonClient(host, sysid, port=port)
    return raw_to_canonical(await client.async_get_raw())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Controller IP address")
    parser.add_argument("--sysid", required=True, help="System ID (SYSID)")
    parser.add_argument("--port", type=int, default=DEFAULT_JSON_PORT)
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead")
    args = parser.parse_args()

    try:
        if args.raw:
            client = IconJsonClient(args.host, args.sysid, port=args.port)
            data = asyncio.run(client.async_get_raw())
        else:
            data = asyncio.run(fetch(args.host, args.sysid, args.port))
    except IconJsonError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
