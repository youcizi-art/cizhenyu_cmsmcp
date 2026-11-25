"""站点集合建模、字段合规约束与 FrontendSite 注册工具。"""

from __future__ import annotations

import re
import secrets
import string
from typing import Any

from cms_api import CmsClient
from tools_resolve import site_key_from

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")

SYSTEM_FIELD_NAMES = frozenset(
    {
        "id",
        "locale",
        "language_group_key",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }
)

ALLOWED_FIELD_TYPES = frozenset(
    {
        "text",
        "textarea",
        "number",
        "select",
        "multi_select",
        "boolean",
        "date",
        "image",
        "file",
        "richtext",
        "json",
        "relation",
        "relation_multi",
        "reference",
    }
)


def _validate_slug(slug: str, label: str) -> str:
    s = (slug or "").strip().lower().replace("-", "_")
    if not SLUG_RE.match(s):
        raise ValueError(f"{label} slug 不合法（仅允许小写字母开头及小写字母/数字/下划线）：{slug!r}")
    return s


def _validate_model_fields(model_slug: str, fields: list[Any], is_submit_only: bool = False) -> list[dict[str, Any]]:
    """按 cizhenyu_payload 三层字段规则校验模型图纸，防止非法字段写入后台。"""
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise ValueError(f"[{model_slug}] 第 {idx + 1} 个字段必须是对象")
        fname = str(raw.get("name") or raw.get("key") or "").strip()
        ftype = str(raw.get("type") or "text").strip()
        if not fname or not SLUG_RE.match(fname):
            raise ValueError(f"[{model_slug}] 字段名不合法：{fname!r}")
        if fname in SYSTEM_FIELD_NAMES:
            raise ValueError(
                f"[{model_slug}] 字段 {fname!r} 属于系统内核表列保留字，禁止写入模型 fields"
            )
        if fname in seen:
            raise ValueError(f"[{model_slug}] 字段名重复：{fname!r}")
        if ftype not in ALLOWED_FIELD_TYPES:
            raise ValueError(
                f"[{model_slug}] 字段 {fname!r} 类型 {ftype!r} 不受支持；合法类型：{sorted(ALLOWED_FIELD_TYPES)}"
            )
        # 行为保留字段契约保护：status 与 sort_order 不可被篡改契约
        if fname == "status":
            if is_submit_only:
                raise ValueError(f"[{model_slug}] 表单提交类模型禁止添加 status 可见性保留字段")
            normalized = {
                "name": "status",
                "label": "发布状态",
                "type": "select",
                "options": ["draft", "published"],
                "defaultValue": "published",
                "isListDisplay": True,
            }
            validated.append(normalized)
            seen.add(fname)
            continue
        if fname == "sort_order":
            normalized = {
                "name": "sort_order",
                "label": "排序",
                "type": "number",
                "defaultValue": 0,
                "isListDisplay": True,
            }
            validated.append(normalized)
            seen.add(fname)
            continue

        item = dict(raw)
        item["name"] = fname
        item["type"] = ftype
        if not item.get("label"):
            item["label"] = fname
        validated.append(item)
        seen.add(fname)
    return validated


def _public_read_policy() -> dict[str, Any]:
    return {
        "enabled": True,
        "public": True,
        "allowList": True,
        "allowDetail": True,
        "allowSubmit": False,
        "read": "public",
        "list": "public",
        "submit": "disabled",
    }


def _submit_only_policy(allowed_origins: list[str] | None = None) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "enabled": True,
        "public": False,
        "allowList": False,
        "allowDetail": False,
        "allowSubmit": True,
        "read": "disabled",
        "list": "disabled",
        "submit": "public",
    }
    if allowed_origins:
        policy["corsOrigins"] = allowed_origins
    return policy


def nav_group_ensure(client: CmsClient, args: dict[str, Any], default_site: str) -> dict[str, Any]:
    """幂等创建站点导航分组路径（如 acme/content、acme/products）。"""
    site_key = _validate_slug(site_key_from(args, default_site), "siteKey")
    raw_paths = args.get("paths")
    if isinstance(raw_paths, list) and raw_paths:
        paths = [str(p).strip().strip("/") for p in raw_paths if str(p).strip()]
    else:
        single = str(args.get("path") or "").strip().strip("/")
        paths = (
            [single]
            if single
            else [
                f"{site_key}/content",
                f"{site_key}/products",
                f"{site_key}/business",
                f"{site_key}/settings",
            ]
        )

    existing = client.list_nav_groups()
    created: list[dict[str, Any]] = []

    for path in paths:
        segments = [_validate_slug(seg, "分组") for seg in path.split("/") if seg.strip()]
        if segments and segments[0] != site_key:
            segments.insert(0, site_key)
        parent_id: str | None = None
        for seg in segments:
            hit = next(
                (
                    g
                    for g in existing
                    if isinstance(g, dict)
                    and g.get("slug") == seg
                    and (g.get("parent_id") or g.get("parentId") or None) == parent_id
                ),
                None,
            )
            if hit:
                parent_id = str(hit.get("id"))
                continue
            res = client.create_nav_group(
                {
                    "name": seg.upper() if parent_id is None else seg,
                    "slug": seg,
                    "parentId": parent_id,
                    "icon": "FolderOutlined",
                }
            )
            new_id = str(res.get("id") or "") if isinstance(res, dict) else ""
            if not new_id:
                raise RuntimeError(f"创建导航分组 {seg} 未返回 id: {res}")
            node = {"id": new_id, "slug": seg, "parent_id": parent_id, "name": seg}
            existing.append(node)
            created.append(node)
            parent_id = new_id

    return {
        "ok": True,
        "siteKey": site_key,
        "ensuredPaths": paths,
        "createdCount": len(created),
        "created": created,
    }


