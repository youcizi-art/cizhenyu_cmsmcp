"""Multi-site collection resolution: shared models + {siteKey}_{logical} instances."""

from __future__ import annotations

from typing import Any

from cms_api import CmsClient


def site_key_from(args: dict[str, Any], default: str) -> str:
    for key in ("site", "siteKey"):
        v = args.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return (default or "default").strip().lower() or "default"


def resolve_collection_slug(client: CmsClient, args: dict[str, Any], site_key: str) -> str:
    ns = (site_key or "").strip().lower()
    if not ns:
        raise ValueError("需要 siteKey（多站点共用模型时，用 siteKey 定位集合实例）")

    c = args.get("collection")
    if isinstance(c, str) and c.strip():
        c = c.strip()
        if "_" not in c and "/" not in c:
            return f"{ns}_{c}"
        return c

    logical = args.get("logical") or args.get("model")
    if isinstance(logical, str) and logical.strip():
        logical = logical.strip()
        prefix = f"{ns}_"
        if logical.startswith(prefix):
            logical = logical[len(prefix) :]
        return f"{ns}_{logical}"

    return resolve_article_collection(client, ns)


def resolve_article_collection(client: CmsClient, site_key: str) -> str:
    preferred = f"{site_key}_article"
    cols = client.list_collections()
    slugs = [
        str(c.get("slug"))
        for c in cols
        if isinstance(c, dict) and isinstance(c.get("slug"), str)
    ]
    if preferred in slugs:
        return preferred
    for s in slugs:
        if s.startswith(f"{site_key}_") and "article" in s.lower():
            return s
    raise RuntimeError(
        f"未找到集合「{preferred}」。请传 collection（完整 slug）或 logical（如 article / product），"
        f"并确保已为站点 {site_key} 导入集合实例。"
    )


def collection_id_of(col: dict[str, Any]) -> str | None:
    for key in ("id", "_id"):
        v = col.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def find_collection(client: CmsClient, slug: str) -> dict[str, Any]:
    for c in client.list_collections():
        if isinstance(c, dict) and c.get("slug") == slug:
            return c
    raise RuntimeError(f"未找到集合 slug={slug}")
