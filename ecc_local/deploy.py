"""按项目启用/停用 ECC 的核心编排。

- Claude：调用 ECC 自带 install.ps1 --target claude-project，再复制 rules。
- Codex ：档位①只放 AGENTS.md；档位②复制 .codex/ 并用 tomlkit 动态裁剪 MCP。
- 安全：部署前对"已存在且非本工具创建"的目录做备份；用 .ecc-local.json 清单实现精确卸载。
"""
from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import List, Optional

from . import mcp
from .eccrepo import EccRepo
from .log import Logger
from .proc import run_stream

MANIFEST = ".ecc-local.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def read_manifest(project: str | Path) -> Optional[dict]:
    p = Path(project) / MANIFEST
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_manifest(project: str | Path, data: dict) -> None:
    (Path(project) / MANIFEST).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _ours(exists_now: bool, prev_flag) -> bool:
    """该路径是否"由本工具创建"(供卸载时安全删除)。"""
    if not exists_now:
        return True
    return bool(prev_flag)


def _backup(path: Path, project: Path, logger: Logger) -> Optional[str]:
    if not path.exists():
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = project / ".ecc-backup" / ts
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if path.is_dir():
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest)
    logger.warn(f"已备份已存在的 {path.name} → {dest}")
    return str(dest)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


# ---------------- Claude ----------------
def enable_claude(ecc: EccRepo, project: Path, profile: str, rules: List[str],
                  logger: Logger, prev: Optional[dict]) -> dict:
    claude_dir = project / ".claude"
    prev_flag = (prev or {}).get("claude", {}).get("createdByUs") if prev else None
    ours = _ours(claude_dir.exists(), prev_flag)
    if claude_dir.exists() and not ours:
        _backup(claude_dir, project, logger)

    logger.info("启用 Claude：install.ps1 --target claude-project ...")
    code = run_stream(
        ["pwsh", "-NoProfile", "-File", str(ecc.install_ps1),
         "--target", "claude-project", "--profile", profile],
        cwd=str(project), logger=logger,
    )
    if code != 0:
        logger.err(f"install.ps1 退出码 {code}，Claude 安装可能未完成。")

    rules_dest = claude_dir / "rules" / "ecc"
    rules_dest.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for r in rules:
        src = ecc.rules_dir / r
        if src.exists():
            _copy_tree(src, rules_dest / r)
            copied.append(r)
            logger.ok(f"  rules/{r} → .claude/rules/ecc/{r}")
        else:
            logger.warn(f"  rules/{r} 不存在，跳过")
    logger.ok("Claude 启用完成。")
    return {"enabled": True, "profile": profile, "rules": copied, "createdByUs": ours}


# ---------------- Codex ----------------
def enable_codex(ecc: EccRepo, project: Path, full: bool, override: bool,
                 keep_servers: List[str], logger: Logger, prev: Optional[dict]) -> dict:
    prevc = (prev or {}).get("codex", {}) if prev else {}

    if full:
        codex_dst = project / ".codex"
        codex_ours = _ours(codex_dst.exists(), prevc.get("codexCreatedByUs"))
        if codex_dst.exists() and not codex_ours:
            _backup(codex_dst, project, logger)
        codex_dst.mkdir(parents=True, exist_ok=True)
        for item in ecc.codex_dir.iterdir():
            target = codex_dst / item.name
            if item.is_dir():
                _copy_tree(item, target)
            else:
                shutil.copy2(item, target)
        logger.ok("  复制 .codex/ (config.toml + agents + AGENTS.md)")

        cfg = codex_dst / "config.toml"
        kept, removed, notify_removed = mcp.trim_config(cfg, keep_servers)
        logger.ok(f"  config.toml 裁剪 → 保留 {kept}；移除 {removed}")
        if notify_removed:
            logger.ok("  已移除 macOS 专用的 notify")

        agents_file = None
        agents_ours = False
        if override:
            agents_file = "AGENTS.override.md"
            ad = project / agents_file
            agents_ours = _ours(ad.exists(), prevc.get("agentsCreatedByUs"))
            if ad.exists() and not agents_ours:
                _backup(ad, project, logger)
            shutil.copy2(ecc.agents_md, ad)
            logger.ok(f"  指令(override) → {agents_file}")

        rec = {
            "enabled": True, "mode": "full", "override": bool(override),
            "agentsFile": agents_file, "agentsCreatedByUs": agents_ours,
            "codexCreatedByUs": codex_ours,
            "mcpKept": kept, "mcpRemoved": removed,
        }
    else:
        agents_file = "AGENTS.override.md" if override else "AGENTS.md"
        ad = project / agents_file
        agents_ours = _ours(ad.exists(), prevc.get("agentsCreatedByUs"))
        if ad.exists() and not agents_ours:
            _backup(ad, project, logger)
        shutil.copy2(ecc.agents_md, ad)
        logger.ok(f"  指令 → {agents_file}")
        rec = {
            "enabled": True, "mode": "light", "override": bool(override),
            "agentsFile": agents_file, "agentsCreatedByUs": agents_ours,
            "codexCreatedByUs": False, "mcpKept": [], "mcpRemoved": [],
        }

    logger.ok("Codex 启用完成。")
    return rec


