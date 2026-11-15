"""Authenticated CMS HTTP client — cookie from Deploy session; tools call CMS APIs."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from cms_session import load_active_session


def _ssl_context() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


class CmsClient:
    def __init__(self, origin: str, cookie: str):
        self.origin = origin.rstrip("/")
        self.cookie = cookie
        self._ctx = _ssl_context()

    @classmethod
    def from_active(cls, fallback_origin: str | None = None) -> "CmsClient":
        s = load_active_session(fallback_origin)
        return cls(s["origin"], s["cookie"])

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
    ) -> Any:
        url = f"{self.origin}{path}"
        data = None
        headers = {
            "Cookie": self.cookie,
            "Accept": "application/json",
            "User-Agent": "cizhenyu-cmsmcp/0.6",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last = ""
        for attempt in range(4):
            if attempt:
                time.sleep(0.6 * attempt)
            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, context=self._ctx, timeout=120) as res:
                    text = res.read().decode("utf-8", errors="replace")
                    if not text.strip():
                        return None
                    return json.loads(text)
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", errors="replace")
                last = f"{path} → {e.code}: {text}"
                if e.code >= 500 and attempt < 3:
                    continue
                raise RuntimeError(last) from None
            except Exception as e:  # noqa: BLE001
                last = f"请求失败 {path}: {e}"
                if attempt < 3:
                    continue
                raise RuntimeError(last) from None
        raise RuntimeError(last or f"请求失败 {path}")

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, body)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def list_models(self) -> list[Any]:
        return _extract_list(self.get("/api/schema/models"))

    def list_collections(self) -> list[Any]:
        return _extract_list(self.get("/api/schema/collections"))

    def list_nav_groups(self) -> list[Any]:
        return _extract_list(self.get("/api/schema/nav-groups"))

    def get_field_settings(self, collection_id: str) -> Any:
        return self.get(f"/api/schema/collections/{collection_id}/field-settings")

    def put_field_settings(self, collection_id: str, settings: Any) -> Any:
        return self.put(
            f"/api/schema/collections/{collection_id}/field-settings",
            {"settings": settings},
        )

    def get_api_policy(self, collection_id: str) -> Any:
        return self.get(f"/api/schema/collections/{collection_id}/api-policy")

    def put_api_policy(self, collection_id: str, policy: Any) -> Any:
        return self.put(
            f"/api/schema/collections/{collection_id}/api-policy",
            {"policy": policy},
        )

    def get_frontend_sites(self) -> Any:
        return self.get("/api/sites/frontend")

    def list_entities_paginated(
        self,
        slug: str,
        page_size: int = 50,
        locale: str | None = None,
    ) -> list[Any]:
        page_size = max(1, min(100, int(page_size)))
        page = 1
        out: list[Any] = []
        while page <= 500:
            path = f"/api/entities/{quote(slug, safe='')}?page={page}&pageSize={page_size}"
            if locale and locale.strip():
                path += f"&locale={quote(locale.strip())}"
            v = self.get(path)
            batch = _extract_list(v)
            out.extend(batch)
            has_more = False
            if isinstance(v, dict):
                meta = v.get("meta") or {}
                has_more = bool(meta.get("hasMore"))
            if not has_more or not batch:
                break
            page += 1
        return out

    def get_entity(self, slug: str, entity_id: str, locale: str | None = None) -> Any:
        entity_id = (entity_id or "").strip()
        if not entity_id:
            raise ValueError("实体 id 不能为空")
        path = f"/api/entities/{quote(slug, safe='')}/{quote(entity_id, safe='')}"
        if locale and locale.strip():
            path += f"?locale={quote(locale.strip())}"
        try:
            v = self.get(path)
            if v is None:
                raise RuntimeError("empty")
            if isinstance(v, dict):
                for key in ("item", "data", "entity"):
                    if key in v and isinstance(v[key], dict):
                        return v[key]
                if "id" in v or "data" in v:
                    return v
            return v
        except Exception:
            for row in self.list_entities_paginated(slug, 100, locale):
                if isinstance(row, dict) and row.get("id") == entity_id:
                    return row
            raise RuntimeError(f"未找到 {slug}/{entity_id}") from None

    def batch_save_entities(self, slug: str, payload: Any) -> Any:
        return self.post(f"/api/entities/{quote(slug, safe='')}/batch-save", payload)

    def delete_entity(self, slug: str, entity_id: str) -> Any:
        return self.delete(f"/api/entities/{quote(slug, safe='')}/{quote(entity_id, safe='')}")


def _extract_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        for key in ("list", "items", "data", "models", "collections", "sites", "navGroups"):
            x = v.get(key)
            if isinstance(x, list):
                return x
            if isinstance(x, dict) and isinstance(x.get("list"), list):
                return x["list"]
    return []
