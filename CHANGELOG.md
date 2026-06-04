# Changelog

## v1.2.0 — 2026-06-04
### 修复（重要）
- **双击 exe 时找不到 `pwsh` / `npm` 导致 Claude 静默半装**：新增可执行文件定位（`ecc_local/tools.py`）——
  启动时合并注册表持久 PATH(机器+用户) 与 pwsh 常见位置；用 PATHEXT 解析（能找到 `npm.cmd`）；
  `.cmd/.bat` 自动用 `cmd /c` 包裹；`pwsh` 找不到回退 `powershell`。
- Claude 安装、ECC 更新（git/npm）、`git_info` 全部改用解析后的全路径。
### 改进
- Self-Check 新增 `npm` 检查，并显示各依赖的**真实解析路径**（反映 exe 实际能否找到）。

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
