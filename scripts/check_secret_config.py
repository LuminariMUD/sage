#!/usr/bin/env python3
"""Report whether expected credentials are configured without printing values."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from dotenv import dotenv_values

SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "OPENAI_API_KEY",
    "LANGSMITH_API_KEY",
    "SAGE_API_KEY",
    "SAGE_MCP_KEY",
    "SAGE_MCP_BACKEND_KEY",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("names", nargs="*", choices=SECRET_NAMES)
    args = parser.parse_args()

    selected_names = args.names or SECRET_NAMES
    file_values: dict[str, str | None] = {}
    if args.env_file.exists():
        file_values = dotenv_values(args.env_file)
        mode = stat.S_IMODE(args.env_file.stat().st_mode)
        if mode & 0o077:
            print(f"{args.env_file}: WARNING permissions should be 600")
        else:
            print(f"{args.env_file}: permissions restricted")
    else:
        print(f"{args.env_file}: not found; checking the process environment")

    for name in selected_names:
        value = os.environ.get(name) or file_values.get(name)
        print(f"{name}: {'SET' if value else 'MISSING'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
