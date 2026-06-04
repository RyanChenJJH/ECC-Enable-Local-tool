"""CLI 入口。例：py -3.12 ecc_local_cli.py selfcheck --project D:\\proj"""
import sys

# 让中文在 pwsh 7(默认 UTF-8)下正确显示
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ecc_local.cli import main

if __name__ == "__main__":
    sys.exit(main())
