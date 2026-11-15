"""Schema / models / fields / API policy tools."""

from __future__ import annotations

from typing import Any

from cms_api import CmsClient
from tools_resolve import collection_id_of, find_collection, resolve_collection_slug, site_key_from


def models_list(client: CmsClient) -> dict[str, Any]:
    models = client.list_models()
    return {
        "count": len(models),
        "models": models,
        "note": "模型全局共用；各站点通过 {siteKey}_{logical} 集合实例绑定同一模型。",
    }


def model_get(client: CmsClient, args: dict[str, Any]) -> dict[str, Any]:
    key = None
    for k in ("name", "slug", "id"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            key = v.strip()
            break
    if not key:
        raise ValueError("需要 name / slug / id")
    for m in client.list_models():
        if not isinstance(m, dict):
            continue
        if (
            m.get("name") == key
            or m.get("slug") == key
            or m.get("id") == key
            or m.get("_id") == key
        ):
            return {"model": m}
    raise RuntimeError(f"未找到模型「{key}」")


def nav_groups_list(client: CmsClient) -> dict[str, Any]:
    groups = client.list_nav_groups()
    return {"count": len(groups), "navGroups": groups}


def _model_ref_keys(col: dict[str, Any]) -> list[str]:
    """Collect possible model lookup keys from a collection doc."""
    keys: list[str] = []
    for field in ("modelSlug", "modelId", "model"):
        v = col.get(field)
        if isinstance(v, str) and v.strip():
            keys.append(v.strip())
        elif isinstance(v, dict):
            for sub in ("slug", "id", "_id", "name"):
                sv = v.get(sub)
                if isinstance(sv, str) and sv.strip():
                    keys.append(sv.strip())
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _match_model(models: list[Any], key: str) -> dict[str, Any] | None:
    for m in models:
        if not isinstance(m, dict):
            continue
        if (
            m.get("id") == key
            or m.get("_id") == key
            or m.get("slug") == key
            or m.get("name") == key
        ):
            return m
    return None


def collection_inspect(
    client: CmsClient,
    args: dict[str, Any],
    default_site: str,
) -> dict[str, Any]:
    site_key = site_key_from(args, default_site)
    slug = resolve_collection_slug(client, args, site_key)
    col = find_collection(client, slug)
    cid = collection_id_of(col)
    if not cid:
        raise RuntimeError(f"集合 {slug} 缺少 id")

    try:
        fields = client.get_field_settings(cid)
    except Exception:
        fields = None
    try:
        policy = client.get_api_policy(cid)
    except Exception:
        policy = None

    model_summary = None
    refs = _model_ref_keys(col)
    if refs:
        models = client.list_models()
        for ref in refs:
            hit = _match_model(models, ref)
            if hit is not None:
                model_summary = hit
                break

    logical = slug[len(f"{site_key}_") :] if slug.startswith(f"{site_key}_") else slug
    return {
        "siteKey": site_key,
        "logical": logical,
        "collectionSlug": slug,
        "collectionId": cid,
        "collection": col,
        "model": model_summary,
        "fieldSettings": fields,
        "apiPolicy": policy,
    }


def collection_fields(client: CmsClient, args: dict[str, Any], default_site: str) -> dict[str, Any]:
    site_key = site_key_from(args, default_site)
    slug = resolve_collection_slug(client, args, site_key)
    col = find_collection(client, slug)
    cid = collection_id_of(col)
    if not cid:
        raise RuntimeError(f"集合 {slug} 缺少 id")
    return {
        "siteKey": site_key,
        "collectionSlug": slug,
        "collectionId": cid,
        "fieldSettings": client.get_field_settings(cid),
    }


def collection_api_policy(
    client: CmsClient, args: dict[str, Any], default_site: str
) -> dict[str, Any]:
    site_key = site_key_from(args, default_site)
    slug = resolve_collection_slug(client, args, site_key)
    col = find_collection(client, slug)
    cid = collection_id_of(col)
    if not cid:
        raise RuntimeError(f"集合 {slug} 缺少 id")
    return {
        "siteKey": site_key,
        "collectionSlug": slug,
        "collectionId": cid,
        "apiPolicy": client.get_api_policy(cid),
    }


def collection_fields_put(
    client: CmsClient, args: dict[str, Any], default_site: str
) -> dict[str, Any]:
    site_key = site_key_from(args, default_site)
    slug = resolve_collection_slug(client, args, site_key)
    col = find_collection(client, slug)
    cid = collection_id_of(col)
    if not cid:
        raise RuntimeError(f"集合 {slug} 缺少 id")
    settings = args.get("settings") or args.get("fieldSettings")
    if settings is None:
        raise ValueError("需要 settings（字段设置对象）")
    res = client.put_field_settings(cid, settings)
    return {
        "ok": True,
        "siteKey": site_key,
        "collectionSlug": slug,
        "collectionId": cid,
        "result": res,
    }


def collection_api_policy_put(
    client: CmsClient, args: dict[str, Any], default_site: str
) -> dict[str, Any]:
    site_key = site_key_from(args, default_site)
    slug = resolve_collection_slug(client, args, site_key)
    col = find_collection(client, slug)
    cid = collection_id_of(col)
    if not cid:
        raise RuntimeError(f"集合 {slug} 缺少 id")
    policy = args.get("policy") or args.get("apiPolicy")
    if policy is None:
        raise ValueError("需要 policy（API 策略对象）")
    res = client.put_api_policy(cid, policy)
    return {
        "ok": True,
        "siteKey": site_key,
        "collectionSlug": slug,
        "collectionId": cid,
        "result": res,
    }
