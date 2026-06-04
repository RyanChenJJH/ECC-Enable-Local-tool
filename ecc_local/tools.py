"""可执行文件定位（解决"双击 exe 找不到 pwsh / npm"的问题）。

双击 exe 时进程只继承 Explorer 的 PATH，可能不含 node 目录，也不含 pwsh 的
WindowsApps 别名目录；而且 npm 是 .cmd，subprocess 不经 shell 无法直接执行。
本模块：
  1) 启动时把注册表里的持久 PATH(机器+用户) 合并进 os.environ['PATH']；
  2) 补充 pwsh 常见安装位置；
  3) find() 用 PATHEXT 解析(能找到 npm.cmd)，runner() 对 .cmd/.bat 用 `cmd /c` 包裹。
"""
from __future__ import annotations

import glob
import os
import shutil
from functools import lru_cache
from typing import List, Optional


def _registry_paths() -> List[str]:
    out: List[str] = []
    if os.name != "nt":
        return out
    try:
        import winreg  # noqa: PLC0415
    except Exception:
        return out
    for root, sub in [
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ]:
        try:
            with winreg.OpenKey(root, sub) as key:
                val, _ = winreg.QueryValueEx(key, "Path")
                out.append(os.path.expandvars(val))
        except Exception:
            pass
    return out


def _augment_path() -> None:
    """把持久 PATH 与 pwsh 常见位置合并进当前进程 PATH（只做一次）。"""
    extra: List[str] = []
    for chunk in _registry_paths():
        extra += chunk.split(os.pathsep)
    # pwsh 7（MSI 安装位置）+（Store 安装的真实二进制目录）+ 执行别名目录
    extra.append(r"C:\Program Files\PowerShell\7")
    extra += glob.glob(r"C:\Program Files\WindowsApps\Microsoft.PowerShell_*_x64__8wekyb3d8bbwe")
    extra.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps"))

    cur = os.environ.get("PATH", "")
    merged = [p for p in cur.split(os.pathsep) if p]
    seen = {os.path.normcase(p) for p in merged}
    for e in extra:
        for part in e.split(os.pathsep):
            part = part.strip().strip('"')
            if part and os.path.normcase(part) not in seen:
                merged.append(part)
                seen.add(os.path.normcase(part))
    os.environ["PATH"] = os.pathsep.join(merged)


_augment_path()


@lru_cache(maxsize=None)
def find(name: str) -> Optional[str]:
    """返回可执行文件全路径（含 .exe/.cmd/.bat），找不到返回 None。"""
    return shutil.which(name)


def find_pwsh() -> Optional[str]:
    """优先 PowerShell 7(pwsh)，找不到回退 Windows PowerShell 5.1(powershell)。"""
    return find("pwsh") or find("powershell")


def runner(name: str) -> Optional[List[str]]:
    """返回可直接拼参数交给 subprocess 的前缀列表。

    .cmd/.bat 用 `cmd /c` 包裹（否则 subprocess 无法执行）；.exe 直接用全路径。
    找不到返回 None。
    """
    full = find(name)
    if not full:
        return None
    if full.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", full]
    return [full]


def pwsh_runner() -> Optional[List[str]]:
    full = find_pwsh()
    return [full] if full else None
