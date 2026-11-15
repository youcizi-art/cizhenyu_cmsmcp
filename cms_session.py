"""Load Deploy CMS login session (permission follows the logged-in account)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def _default_session_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
    if base:
        return Path(base) / "cizhenyu-deploy" / "auth" / "cms"
    return Path.home() / "AppData" / "Local" / "cizhenyu-deploy" / "auth" / "cms"


def session_dir() -> Path:
    env = (
        os.environ.get("CIZHENYU_CMS_SESSION_DIR")
        or os.environ.get("CMS_SESSION_DIR")
        or ""
    ).strip()
    if env:
        return Path(env)
    return _default_session_dir()


def _origin_key(origin: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in origin)


def _normalize_origin(origin: str) -> str:
    s = (origin or "").strip()
    if not s:
        raise ValueError("CMS 地址不能为空")
    if "://" not in s:
        s = f"https://{s}"
    return s.rstrip("/")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def load_active_session(
    fallback_origin: str | None = None,
) -> dict[str, str]:
    """
    Returns {origin, cookie, username?}.
    Prefers Deploy active.json → matching session file.
    """
    dir_ = session_dir()
    active = _read_json(dir_ / "active.json")
    origin = ""
    if active:
        origin = str(active.get("origin") or "").strip()

    if not origin and fallback_origin:
        origin = _normalize_origin(fallback_origin)

    if origin:
        origin = _normalize_origin(origin)
        session = _read_json(dir_ / f"{_origin_key(origin)}.json")
        if session and str(session.get("cookie") or "").strip():
            return {
                "origin": _normalize_origin(str(session.get("origin") or origin)),
                "cookie": str(session.get("cookie")).strip(),
                "username": str(session.get("username") or active.get("username") or ""),
            }

    # Fallback: newest session file in dir
    newest: dict[str, Any] | None = None
    newest_at = -1
    if dir_.is_dir():
        for path in dir_.glob("*.json"):
            if path.name == "active.json":
                continue
            data = _read_json(path)
            if not data or not str(data.get("cookie") or "").strip():
                continue
            saved = int(data.get("savedAt") or data.get("saved_at") or 0)
            if saved >= newest_at:
                newest_at = saved
                newest = data

    if newest:
        return {
            "origin": _normalize_origin(str(newest.get("origin") or "")),
            "cookie": str(newest.get("cookie")).strip(),
            "username": str(newest.get("username") or ""),
        }

    hint = str(dir_)
    raise RuntimeError(
        f"未检测到 Deploy CMS 登录（session dir: {hint}）。请先在 Deploy 运营页登录 CMS。"
    )


def default_site_key() -> str:
    return (os.environ.get("CMS_SITE_KEY") or "default").strip() or "default"


def default_site_origin(cms_origin: str) -> str:
    env = (os.environ.get("CMS_SITE_ORIGIN") or "").strip()
    return env or cms_origin
