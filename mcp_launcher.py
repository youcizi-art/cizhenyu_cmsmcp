#!/usr/bin/env python3
"""CMS MCP launcher — runs mcp_server.py (tool logic lives in this repo)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    server = here / "mcp_server.py"
    if not server.is_file():
        print(f"cmsmcp: missing {server}", file=sys.stderr)
        return 3

    origin = (
        os.environ.get("CMS_ORIGIN")
        or os.environ.get("CIZHENYU_CMS_ORIGIN")
        or ""
    ).strip()
    env = os.environ.copy()
    if origin:
        env.setdefault("CMS_ORIGIN", origin)
        env.setdefault("CIZHENYU_CMS_ORIGIN", origin)
    env.setdefault("PYTHONUTF8", "1")

    return subprocess.call([sys.executable, str(server)], env=env, cwd=str(here))


if __name__ == "__main__":
    raise SystemExit(main())
