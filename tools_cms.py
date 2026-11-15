"""CMS content tools: sites, collections, entities, draft/publish, revalidate."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from cms_api import CmsClient
from tools_resolve import resolve_collection_slug


def whoami(client: CmsClient) -> dict[str, Any]:
    cols = client.list_collections()
    return {
        "ok": True,
        "cmsOrigin": client.origin,
        "collectionsVisible": len(cols),
        "message": "已使用本机保存的 CMS 登录态；可见集合数取决于当前账号权限",
    }


def sites_list(client: CmsClient) -> dict[str, Any]:
    sites = client.get_frontend_sites()
    return {"sites": sites, "cmsOrigin": client.origin}


def collections_list(client: CmsClient, site_key: str, all_sites: bool) -> dict[str, Any]:
    ns = (site_key or "").strip().lower()
    cols = client.list_collections()
    if all_sites or not ns or ns == "*":
        filtered = cols
    else:
        prefix = f"{ns}_"
        filtered = [
            c
            for c in cols
            if isinstance(c, dict)
            and isinstance(c.get("slug"), str)
            and (c["slug"].startswith(prefix) or c["slug"] == ns)
        ]
    return {
        "siteKey": None if all_sites or ns == "*" else ns,
        "allSites": all_sites or not ns or ns == "*",
        "count": len(filtered),
        "collections": filtered,
        "note": "集合实例命名：{siteKey}_{logical}；模型全局共用。",
    }


def entities_list(client: CmsClient, args: dict[str, Any], site_key: str) -> dict[str, Any]:
    collection = resolve_collection_slug(client, args, site_key)
    page_size = int(args.get("pageSize") or 50)
    page_size = max(1, min(100, page_size))
    locale = args.get("locale")
    locale = locale.strip() if isinstance(locale, str) and locale.strip() else None
    items = client.list_entities_paginated(collection, page_size, locale)
    return {
        "siteKey": site_key,
        "collection": collection,
        "locale": locale,
        "count": len(items),
        "items": items,
    }


def entity_get(client: CmsClient, args: dict[str, Any], site_key: str) -> dict[str, Any]:
    collection = resolve_collection_slug(client, args, site_key)
    entity_id = args.get("id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("需要 id")
    locale = args.get("locale")
    locale = locale.strip() if isinstance(locale, str) and locale.strip() else None
    row = client.get_entity(collection, entity_id.strip(), locale)
    return {"siteKey": site_key, "collection": collection, "item": row}


def _build_entries(site_key: str, args: dict[str, Any]) -> list[Any]:
    entries = args.get("entries")
    if isinstance(entries, list):
        if not entries:
            raise ValueError("entries 不能为空")
        return entries
    data = args.get("data")
    if not isinstance(data, dict):
        raise ValueError("需要 data（字段对象）或 entries（批量数组）")
    locale = args.get("locale")
    locale = locale.strip() if isinstance(locale, str) and locale.strip() else "zh-CN"
    slug_hint = data.get("slug") if isinstance(data.get("slug"), str) else "entity"
    group = args.get("languageGroupKey")
    if isinstance(group, str) and group.strip():
        group = group.strip()
    else:
        group = f"{site_key[:8]}-mcp-{str(slug_hint)[:24]}"
    entry: dict[str, Any] = {
        "locale": locale,
        "languageGroupKey": group,
        "data": data,
    }
    eid = args.get("id")
    if isinstance(eid, str) and eid.strip():
        entry["id"] = eid.strip()
    return [entry]


def entity_save(client: CmsClient, site_key: str, args: dict[str, Any]) -> dict[str, Any]:
    collection = resolve_collection_slug(client, args, site_key)
    entries = _build_entries(site_key, args)
    res = client.batch_save_entities(collection, entries)
    saved_id = None
    if isinstance(res, dict):
        lst = (res.get("list") or [])
        if lst and isinstance(lst[0], dict):
            saved_id = lst[0].get("id")
        saved_id = saved_id or res.get("id")
    return {
        "ok": True,
        "siteKey": site_key,
        "collection": collection,
        "entityId": saved_id,
        "result": res,
        "message": f"已写入 {collection}",
    }


def content_save(
    client: CmsClient, site_key: str, args: dict[str, Any], publish: bool
) -> dict[str, Any]:
    title = args.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("需要 title")
    title = title.strip()
    slug = args.get("slug")
    slug = slug.strip() if isinstance(slug, str) and slug.strip() else "mcp-draft"
    content = args.get("content") if isinstance(args.get("content"), str) else ""
    meta = args.get("metaDescription") if isinstance(args.get("metaDescription"), str) else ""
    locale = args.get("locale")
    locale = locale.strip() if isinstance(locale, str) and locale.strip() else "zh-CN"
    status = "published" if publish else "draft"
    collection = resolve_collection_slug(client, args, site_key)
    group = args.get("languageGroupKey")
    if isinstance(group, str) and group.strip():
        group = group.strip()
    else:
        group = f"{site_key[:8]}-mcp-{slug[:24]}"

    data: dict[str, Any] = {
        "title": title,
        "slug": slug,
        "status": status,
        "seo_title": title,
        "seo_description": meta,
        "summary": meta,
        "content": content,
        "h1": title,
    }
    extra = args.get("data")
    if isinstance(extra, dict):
        data.update(extra)

    entries = [{"locale": locale, "languageGroupKey": group, "data": data}]
    res = client.batch_save_entities(collection, entries)
    saved_id = None
    if isinstance(res, dict):
        lst = res.get("list") or []
        if lst and isinstance(lst[0], dict):
            saved_id = lst[0].get("id")
        saved_id = saved_id or res.get("id")
    return {
        "ok": True,
        "siteKey": site_key,
        "collection": collection,
        "locale": locale,
        "languageGroupKey": group,
        "status": status,
        "slug": slug,
        "title": title,
        "entityId": saved_id,
        "result": res,
        "message": f"已写入 {collection} · {locale} · status={status} · slug={slug}",
    }


def entity_delete(client: CmsClient, site_key: str, args: dict[str, Any]) -> dict[str, Any]:
    collection = resolve_collection_slug(client, args, site_key)
    entity_id = args.get("id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("需要 id")
    entity_id = entity_id.strip()
    client.delete_entity(collection, entity_id)
    return {
        "ok": True,
        "siteKey": site_key,
        "collection": collection,
        "id": entity_id,
        "message": f"已删除 {collection}/{entity_id}",
    }


def revalidate(client: CmsClient, site_key: str, args: dict[str, Any]) -> dict[str, Any]:
    paths = args.get("paths") if isinstance(args.get("paths"), list) else []
    sites = client.get_frontend_sites()
    site_list = sites if isinstance(sites, list) else []
    if isinstance(sites, dict):
        for key in ("sites", "list", "items", "data"):
            if isinstance(sites.get(key), list):
                site_list = sites[key]
                break

    revalidate_url = ""
    secret = ""
    origin = ""
    for s in site_list:
        if not isinstance(s, dict):
            continue
        if s.get("siteKey") != site_key:
            continue
        revalidate_url = str(s.get("revalidateUrl") or "")
        secret = str(s.get("revalidateSecret") or "")
        origin = str(s.get("origin") or "")
        break

    if not revalidate_url and origin:
        revalidate_url = f"{origin.rstrip('/')}/api/revalidate"
    if not revalidate_url or not secret:
        return {
            "skipped": True,
            "siteKey": site_key,
            "reason": "缺少 revalidateUrl/secret，无法刷新前端缓存",
        }

    body = json.dumps(
        {"secret": secret, "siteKey": site_key, "paths": paths},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        revalidate_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            text = res.read().decode("utf-8", errors="replace")
            status = res.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"revalidate HTTP {e.code}: {text}") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"revalidate 失败: {e}") from None

    if not (200 <= status < 300):
        raise RuntimeError(f"revalidate HTTP {status}: {text}")
    return {
        "siteKey": site_key,
        "httpStatus": status,
        "body": text[:500],
    }
