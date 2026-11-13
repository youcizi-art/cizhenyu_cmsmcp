#!/usr/bin/env python3
"""CMS MCP launcher — prefers Deploy sidecar binary, falls back to stdio stub."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_sidecar() -> Path | None:
    env = os.environ.get("CIZHENYU_CMS_MCP_BIN", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    here = Path(__file__).resolve().parent
    candidates = [
        here / "cizhenyu-cms-mcp.exe",
        here / "cizhenyu-cms-mcp",
        here.parent.parent / "cizhenyu-cms-mcp.exe",
    ]
    # Sibling of current Deploy exe if launched from workRoot scripts
    for p in candidates:
        if p.is_file():
            return p
    which = shutil.which("cizhenyu-cms-mcp") or shutil.which("cizhenyu-cms-mcp.exe")
    if which:
        return Path(which)
    return None


def main() -> int:
    origin = (
        os.environ.get("CMS_ORIGIN")
        or os.environ.get("CIZHENYU_CMS_ORIGIN")
        or ""
    ).strip()
    if not origin:
        print("cmsmcp: set CMS_ORIGIN (Deploy will inject from CMS login)", file=sys.stderr)
        return 2

    site = (os.environ.get("CMS_SITE_KEY") or "default").strip() or "default"
    site_origin = (os.environ.get("CMS_SITE_ORIGIN") or origin).strip() or origin

    sidecar = find_sidecar()
    if sidecar is None:
        print(
            "cmsmcp: cizhenyu-cms-mcp binary not found. "
            "Install/build Deploy sidecar or place it next to this launcher.",
            file=sys.stderr,
        )
        return 3

    # 鉴权以 Deploy 当前活跃登录为准；CLI origin 仅作回退
    cmd = [str(sidecar), "--from-active"]
    if origin:
        cmd.extend(["--origin", origin])
    if site:
        cmd.extend(["--site", site])
    if site_origin:
        cmd.extend(["--site-origin", site_origin])
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
