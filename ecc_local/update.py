"""一键更新 ECC：git pull + npm install，并对比版本与 MCP 变化。

ECC 的"内容更新"(agents/skills/rules/MCP/profile)是数据，工具运行时动态读取，
所以 pull 后无需改工具即自动适配；这里再给出变更摘要，提示随后跑一次 Self-Check。
"""
from __future__ import annotations

from typing import Optional

from . import mcp
from .eccrepo import EccRepo
from .log import Logger
from .proc import run_stream


def _servers(ecc: EccRepo):
    try:
        if ecc.codex_config.exists():
            return set(mcp.discover_servers(ecc.codex_config))
    except Exception:
        pass
    return set()


def update_ecc(ecc: EccRepo, logger: Optional[Logger] = None) -> bool:
    logger = logger or Logger()
    repo = str(ecc.path)
    if not (ecc.path / ".git").exists():
        logger.err(f"{repo} 不是 git 仓库，无法 pull。")
        return False

    before_ver = ecc.version() or ecc.git_info()
    before_servers = _servers(ecc)
    before_profiles = set(ecc.profiles())

    logger.info("git pull --ff-only ...")
    code = run_stream(["git", "-C", repo, "pull", "--ff-only"], cwd=None, logger=logger)
    if code != 0:
        logger.err("git pull 失败（可能有本地改动或网络问题）。请手动检查仓库状态。")
        return False

    logger.info("npm install ...")
    run_stream(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"],
               cwd=repo, logger=logger)

    after_ver = ecc.version() or ecc.git_info()
    after_servers = _servers(ecc)
    after_profiles = set(ecc.profiles())

    logger.ok(f"版本：{before_ver} → {after_ver}")
    new_srv = sorted(after_servers - before_servers)
    gone_srv = sorted(before_servers - after_servers)
    new_prof = sorted(after_profiles - before_profiles)
    gone_prof = sorted(before_profiles - after_profiles)
    if new_srv:
        logger.warn("新增 MCP server：" + ", ".join(new_srv) + "（部署时会自动出现在 MCP 列表）")
    if gone_srv:
        logger.warn("移除 MCP server：" + ", ".join(gone_srv))
    if new_prof:
        logger.warn("新增 profile：" + ", ".join(new_prof))
    if gone_prof:
        logger.warn("移除 profile：" + ", ".join(gone_prof))
    if not (new_srv or gone_srv or new_prof or gone_prof):
        logger.info("MCP / profile 无结构性变化。")

    logger.ok("ECC 已更新。建议随后跑一次 Self-Check 确认接口完好。")
    return True
