# Cizhenyu CMS MCP

运营插件：通过本机已登录的 CMS 会话调用 CMS API（权限跟随账号）。

## 运行

Deploy 工具箱安装后，由 `mcp_launcher.py` 启动旁路二进制 `cizhenyu-cms-mcp`：

- `CMS_ORIGIN`：CMS 管理地址（Deploy 从登录态注入）
- `CMS_SITE_KEY`：可选，默认 `default`（具体站点由 Agent 在工具参数中指定/按权限操作）
- `CIZHENYU_CMS_MCP_BIN`：可选，旁路二进制绝对路径

## 源码仓库

https://github.com/youcizi-art/cizhenyu_cmsmcp
