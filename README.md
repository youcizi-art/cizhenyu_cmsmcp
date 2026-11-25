# Cizhenyu CMS MCP

运营插件：通过本机已登录的 CMS 会话调用 CMS API（权限跟随账号）。

工具实现与传输协议均在本仓库；Deploy 只负责 CMS 登录、会话落盘、工具箱安装与 Agent 注入。

## 多站点约定

- **模型全局共用**（`cms_models_list`）
- **集合按站点实例化**：`{siteKey}_{logical}`（如 `pet_article`）
- 工具参数传 `siteKey` + `logical`（或完整 `collection` slug）

## 传输

stdio **按行 JSON**（newline-delimited JSON-RPC），与 Crawl4AI / Stagehand / 官方 MCP SDK 一致。

## 工具一览

| 工具 | 作用 |
|------|------|
| `cms_whoami` | 登录探测 |
| `cms_sites_list` | 全部前端站点 |
| `cms_models_list` / `cms_model_get` | 共用模型 |
| `cms_nav_groups_list` | 导航分组 |
| `cms_collections_list` | 集合（`allSites=true` 看全站） |
| `cms_collection_inspect` | 集合 + 关联模型（`modelSlug`/`modelId`）+ 字段 + API 策略 |
| `cms_collection_fields` / `_put` | 字段元数据读写 |
| `cms_collection_api_policy` / `_put` | API 策略读写 |
| `cms_entities_list` / `cms_entity_get` / `cms_entity_save` / `cms_entity_delete` | 实体 CRUD |
| `cms_content_draft` / `cms_content_publish` | 文章类便捷写入 |
| `cms_revalidate` | 前端缓存刷新 |
| `cms_nav_group_ensure` | 幂等创建 `{siteKey}/*` 导航分组 |
| `cms_models_ensure` | 三层字段合规校验并只增不改导入缺失模型 |
| `cms_collections_ensure` | 幂等实例化 `{siteKey}_{logical}` 集合与公开/submit 策略 |
| `cms_frontend_site_upsert` | 注册或更新 CMS 前端站点及 revalidate 密钥 |
| `cms_tech_*` / `crawl_fetch` | 站点技术探测 |

写操作需 `confirm=true`。

## 运行

Deploy 工具箱安装后，由 `mcp_launcher.py` → `mcp_server.py`：

- `CMS_ORIGIN` / `CIZHENYU_CMS_ORIGIN`：提示用；真实鉴权读 Deploy 活跃登录
- `CIZHENYU_CMS_SESSION_DIR`：可选，默认 `%LOCALAPPDATA%/cizhenyu-deploy/auth/cms`
- `CMS_SITE_KEY`：可选默认站点

本地冒烟：

```text
python mcp_server.py
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}
```

## 源码仓库

https://github.com/youcizi-art/cizhenyu_cmsmcp
