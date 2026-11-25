#!/usr/bin/env python3
"""Cizhenyu CMS MCP — stdio newline-delimited JSON-RPC (MCP standard).

Auth: Deploy CMS login session (CIZHENYU_CMS_SESSION_DIR / app data auth/cms).
Deploy only injects origin/session path; all CMS tools live here.

Smoke:
    python mcp_server.py
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

import tools_bootstrap
import tools_cms
import tools_crawl
import tools_schema
from cms_api import CmsClient
from cms_session import default_site_key, default_site_origin, load_active_session

SERVER_NAME = "cizhenyu-cms"
SERVER_VERSION = "0.6.0"
SUPPORTED_PROTOCOLS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-06-18"
MAX_OUTPUT_CHARS = 80_000

_SITE = {
    "type": "string",
    "description": "站点 key。集合实例为 {siteKey}_{logical}；多站点共用同一模型。",
}
_LOGICAL = {
    "type": "string",
    "description": "逻辑集合/模型名（如 article、product）。解析为 {siteKey}_{logical}。",
}
_COLLECTION = {
    "type": "string",
    "description": "完整集合 slug；也可只传 logical 名（自动加 siteKey 前缀）。",
}
_CONFIRM = {"type": "boolean", "description": "Must be true after user approval"}
_TARGET = {
    "type": "object",
    "properties": {"siteKey": _SITE, "site": _SITE, "logical": _LOGICAL, "collection": _COLLECTION},
}
_DRAFT = {
    "type": "object",
    "properties": {
        "siteKey": _SITE,
        "site": _SITE,
        "logical": _LOGICAL,
        "collection": _COLLECTION,
        "title": {"type": "string"},
        "slug": {"type": "string"},
        "content": {"type": "string"},
        "metaDescription": {"type": "string"},
        "locale": {"type": "string"},
        "languageGroupKey": {"type": "string"},
        "data": {"type": "object"},
        "confirm": _CONFIRM,
    },
    "required": ["title", "content", "confirm"],
}

TOOLS: list[dict[str, Any]] = [
    {"name": "cms_whoami", "description": "Check whether the local CMS login session works", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cms_sites_list", "description": "List frontend sites registered in CMS", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cms_models_list", "description": "List shared CMS models (global schema)", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "cms_model_get",
        "description": "Get one shared model by name / slug / id",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "slug": {"type": "string"}, "id": {"type": "string"}},
        },
    },
    {"name": "cms_nav_groups_list", "description": "List CMS nav groups", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "cms_collections_list",
        "description": "List collection instances. Pass allSites=true for every site.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "allSites": {"type": "boolean", "description": "If true, return collections for all sites"},
            },
        },
    },
    {
        "name": "cms_collection_inspect",
        "description": "Resolve {siteKey}_{logical} and return collection + linked model (via modelSlug/modelId) + fieldSettings + apiPolicy.",
        "inputSchema": _TARGET,
    },
    {"name": "cms_collection_fields", "description": "Get field settings for a site collection", "inputSchema": _TARGET},
    {"name": "cms_collection_api_policy", "description": "Get API policy for a site collection", "inputSchema": _TARGET},
    {
        "name": "cms_collection_fields_put",
        "description": "Update field settings. HIGH RISK. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "settings": {"type": "object"},
                "confirm": _CONFIRM,
            },
            "required": ["settings", "confirm"],
        },
    },
    {
        "name": "cms_collection_api_policy_put",
        "description": "Update API policy. HIGH RISK. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "policy": {"type": "object"},
                "confirm": _CONFIRM,
            },
            "required": ["policy", "confirm"],
        },
    },
    {
        "name": "cms_entities_list",
        "description": "List entities. Pass siteKey + logical (or collection).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "locale": {"type": "string"},
                "pageSize": {"type": "integer"},
            },
        },
    },
    {
        "name": "cms_entity_get",
        "description": "Get one entity by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "id": {"type": "string"},
                "locale": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "cms_entity_save",
        "description": "Generic entity create/update. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "data": {"type": "object"},
                "entries": {"type": "array"},
                "id": {"type": "string"},
                "locale": {"type": "string"},
                "languageGroupKey": {"type": "string"},
                "confirm": _CONFIRM,
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "cms_tech_home",
        "description": "Fetch homepage tech signals for siteOrigin",
        "inputSchema": {"type": "object", "properties": {"siteOrigin": {"type": "string"}}},
    },
    {
        "name": "cms_tech_robots",
        "description": "Fetch robots.txt for siteOrigin",
        "inputSchema": {"type": "object", "properties": {"siteOrigin": {"type": "string"}}},
    },
    {
        "name": "cms_tech_sitemap",
        "description": "Probe sitemap for siteOrigin",
        "inputSchema": {"type": "object", "properties": {"siteOrigin": {"type": "string"}}},
    },
    {
        "name": "crawl_fetch",
        "description": "Fetch a URL",
        "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "cms_content_draft",
        "description": "Save article-like content as draft. Requires confirm=true.",
        "inputSchema": _DRAFT,
    },
    {
        "name": "cms_content_publish",
        "description": "Publish article-like content. HIGH RISK. Requires confirm=true.",
        "inputSchema": _DRAFT,
    },
    {
        "name": "cms_entity_delete",
        "description": "Delete one entity. HIGH RISK. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "logical": _LOGICAL,
                "collection": _COLLECTION,
                "id": {"type": "string"},
                "confirm": _CONFIRM,
            },
            "required": ["id", "confirm"],
        },
    },
    {
        "name": "cms_revalidate",
        "description": "Revalidate frontend cache. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "paths": {"type": "array", "items": {"type": "string"}},
                "confirm": _CONFIRM,
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "cms_nav_group_ensure",
        "description": "Idempotently ensure site nav group hierarchy (e.g. {siteKey}/content, {siteKey}/products, {siteKey}/business, {siteKey}/settings). Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "path": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
                "confirm": _CONFIRM,
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "cms_models_ensure",
        "description": "Validate three-layer field rules and create ONLY missing CMS models (never overwrites existing shared models). Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "models": {"type": "array", "items": {"type": "object"}},
                "confirm": _CONFIRM,
            },
            "required": ["models", "confirm"],
        },
    },
    {
        "name": "cms_collections_ensure",
        "description": "Idempotently instantiate {siteKey}_{logical} collections under {siteKey}/* nav groups and configure public_read / submit_only API policies. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "collections": {"type": "array", "items": {"type": "object"}},
                "corsOrigins": {"type": "array", "items": {"type": "string"}},
                "skipExistingPolicy": {"type": "boolean"},
                "confirm": _CONFIRM,
            },
            "required": ["collections", "confirm"],
        },
    },
    {
        "name": "cms_frontend_site_upsert",
        "description": "Idempotently register or update a FrontendSite entry (siteKey, origin, revalidateUrl, revalidateSecret, groupIds) in CMS. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteKey": _SITE,
                "site": _SITE,
                "displayName": {"type": "string"},
                "siteOrigin": {"type": "string"},
                "origin": {"type": "string"},
                "revalidateUrl": {"type": "string"},
                "revalidateSecret": {"type": "string"},
                "confirm": _CONFIRM,
            },
            "required": ["confirm"],
        },
    },
]

INSTRUCTIONS = (
    "CMS MCP for Cizhenyu. Models are global; collections are {siteKey}_{logical}. "
    "Write tools need confirm=true. Login via Cizhenyu Deploy first."
)


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str, data: dict | None = None) -> None:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data:
        payload["data"] = data
    _send({"jsonrpc": "2.0", "id": request_id, "error": payload})


def _truncate(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return json.dumps(
        {"truncated": True, "note": f"output exceeded {MAX_OUTPUT_CHARS} chars", "preview": text[:4000]},
        ensure_ascii=False,
    )


def _require_confirm(args: dict[str, Any], action: str) -> None:
    if args.get("confirm") is True:
        return
    raise PermissionError(
        f"已拒绝执行「{action}」。请先向用户展示将写入/删除的内容，获得明确同意后，以 confirm=true 再次调用。"
    )


def _site_key(args: dict[str, Any]) -> str:
    for key in ("site", "siteKey"):
        v = args.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return default_site_key()


def _site_origin(args: dict[str, Any], cms_origin: str) -> str:
    v = args.get("siteOrigin")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return default_site_origin(cms_origin)


def _client(fallback_origin: str | None = None) -> CmsClient:
    return CmsClient.from_active(fallback_origin)


def call_tool(name: str, args: dict[str, Any]) -> Any:
    fallback = (os.environ.get("CMS_ORIGIN") or os.environ.get("CIZHENYU_CMS_ORIGIN") or "").strip()
    site_key = _site_key(args)
    all_sites = bool(args.get("allSites")) or site_key == "*"

    if name == "cms_whoami":
        return tools_cms.whoami(_client(fallback))
    if name == "cms_sites_list":
        return tools_cms.sites_list(_client(fallback))
    if name == "cms_models_list":
        return tools_schema.models_list(_client(fallback))
    if name == "cms_model_get":
        return tools_schema.model_get(_client(fallback), args)
    if name == "cms_nav_groups_list":
        return tools_schema.nav_groups_list(_client(fallback))
    if name == "cms_collections_list":
        return tools_cms.collections_list(_client(fallback), site_key, all_sites)
    if name == "cms_collection_inspect":
        return tools_schema.collection_inspect(_client(fallback), args, site_key)
    if name == "cms_collection_fields":
        return tools_schema.collection_fields(_client(fallback), args, site_key)
    if name == "cms_collection_api_policy":
        return tools_schema.collection_api_policy(_client(fallback), args, site_key)
    if name == "cms_entities_list":
        return tools_cms.entities_list(_client(fallback), args, site_key)
    if name == "cms_entity_get":
        return tools_cms.entity_get(_client(fallback), args, site_key)

    if name in ("cms_tech_home", "cms_tech_robots", "cms_tech_sitemap"):
        try:
            cms_origin = load_active_session(fallback or None)["origin"]
        except Exception:
            cms_origin = fallback
        origin = _site_origin(args, cms_origin)
        if not origin or origin.rstrip("/") == (cms_origin or "").rstrip("/"):
            raise ValueError("请传入 siteOrigin（前端站点地址），不要用 CMS 管理地址")
        if name == "cms_tech_home":
            return tools_crawl.tech_home(origin)
        if name == "cms_tech_robots":
            return tools_crawl.tech_robots(origin)
        return tools_crawl.tech_sitemap(origin)

    if name == "crawl_fetch":
        return tools_crawl.crawl_fetch(args)

    if name == "cms_entity_save":
        _require_confirm(args, "通用实体写入")
        return tools_cms.entity_save(_client(fallback), site_key, args)
    if name == "cms_content_draft":
        _require_confirm(args, "写入草稿")
        return tools_cms.content_save(_client(fallback), site_key, args, False)
    if name == "cms_content_publish":
        _require_confirm(args, "发布内容")
        return tools_cms.content_save(_client(fallback), site_key, args, True)
    if name == "cms_entity_delete":
        _require_confirm(args, "删除内容")
        return tools_cms.entity_delete(_client(fallback), site_key, args)
    if name == "cms_collection_fields_put":
        _require_confirm(args, "更新集合字段设置")
        return tools_schema.collection_fields_put(_client(fallback), args, site_key)
    if name == "cms_collection_api_policy_put":
        _require_confirm(args, "更新集合 API 策略")
        return tools_schema.collection_api_policy_put(_client(fallback), args, site_key)
    if name == "cms_revalidate":
        _require_confirm(args, "刷新前端缓存")
        return tools_cms.revalidate(_client(fallback), site_key, args)
    if name == "cms_nav_group_ensure":
        _require_confirm(args, "创建站点导航分组")
        return tools_bootstrap.nav_group_ensure(_client(fallback), args, site_key)
    if name == "cms_models_ensure":
        _require_confirm(args, "补齐缺失数据模型")
        return tools_bootstrap.models_ensure(_client(fallback), args, site_key)
    if name == "cms_collections_ensure":
        _require_confirm(args, "实例化站点集合与公开策略")
        return tools_bootstrap.collections_ensure(_client(fallback), args, site_key)
    if name == "cms_frontend_site_upsert":
        _require_confirm(args, "注册或更新前端站点")
        return tools_bootstrap.frontend_site_upsert(_client(fallback), args, site_key)

    raise KeyError(name)


def handle(request: dict[str, Any]) -> None:
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol = requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
        _result(
            request_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            },
        )
        return

    if method in ("notifications/initialized", "notifications/cancelled", "initialized"):
        return

    if method == "ping":
        _result(request_id, {})
        return

    if method == "tools/list":
        _result(request_id, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            payload = call_tool(str(name), arguments)
            _result(
                request_id,
                {"content": [{"type": "text", "text": _truncate(payload)}], "isError": False},
            )
        except KeyError:
            _error(request_id, -32602, f"unknown tool: {name}", {"available": [t["name"] for t in TOOLS]})
        except (ValueError, PermissionError, RuntimeError) as exc:
            _result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)}, ensure_ascii=False)}],
                    "isError": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{SERVER_NAME}] tool {name} failed: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            _result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
                            ),
                        }
                    ],
                    "isError": True,
                },
            )
        return

    if method == "resources/list":
        _result(request_id, {"resources": []})
        return

    if request_id is None:
        return

    _error(request_id, -32601, f"method not found: {method}")


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    print(f"[{SERVER_NAME}] ready (stdio NDJSON)", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            _error(None, -32700, f"parse error: {exc}")
            continue
        if not isinstance(request, dict):
            _error(None, -32600, "request must be a JSON object")
            continue
        try:
            handle(request)
        except Exception as exc:  # pragma: no cover
            print(f"[{SERVER_NAME}] handler crashed: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if request.get("id") is not None:
                _error(request.get("id"), -32603, f"internal error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
