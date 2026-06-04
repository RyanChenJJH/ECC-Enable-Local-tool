"""子进程封装：逐行把外部命令(pwsh / node / git / npm)的输出转发到 logger。"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Sequence

from .log import Logger


def run_stream(cmd: Sequence[str], cwd: Optional[str], logger: Logger) -> int:
    """运行命令并把 stdout/stderr 实时转发到 logger。返回退出码。"""
    logger.info("$ " + " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.Popen(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        logger.err(f"找不到命令：{cmd[0]}（请确认它在 PATH 中）")
        return 127
    except Exception as exc:  # noqa: BLE001
        logger.err(f"启动失败：{exc}")
        return 1

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        if line:
            logger.info("  " + line)
    proc.wait()
    return proc.returncode