def models_ensure(client: CmsClient, args: dict[str, Any], default_site: str) -> dict[str, Any]:
    """只增不改地导入缺失模型：线上已存在同名 slug 时一律跳过，严禁覆写多站点共用模型。"""
    raw_models = args.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("需要非空数组 models")

    site_key = ""
    try:
        site_key = _validate_slug(site_key_from(args, default_site), "siteKey")
    except Exception:
        site_key = ""

    existing_models = client.list_models()
    existing_slugs = {
        str(m.get("slug")).strip()
        for m in existing_models
        if isinstance(m, dict) and m.get("slug")
    }

    to_create: list[dict[str, Any]] = []
    skipped_existing: list[str] = []

    for row in raw_models:
        if not isinstance(row, dict):
            raise ValueError("models 数组元素必须是对象")
        slug = _validate_slug(str(row.get("slug") or ""), "模型")
        if slug in existing_slugs:
            skipped_existing.append(slug)
            continue
        name = str(row.get("name") or slug).strip()
        is_submit = bool(row.get("submitOnly")) or slug.endswith(("inquiry", "message"))
        fields = _validate_model_fields(slug, row.get("fields") or [], is_submit_only=is_submit)
        # 重写关联字段中的 collectionSlug 前缀为当前站点命名空间
        if site_key:
            for f in fields:
                rel = f.get("relationConfig")
                if isinstance(rel, dict) and isinstance(rel.get("collectionSlug"), str):
                    cslug = rel["collectionSlug"].strip()
                    if cslug.startswith("b2b_"):
                        rel["collectionSlug"] = f"{site_key}_{cslug[4:]}"
                    elif not cslug.startswith(f"{site_key}_"):
                        rel["collectionSlug"] = f"{site_key}_{cslug}"

        to_create.append(
            {
                "name": name,
                "slug": slug,
                "description": str(row.get("description") or ""),
                "fields": fields,
            }
        )
        existing_slugs.add(slug)

    import_res = client.batch_import_models(to_create) if to_create else {"created": [], "updated": []}
    return {
        "ok": True,
        "createdCount": len(to_create),
        "createdSlugs": [m["slug"] for m in to_create],
        "skippedExisting": skipped_existing,
        "result": import_res,
        "note": "已存在的全局模型已自动跳过保护，未做任何覆盖修改。",
    }


