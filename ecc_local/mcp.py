"""动态 MCP 识别与裁剪。

不再硬编码服务器清单：从 config.toml 里**实际存在**的 [mcp_servers.*] 动态枚举；
对已知服务器按"是否需要 key"给建议，未知(上游新增)默认保留并标注，绝不静默丢。
裁剪用 tomlkit，保留注释与格式。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import tomlkit

# 已知服务器的判定规则：keyless=无需 key；env=需要其中任一环境变量；heavy=较重(默认不留)。
KNOWN: Dict[str, dict] = {
    "sequential-thinking": {"keyless": True},
    "memory": {"keyless": True},
    "context7": {"keyless": True},  # 可无 key 运行
    "github": {"env": ["GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"]},
    "exa": {"env": ["EXA_API_KEY"]},
    "playwright": {"heavy": True},  # 无 key 但走浏览器扩展，较重
}


def _load(config_path: str | Path) -> tomlkit.TOMLDocument:
    return tomlkit.parse(Path(config_path).read_text(encoding="utf-8"))


def discover_servers(config_path: str | Path) -> List[str]:
    """返回 config.toml 中真实存在的 mcp server 名(动态)。"""
    try:
        doc = _load(config_path)
    except Exception:
        return []
    servers = doc.get("mcp_servers")
    if not servers:
        return []
    return list(servers.keys())


def suggest(name: str, keep_playwright: bool = False) -> Tuple[bool, str]:
    """对单个 server 给出 (是否保留, 原因)。未知 server 默认保留并标注。"""
    info = KNOWN.get(name)
    if info is None:
        return True, "未知 server(可能是 ECC 新增)，默认保留"
    if info.get("keyless"):
        return True, "无需 API key，保留"
    if info.get("heavy"):
        if keep_playwright:
            return True, "较重(浏览器扩展)，按设置保留"
        return False, "较重(浏览器扩展)，默认移除"
    envs = info.get("env", [])
    for e in envs:
        if os.environ.get(e):
            return True, f"检测到环境变量 {e}，保留"
    return False, f"未检测到 {'/'.join(envs)}，移除"


def auto_plan(config_path: str | Path, keep_playwright: bool = False) -> List[Tuple[str, bool, str]]:
    """对发现的所有 server 给出建议：[(name, keep, reason), ...]"""
    return [(n, *suggest(n, keep_playwright)) for n in discover_servers(config_path)]


def trim_config(config_path: str | Path, keep_servers: List[str],
                remove_notify_on_windows: bool = True) -> Tuple[List[str], List[str], bool]:
    """按 keep_servers 裁剪 mcp_servers；Windows 下移除 macOS 专用的 notify。

    用 tomlkit 编辑并原子写回。返回 (kept, removed, notify_removed)。
    """
    path = Path(config_path)
    doc = _load(path)
    kept: List[str] = []
    removed: List[str] = []

    servers = doc.get("mcp_servers")
    if servers:
        for name in list(servers.keys()):
            if name in keep_servers:
                kept.append(name)
            else:
                del servers[name]
                removed.append(name)

    notify_removed = False
    if remove_notify_on_windows and os.name == "nt" and "notify" in doc:
        del doc["notify"]
        notify_removed = True

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
    os.replace(tmp, path)
    return kept, removed, notify_removed
