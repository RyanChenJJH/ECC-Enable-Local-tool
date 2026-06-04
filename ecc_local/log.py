"""极简日志器：把消息发给一个 sink(GUI 文本框/控制台)，并可选写入日志文件。"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable, Optional


class Logger:
    def __init__(self, sink: Optional[Callable[[str, str], None]] = None,
                 logfile: Optional[str] = None):
        # sink(level, message)
        self.sink = sink or (lambda level, msg: print(f"[{level}] {msg}"))
        self.logfile = Path(logfile) if logfile else None

    def _emit(self, level: str, msg: str) -> None:
        try:
            self.sink(level, msg)
        except Exception:
            pass
        if self.logfile:
            try:
                self.logfile.parent.mkdir(parents=True, exist_ok=True)
                with self.logfile.open("a", encoding="utf-8") as f:
                    ts = datetime.datetime.now().isoformat(timespec="seconds")
                    f.write(f"{ts} [{level}] {msg}\n")
            except Exception:
                pass

    def info(self, m: str) -> None: self._emit("INFO", m)
    def ok(self, m: str) -> None: self._emit("OK", m)
    def warn(self, m: str) -> None: self._emit("WARN", m)
    def err(self, m: str) -> None: self._emit("ERR", m)