def collections_ensure(client: CmsClient, args: dict[str, Any], default_site: str) -> dict[str, Any]:
    """幂等实例化 {siteKey}_{logical} 集合并自动配置公开 API 策略（公开只读 vs 表单仅 submit）。"""
    site_key = _validate_slug(site_key_from(args, default_site), "siteKey")
    raw_cols = args.get("collections")
    if not isinstance(raw_cols, list) or not raw_cols:
        raise ValueError("需要非空数组 collections")

    cors_origins = [
        str(x).strip()
        for x in (args.get("corsOrigins") or [])
        if isinstance(x, str) and str(x).strip()
    ]

    normalized_cols: list[dict[str, Any]] = []
    policy_modes: dict[str, str] = {}

    for row in raw_cols:
        if not isinstance(row, dict):
            raise ValueError("collections 数组元素必须是对象")
        logical_raw = str(row.get("logical") or row.get("slug") or "").strip().lower().replace("-", "_")
        if logical_raw.startswith(f"{site_key}_"):
            slug = _validate_slug(logical_raw, "集合")
            logical = slug[len(site_key) + 1 :]
        elif logical_raw.startswith("b2b_"):
            logical = logical_raw[4:]
            slug = _validate_slug(f"{site_key}_{logical}", "集合")
        else:
            logical = logical_raw
            slug = _validate_slug(f"{site_key}_{logical}", "集合")

        model_slug = _validate_slug(str(row.get("modelSlug") or logical), "关联模型")
        raw_group = str(row.get("groupPath") or f"{site_key}/content").strip().strip("/")
        if raw_group.startswith("b2b/"):
            group_path = f"{site_key}/{raw_group[4:]}"
        elif not raw_group.startswith(f"{site_key}/") and raw_group != site_key:
            group_path = f"{site_key}/{raw_group}"
        else:
            group_path = raw_group

        mode = str(row.get("apiMode") or "").strip().lower()
        if not mode:
            if logical in ("inquiry", "online_message") or logical.endswith(("_inquiry", "_message")):
                mode = "submit_only"
            elif logical in ("entity", "taxonomy", "translation_fields", "product_spec_template"):
                mode = "private"
            else:
                mode = "public_read"
        policy_modes[slug] = mode

        presentation = str(row.get("presentationMode") or ("single_form" if logical == "company_info" else "list"))
        normalized_cols.append(
            {
                "name": str(row.get("name") or logical),
                "slug": slug,
                "modelSlug": model_slug,
                "groupPath": group_path,
                "description": str(row.get("description") or ""),
                "icon": str(row.get("icon") or "DatabaseOutlined"),
                "presentationMode": presentation,
            }
        )

    import_res = client.batch_import_collections(normalized_cols)

    # 为本次涉及的集合写入安全的默认 API 策略（skipExistingPolicy 默认为 True，不覆盖已配好的线上策略）
    skip_existing_policy = args.get("skipExistingPolicy", True) is not False
    all_cols = client.list_collections()
    policies_applied: list[str] = []

    for col in all_cols:
        if not isinstance(col, dict):
            continue
        cslug = str(col.get("slug") or "")
        cid = str(col.get("id") or "")
        if cslug not in policy_modes or not cid:
            continue
        mode = policy_modes[cslug]
        if mode == "private":
            continue
        if skip_existing_policy:
            try:
                cur = client.get_api_policy(cid)
                pol = cur.get("policy") if isinstance(cur, dict) else cur
                if isinstance(pol, dict) and any(k in pol for k in ("public", "read", "list", "submit", "allowSubmit")):
                    continue
            except Exception:
                pass
        target_policy = _submit_only_policy(cors_origins) if mode == "submit_only" else _public_read_policy()
        client.put_api_policy(cid, target_policy)
        policies_applied.append(f"{cslug}:{mode}")

    return {
        "ok": True,
        "siteKey": site_key,
        "importResult": import_res,
        "policiesApplied": policies_applied,
    }


def frontend_site_upsert(client: CmsClient, args: dict[str, Any], default_site: str) -> dict[str, Any]:
    """在 CMS「前端站点」中幂等登记或更新站点域名、分组绑定与 /api/revalidate 刷新密钥。"""
    site_key = _validate_slug(site_key_from(args, default_site), "siteKey")
    display_name = str(args.get("displayName") or site_key).strip()
    raw_origin = str(args.get("siteOrigin") or args.get("origin") or "http://127.0.0.1:4321").strip().rstrip("/")
    if raw_origin and not raw_origin.startswith(("http://", "https://")):
        raw_origin = f"https://{raw_origin}"
    revalidate_url = str(args.get("revalidateUrl") or f"{raw_origin}/api/revalidate").strip()
    secret = str(args.get("revalidateSecret") or "").strip()

    raw_sites = client.get_frontend_sites()
    sites_list: list[dict[str, Any]] = []
    if isinstance(raw_sites, list):
        sites_list = [s for s in raw_sites if isinstance(s, dict)]
    elif isinstance(raw_sites, dict):
        for k in ("sites", "list", "data", "items"):
            if isinstance(raw_sites.get(k), list):
                sites_list = [s for s in raw_sites[k] if isinstance(s, dict)]
                break

    # 查找本站根导航分组 ID 以便 CMS 修改内容后精准扇出通知本站 revalidate
    groups = client.list_nav_groups()
    group_ids = [
        str(g.get("id"))
        for g in groups
        if isinstance(g, dict)
        and g.get("slug") == site_key
        and not (g.get("parent_id") or g.get("parentId"))
        and g.get("id")
    ]

    updated = False
    used_secret = secret
    for item in sites_list:
        if item.get("siteKey") == site_key:
            existing_secret = str(item.get("revalidateSecret") or "").strip()
            used_secret = secret or existing_secret or "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
            )
            item["displayName"] = display_name
            item["origin"] = raw_origin
            item["revalidateUrl"] = revalidate_url
            item["revalidateSecret"] = used_secret
            item["enabled"] = True
            if group_ids:
                item["groupIds"] = group_ids
            updated = True
            break

    if not updated:
        if not used_secret:
            used_secret = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        sites_list.append(
            {
                "siteKey": site_key,
                "displayName": display_name,
                "origin": raw_origin,
                "revalidateUrl": revalidate_url,
                "revalidateSecret": used_secret,
                "enabled": True,
                "groupIds": group_ids,
                "sort": len(sites_list),
            }
        )

    client.put_frontend_sites(sites_list)
    return {
        "ok": True,
        "siteKey": site_key,
        "action": "updated" if updated else "created",
        "origin": raw_origin,
        "revalidateUrl": revalidate_url,
        "revalidateSecret": used_secret,
        "groupIds": group_ids,
    }
