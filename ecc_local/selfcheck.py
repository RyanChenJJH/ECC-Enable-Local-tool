"""Self-Check 体检：校验 ECC 接口、依赖、版本、以及"全局禁用"不变式。

把"会随上游变化"的契约点都检查一遍，上游若大改结构能第一时间发现并精确报出。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .eccrepo import EccRepo
from .log import Logger

Result = Tuple[str, str, str]  # (name, status, detail)  status ∈ PASS/WARN/FAIL


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def run(ecc: EccRepo, project: Optional[str] = None, profile: Optional[str] = None,
        logger: Optional[Logger] = None) -> List[Result]:
    results: List[Result] = []

    def add(name: str, status: str, detail: str) -> None:
        results.append((name, status, detail))

    # ECC 接口
    add("ECC 路径", "PASS" if ecc.path.exists() else "FAIL", str(ecc.path))
    add("install.ps1", "PASS" if ecc.install_ps1.exists() else "FAIL", str(ecc.install_ps1))
    add(".codex/config.toml", "PASS" if ecc.codex_config.exists() else "WARN", str(ecc.codex_config))
    add("AGENTS.md", "PASS" if ecc.agents_md.exists() else "WARN", str(ecc.agents_md))
    add("rules/", "PASS" if ecc.rules_dir.exists() else "WARN", str(ecc.rules_dir))
    add("manifests/profiles", "PASS" if ecc.profiles_manifest.exists() else "WARN",
        str(ecc.profiles_manifest))

    profs = ecc.profiles()
    add("可用 profile", "PASS", ", ".join(profs))
    if profile:
        ok = profile in profs
        add(f"profile '{profile}'", "PASS" if ok else "WARN",
            "存在" if ok else "清单里没有此 profile(上游可能改名)")

    # 依赖
    add("依赖 pwsh", "PASS" if _which("pwsh") else "FAIL", _which("pwsh") or "未找到(Claude 启用需要)")
    add("依赖 node", "PASS" if _which("node") else "FAIL", _which("node") or "未找到(Claude 安装器需要)")
    add("依赖 git", "PASS" if _which("git") else "WARN", _which("git") or "未找到(更新 ECC 需要)")

    # 版本
    add("ECC 版本", "PASS", ecc.version() or ecc.git_info() or "未知")

    # 全局禁用不变式
    home = Path.home()
    cs = home / ".claude" / "settings.json"
    if cs.exists():
        try:
            compact = cs.read_text(encoding="utf-8", errors="replace").replace(" ", "")
        except Exception:
            compact = ""
        bad = '"ecc@ecc":true' in compact
        add("全局 Claude 未启用 ecc 插件", "WARN" if bad else "PASS",
            "settings.json 含 ecc@ecc:true(全局被启用了)" if bad else "干净")
    else:
        add("全局 Claude settings", "PASS", "无 settings.json")

    cc = home / ".codex" / "config.toml"
    if cc.exists():
        try:
            txt = cc.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            txt = ""
        has = "ecc" in txt
        add("全局 Codex 不含 ecc", "WARN" if has else "PASS",
            "config.toml 提及 ecc(确认是否被全局装过)" if has else "干净")
    else:
        add("全局 Codex config", "PASS", "无 config.toml")

    # 项目状态
    if project:
        man = Path(project) / ".ecc-local.json"
        add("项目 ECC 状态", "PASS" if man.exists() else "WARN",
            "已启用(有清单)" if man.exists() else "未启用")

    if logger:
        for name, status, detail in results:
            fn = logger.ok if status == "PASS" else (logger.warn if status == "WARN" else logger.err)
            fn(f"[{status}] {name}: {detail}")

    return results
