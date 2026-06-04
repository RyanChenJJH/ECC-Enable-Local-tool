# Changelog

## v1.1.0 — 2026-06-04
### 新增
- **应用图标**：exe 文件图标 + 窗口标题栏图标（`assets/icon.ico`，由 `assets/make_icon.py` 生成）。
- **README「界面用法」补全**：完整参数说明表，含 Claude `rules` 多选的用法与含义、Codex 档位与 MCP 设置。
### 构建
- `build.ps1` 与 GitHub Actions 增加 `--icon` 与 `--add-data`（打包图标资源）。

## v1.0.0 — 2026-06-04
- 首个版本：tkinter GUI + CLI（共用同一套 core）。
- 动态 MCP 识别（tomlkit）、Self-Check 体检、一键部署/停用、DryRun 预览。
- 安全卸载（`.ecc-local.json` 清单）、一键更新 ECC（git pull + npm install）。
- 旧 PowerShell 脚本归档到 `legacy/`。
