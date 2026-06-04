"""tkinter 小窗口界面。长任务放后台线程，日志经队列回传主线程，界面不卡死。"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, deploy, mcp, selfcheck, settings, update
from .eccrepo import EccRepo, default_ecc_repo
from .log import Logger

PAD = 6


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"ECC 局部启用工具  v{__version__}")
        root.geometry("780x680")
        root.minsize(720, 600)

        self.log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.busy = False
        self.mcp_vars: dict[str, tk.BooleanVar] = {}
        self.mcp_scanned = False

        st = settings.load()
        self.ecc_var = tk.StringVar(value=st.get("ecc") or str(default_ecc_repo()))
        self.project_var = tk.StringVar(value=st.get("project") or "")
        self.claude_on = tk.BooleanVar(value=True)
        self.codex_on = tk.BooleanVar(value=True)
        self.profile_var = tk.StringVar(value="core")
        self.codex_mode = tk.StringVar(value="light")  # light / full
        self.override_var = tk.BooleanVar(value=False)
        self.keep_pw_var = tk.BooleanVar(value=False)

        self._build()
        self._refresh_ecc_meta()
        self.root.after(100, self._drain_log)

    # ---------------- 构建界面 ----------------
    def _build(self) -> None:
        top = ttk.LabelFrame(self.root, text="路径")
        top.pack(fill="x", padx=PAD, pady=PAD)
        self._path_row(top, "ECC 仓库：", self.ecc_var, self._browse_ecc, 0)
        self._path_row(top, "项目目录：", self.project_var, self._browse_project, 1)
        top.columnconfigure(1, weight=1)

        mid = ttk.Frame(self.root)
        mid.pack(fill="x", padx=PAD)

        # Claude
        cf = ttk.LabelFrame(mid, text="Claude Code")
        cf.pack(side="left", fill="both", expand=True, padx=(0, PAD))
        ttk.Checkbutton(cf, text="启用 Claude", variable=self.claude_on).pack(anchor="w", padx=PAD, pady=2)
        prow = ttk.Frame(cf); prow.pack(fill="x", padx=PAD)
        ttk.Label(prow, text="profile:").pack(side="left")
        self.profile_combo = ttk.Combobox(prow, textvariable=self.profile_var, state="readonly", width=14)
        self.profile_combo.pack(side="left", padx=4)
        ttk.Label(cf, text="rules (可多选):").pack(anchor="w", padx=PAD)
        self.rules_list = tk.Listbox(cf, selectmode=tk.MULTIPLE, height=6, exportselection=False)
        self.rules_list.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        # Codex
        xf = ttk.LabelFrame(mid, text="Codex")
        xf.pack(side="left", fill="both", expand=True)
        ttk.Checkbutton(xf, text="启用 Codex", variable=self.codex_on).pack(anchor="w", padx=PAD, pady=2)
        ttk.Radiobutton(xf, text="档位① 仅指令(AGENTS.md)", variable=self.codex_mode,
                        value="light", command=self._toggle_mcp).pack(anchor="w", padx=PAD)
        ttk.Radiobutton(xf, text="档位② 整个 .codex/(含 MCP)", variable=self.codex_mode,
                        value="full", command=self._toggle_mcp).pack(anchor="w", padx=PAD)
        ttk.Checkbutton(xf, text="用 AGENTS.override.md(屏蔽全局指令)",
                        variable=self.override_var).pack(anchor="w", padx=PAD)
        ttk.Checkbutton(xf, text="保留 playwright", variable=self.keep_pw_var).pack(anchor="w", padx=PAD)
        self.scan_btn = ttk.Button(xf, text="扫描 MCP（动态识别）", command=self._scan_mcp)
        self.scan_btn.pack(anchor="w", padx=PAD, pady=2)
        self.mcp_frame = ttk.LabelFrame(xf, text="MCP 服务器（勾选=保留）")
        self.mcp_frame.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        # 按钮
        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=PAD, pady=PAD)
        self.buttons = []
        for text, cmd in [("体检 Self-Check", self._do_selfcheck),
                          ("预览 DryRun", lambda: self._do_enable(dry_run=True)),
                          ("一键部署", lambda: self._do_enable(dry_run=False)),
                          ("停用", self._do_disable),
                          ("更新 ECC", self._do_update)]:
            b = ttk.Button(btns, text=text, command=cmd)
            b.pack(side="left", padx=3)
            self.buttons.append(b)

        # 日志
        lf = ttk.LabelFrame(self.root, text="日志")
        lf.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.log_text = tk.Text(lf, height=12, wrap="word", state="disabled", bg="#1e1e1e", fg="#dcdcdc")
        self.log_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)
        for tag, color in [("OK", "#4ec9b0"), ("WARN", "#dcdcaa"), ("ERR", "#f48771"), ("INFO", "#dcdcdc")]:
            self.log_text.tag_config(tag, foreground=color)

        self.status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status, anchor="w", relief="sunken").pack(fill="x")
        self._toggle_mcp()

    def _path_row(self, parent, label, var, browse, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=2, pady=3)
        ttk.Button(parent, text="浏览…", command=browse).grid(row=row, column=2, padx=PAD, pady=3)

    # ---------------- 浏览 / 刷新 ----------------
    def _browse_ecc(self):
        d = filedialog.askdirectory(title="选择 ECC 仓库目录", initialdir=self.ecc_var.get() or ".")
        if d:
            self.ecc_var.set(d)
            self._refresh_ecc_meta()

    def _browse_project(self):
        d = filedialog.askdirectory(title="选择目标项目目录", initialdir=self.project_var.get() or ".")
        if d:
            self.project_var.set(d)

    def _refresh_ecc_meta(self):
        """根据 ECC 路径动态刷新 profile 下拉与 rules 列表。"""
        ecc = EccRepo(self.ecc_var.get())
        profs = ecc.profiles()
        self.profile_combo["values"] = profs
        if self.profile_var.get() not in profs:
            self.profile_var.set("core" if "core" in profs else (profs[0] if profs else "core"))
        self.rules_list.delete(0, tk.END)
        for r in ecc.rule_sets():
            self.rules_list.insert(tk.END, r)
            if r == "common":
                self.rules_list.selection_set(tk.END)

    def _toggle_mcp(self):
        state = "normal" if self.codex_mode.get() == "full" else "disabled"
        try:
            self.scan_btn.config(state=state)
        except Exception:
            pass

    def _scan_mcp(self):
        for w in self.mcp_frame.winfo_children():
            w.destroy()
        self.mcp_vars.clear()
        ecc = EccRepo(self.ecc_var.get())
        if not ecc.codex_config.exists():
            ttk.Label(self.mcp_frame, text="未找到 ECC 的 .codex/config.toml").pack(anchor="w")
            return
        plan = mcp.auto_plan(ecc.codex_config, keep_playwright=self.keep_pw_var.get())
        if not plan:
            ttk.Label(self.mcp_frame, text="(配置里没有 mcp_servers)").pack(anchor="w")
        for name, keep, reason in plan:
            var = tk.BooleanVar(value=keep)
            self.mcp_vars[name] = var
            row = ttk.Frame(self.mcp_frame); row.pack(fill="x", anchor="w")
            ttk.Checkbutton(row, text=name, variable=var, width=22).pack(side="left")
            color = "#0a7d00" if keep else "#8a6d00"
            tk.Label(row, text=reason, fg=color).pack(side="left")
        self.mcp_scanned = True
        self._log("INFO", f"已扫描 MCP：{', '.join(n for n,_,_ in plan)}")

    # ---------------- 日志 ----------------
    def _log(self, level: str, msg: str):
        self.log_queue.put((level, msg))

    def _drain_log(self):
        try:
            while True:
                level, msg = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, f"[{level}] {msg}\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def _logger(self) -> Logger:
        return Logger(sink=lambda lvl, msg: self._log(lvl, msg), logfile=settings.log_file())

    # ---------------- 后台任务封装 ----------------
    def _run_bg(self, target, *args, **kwargs):
        if self.busy:
            messagebox.showinfo("请稍候", "已有任务在运行。")
            return
        self.busy = True
        self.status.set("运行中…")
        for b in self.buttons:
            b.config(state="disabled")

        def wrap():
            try:
                target(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self._log("ERR", f"未捕获异常：{exc}")
            finally:
                self.root.after(0, self._done)

        threading.Thread(target=wrap, daemon=True).start()

    def _done(self):
        self.busy = False
        self.status.set("就绪")
        for b in self.buttons:
            b.config(state="normal")

    def _save_paths(self):
        st = settings.load()
        st["ecc"] = self.ecc_var.get()
        if self.project_var.get():
            st["project"] = self.project_var.get()
        settings.save(st)

    def _ecc(self) -> EccRepo:
        return EccRepo(self.ecc_var.get())

    def _harness(self) -> str:
        c, x = self.claude_on.get(), self.codex_on.get()
        return "both" if c and x else ("claude" if c else ("codex" if x else "none"))

    def _selected_rules(self):
        return [self.rules_list.get(i) for i in self.rules_list.curselection()] or ["common"]

    # ---------------- 动作 ----------------
    def _do_selfcheck(self):
        self._save_paths()
        proj = self.project_var.get() or None
        self._run_bg(selfcheck.run, self._ecc(), proj, self.profile_var.get(), self._logger())

    def _do_enable(self, dry_run: bool):
        self._save_paths()
        if self._harness() == "none":
            messagebox.showwarning("未选择", "请至少勾选 Claude 或 Codex。")
            return
        if not self.project_var.get():
            messagebox.showwarning("缺少项目", "请选择目标项目目录。")
            return
        full = self.codex_mode.get() == "full"
        keep = None
        if full and self.mcp_scanned and self.mcp_vars:
            keep = [n for n, v in self.mcp_vars.items() if v.get()]
        self._run_bg(deploy.enable, self._ecc(), self.project_var.get(),
                     self._harness(), self.profile_var.get(), self._selected_rules(),
                     full, self.override_var.get(), keep, self.keep_pw_var.get(),
                     dry_run, self._logger())

    def _do_disable(self):
        self._save_paths()
        if not self.project_var.get():
            messagebox.showwarning("缺少项目", "请选择目标项目目录。")
            return
        if not messagebox.askyesno("确认停用", "将移除本项目内由本工具创建的 ECC 文件，继续？"):
            return
        self._run_bg(deploy.disable, self.project_var.get(), self._harness(), False, False, self._logger())

    def _do_update(self):
        self._save_paths()
        self._run_bg(update.update_ecc, self._ecc(), self._logger())


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