# ---------------- 编排 ----------------
def enable(ecc: EccRepo, project: str | Path, harness: str = "both", profile: str = "core",
           rules=("common",), full: bool = False, override: bool = False,
           keep_servers: Optional[List[str]] = None, keep_playwright: bool = False,
           dry_run: bool = False, logger: Optional[Logger] = None) -> Optional[dict]:
    logger = logger or Logger()
    project = Path(project).resolve()
    rules = list(rules)
    do_claude = harness in ("both", "claude")
    do_codex = harness in ("both", "codex")

    if not ecc.is_valid():
        logger.err(f"ECC 路径无效(缺 install.ps1 或 rules/)：{ecc.path}")
        return None
    if project == ecc.path:
        logger.err("目标项目不能是 ECC 仓库本身。")
        return None

    prev = read_manifest(project)

    # 动态 MCP 计划(仅档位②)
    mcp_plan = None
    if do_codex and full:
        mcp_plan = mcp.auto_plan(ecc.codex_config, keep_playwright=keep_playwright)
        if keep_servers is None:
            keep_servers = [n for (n, k, _) in mcp_plan if k]

    logger.info(f"ECC     = {ecc.path}")
    logger.info(f"项目    = {project}")
    logger.info(f"对象    = {harness}（Claude={do_claude}, Codex={do_codex}）")
    if do_claude:
        logger.info(f"Claude  = profile={profile}, rules={rules}")
    if do_codex:
        mode = "档位②(整个 .codex/)" if full else "档位①(仅指令)"
        logger.info(f"Codex   = {mode}, override={override}")
    if mcp_plan is not None:
        logger.info("Codex MCP 计划：")
        for n, k, r in mcp_plan:
            mark = "保留" if (keep_servers and n in keep_servers) else "移除"
            logger.info(f"   [{mark}] {n:<20} {r}")
        logger.info("最终保留：" + ", ".join(keep_servers or []))

    if dry_run:
        logger.warn("DryRun：以上为计划，未写入任何文件。")
        return None

    mclaude = enable_claude(ecc, project, profile, rules, logger, prev) if do_claude else None
    mcodex = enable_codex(ecc, project, full, override, keep_servers or [], logger, prev) if do_codex else None

    manifest = {"tool": "ecc-local", "version": 1, "enabledAt": _now(),
                "eccRepo": str(ecc.path), "harness": harness}
    claude_rec = mclaude if mclaude else (prev or {}).get("claude")
    codex_rec = mcodex if mcodex else (prev or {}).get("codex")
    if claude_rec:
        manifest["claude"] = claude_rec
    if codex_rec:
        manifest["codex"] = codex_rec
    write_manifest(project, manifest)
    logger.ok("清单 .ecc-local.json 已写入。")
    return manifest


def disable(project: str | Path, harness: str = "both", dry_run: bool = False,
            force: bool = False, logger: Optional[Logger] = None) -> None:
    logger = logger or Logger()
    project = Path(project).resolve()
    do_claude = harness in ("both", "claude")
    do_codex = harness in ("both", "codex")
    man = read_manifest(project)

    targets: List[Path] = []
    keep_claude_rec = False
    keep_codex_rec = False

    if not man:
        logger.warn("未找到 .ecc-local.json 清单。")
        if not force:
            logger.warn("保守模式：不确定哪些是本工具创建的，已中止。需要时用 force。")
            return
        if do_claude:
            targets.append(project / ".claude")
        if do_codex:
            targets += [project / ".codex", project / "AGENTS.md", project / "AGENTS.override.md"]
    else:
        if do_claude:
            c = man.get("claude")
            if c and c.get("enabled"):
                if c.get("createdByUs"):
                    targets.append(project / ".claude")
                else:
                    logger.warn(".claude 启用前已存在(非本工具创建)，保留不动。")
        else:
            if man.get("claude"):
                keep_claude_rec = True
        if do_codex:
            c = man.get("codex")
            if c and c.get("enabled"):
                if c.get("mode") == "full" and c.get("codexCreatedByUs"):
                    targets.append(project / ".codex")
                elif c.get("mode") == "full":
                    logger.warn(".codex 启用前已存在(非本工具创建)，保留不动。")
                if c.get("agentsFile") and c.get("agentsCreatedByUs"):
                    targets.append(project / c["agentsFile"])
        else:
            if man.get("codex"):
                keep_codex_rec = True

    targets = [t for t in dict.fromkeys(targets) if t.exists()]
    if not targets:
        logger.warn("没有需要删除的内容。")
    else:
        logger.info("将删除：")
        for t in targets:
            logger.info(f"   {t}")
        if dry_run:
            logger.warn("DryRun：未实际删除。")
            return
        for t in targets:
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            logger.ok(f"已删除 {t}")

    if dry_run:
        return

    if man:
        new: dict = {}
        if keep_claude_rec and man.get("claude"):
            new = {"tool": "ecc-local", "version": 1, "updatedAt": _now(),
                   "eccRepo": man.get("eccRepo"), "harness": "claude", "claude": man["claude"]}
        elif keep_codex_rec and man.get("codex"):
            new = {"tool": "ecc-local", "version": 1, "updatedAt": _now(),
                   "eccRepo": man.get("eccRepo"), "harness": "codex", "codex": man["codex"]}
        mp = project / MANIFEST
        if new:
            write_manifest(project, new)
            logger.ok("清单已更新(保留了未停用一侧的记录)。")
        elif mp.exists():
            mp.unlink()
            logger.ok("清单 .ecc-local.json 已移除。")

    logger.ok("停用完成。全局配置(~/.claude、~/.codex)未受影响。")
