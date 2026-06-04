"""命令行入口(与 GUI 共用 core)。例：
    py -3.12 ecc_local_cli.py on --project D:\\proj --codex-full
    py -3.12 ecc_local_cli.py off --project D:\\proj
    py -3.12 ecc_local_cli.py selfcheck --project D:\\proj
    py -3.12 ecc_local_cli.py update
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import deploy, selfcheck, settings, update
from .eccrepo import EccRepo, default_ecc_repo
from .log import Logger


def _logger() -> Logger:
    return Logger(sink=lambda lvl, msg: print(f"[{lvl}] {msg}"), logfile=settings.log_file())


def _resolve_ecc(arg_ecc: str | None) -> EccRepo:
    st = settings.load()
    path = arg_ecc or st.get("ecc") or str(default_ecc_repo())
    return EccRepo(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ecc-local", description="ECC 局部启用工具 (CLI)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--ecc", help="ECC 仓库路径(默认取上次/同级 ECC)")
        p.add_argument("--project", default=".", help="目标项目路径(默认当前目录)")

    pon = sub.add_parser("on", help="在项目内启用")
    common(pon)
    pon.add_argument("--harness", choices=["both", "claude", "codex"], default="both")
    pon.add_argument("--profile", default="core")
    pon.add_argument("--rules", default="common", help="逗号分隔，如 common,zh,python")
    pon.add_argument("--codex-full", action="store_true", help="Codex 用档位②(整个 .codex/)")
    pon.add_argument("--codex-override", action="store_true", help="用 AGENTS.override.md")
    pon.add_argument("--mcp", help="显式保留的 MCP(逗号分隔)，给了就按它来")
    pon.add_argument("--keep-playwright", action="store_true")
    pon.add_argument("--dry-run", action="store_true")

    poff = sub.add_parser("off", help="在项目内停用")
    common(poff)
    poff.add_argument("--harness", choices=["both", "claude", "codex"], default="both")
    poff.add_argument("--dry-run", action="store_true")
    poff.add_argument("--force", action="store_true")

    pchk = sub.add_parser("selfcheck", help="体检")
    common(pchk)
    pchk.add_argument("--profile", default=None)

    pup = sub.add_parser("update", help="更新 ECC(git pull + npm install)")
    pup.add_argument("--ecc")

    args = ap.parse_args(argv)
    log = _logger()
    ecc = _resolve_ecc(getattr(args, "ecc", None))

    # 记住本次用的 ecc 路径
    st = settings.load()
    st["ecc"] = str(ecc.path)
    if getattr(args, "project", None):
        st["project"] = str(Path(args.project).resolve())
    settings.save(st)

    if args.cmd == "on":
        rules = [r.strip() for r in args.rules.split(",") if r.strip()]
        keep = [m.strip() for m in args.mcp.split(",")] if args.mcp else None
        deploy.enable(ecc, args.project, harness=args.harness, profile=args.profile,
                      rules=rules, full=args.codex_full, override=args.codex_override,
                      keep_servers=keep, keep_playwright=args.keep_playwright,
                      dry_run=args.dry_run, logger=log)
    elif args.cmd == "off":
        deploy.disable(args.project, harness=args.harness, dry_run=args.dry_run,
                       force=args.force, logger=log)
    elif args.cmd == "selfcheck":
        selfcheck.run(ecc, project=args.project, profile=args.profile, logger=log)
    elif args.cmd == "update":
        update.update_ecc(ecc, logger=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
