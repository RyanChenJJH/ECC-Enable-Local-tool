"""ECC 仓库模型：定位关键路径、动态读取 profile / rules、读版本。

所有"会随上游变化"的东西都在运行时读取(不硬编码)，所以 ECC 内容更新后工具自动适配。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def tool_root() -> Path:
    """工具自身所在目录(源码运行=仓库根；打包后=exe 所在目录)。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_ecc_repo() -> Path:
    """默认猜测：工具目录的同级 ECC 文件夹(E:\\...\\tool\\ECC\\ECC)。"""
    guess = tool_root().parent / "ECC"
    return guess


class EccRepo:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        try:
            self.path = self.path.resolve()
        except Exception:
            pass

    # ---- 关键路径 ----
    @property
    def install_ps1(self) -> Path: return self.path / "install.ps1"

    @property
    def codex_dir(self) -> Path: return self.path / ".codex"

    @property
    def codex_config(self) -> Path: return self.codex_dir / "config.toml"

    @property
    def agents_md(self) -> Path: return self.path / "AGENTS.md"

    @property
    def rules_dir(self) -> Path: return self.path / "rules"

    @property
    def profiles_manifest(self) -> Path: return self.path / "manifests" / "install-profiles.json"

    # ---- 校验 / 动态读取 ----
    def is_valid(self) -> bool:
        return self.install_ps1.exists() and self.rules_dir.exists()

    def profiles(self) -> List[str]:
        """从 manifests/install-profiles.json 动态读取 profile 名(不硬编码)。"""
        try:
            data = json.loads(self.profiles_manifest.read_text(encoding="utf-8"))
            node = data.get("profiles", data) if isinstance(data, dict) else data
            if isinstance(node, dict):
                return list(node.keys())
            if isinstance(node, list):
                return [p.get("name") for p in node if isinstance(p, dict) and p.get("name")]
        except Exception:
            pass
        return ["minimal", "core", "full"]

    def rule_sets(self) -> List[str]:
        if not self.rules_dir.exists():
            return []
        return sorted(p.name for p in self.rules_dir.iterdir() if p.is_dir())

    def version(self) -> Optional[str]:
        vf = self.path / "VERSION"
        if vf.exists():
            try:
                return vf.read_text(encoding="utf-8").strip()
            except Exception:
                return None
        return None

    def git_info(self) -> Optional[str]:
        from . import tools  # 延迟导入，避免循环
        git = tools.runner("git")
        if not git:
            return None
        try:
            out = subprocess.run(
                git + ["-C", str(self.path), "describe", "--tags", "--always", "--dirty"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:
            pass
        return None
