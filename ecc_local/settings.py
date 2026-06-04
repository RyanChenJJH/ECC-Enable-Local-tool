"""记住上次用的 ECC 路径 / 项目路径等，存到用户本地目录。"""
from __future__ import annotations

import json
import os
from pathlib import Path

_APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ECC-Enable-Local-tool"
_FILE = _APP_DIR / "settings.json"


def load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: dict) -> None:
    try:
        _APP_DIR.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def log_file() -> str:
    """统一的操作日志文件路径。"""
    return str(_APP_DIR / "logs" / "operations.log")
