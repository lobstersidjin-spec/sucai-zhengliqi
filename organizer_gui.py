#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点点素材管理大师 - 图形界面
参考 KOCARD 卡片式设计，采用 ttkbootstrap 暗色主题
"""

import os
import sys
import threading
from pathlib import Path

from tkinter import scrolledtext, messagebox, filedialog
from tkinter.constants import BOTH, X, W, DISABLED, NORMAL, END

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    HAS_TTKBOOTSTRAP = True
except ImportError:
    import tkinter as tk
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
    from media_organizer import Config, MediaOrganizer, __version__, PROJECT_NAME, get_log_file_path
except Exception as e:
    try:
        messagebox.showerror("错误", f"无法加载核心模块: {e}\n请确保 media_organizer.py 存在")
    except Exception:
        pass
    sys.exit(1)

# 暗色主题文本区域配色
TEXT_BG = "#2b3e50"
TEXT_FG = "#ecf0f1"
TEXT_INSERT = "#3498db"


def _bs(style):
    """ttkbootstrap bootstyle 参数"""
    return {"bootstyle": style} if HAS_TTKBOOTSTRAP else {}


def _lf_style():
    """卡片式 Labelframe 样式"""
    return _bs("secondary") if HAS_TTKBOOTSTRAP else {}


def main():
    config = Config()

    if HAS_TTKBOOTSTRAP:
        root = ttk.Window(
            title=f"{PROJECT_NAME} v{__version__}",
            themename="darkly",
            size=(860, 700),
            resizable=(True, True),
            minsize=(700, 560),
        )
    else:
        root = tk.Tk()
        root.title(f"{PROJECT_NAME} v{__version__}")
        root.geometry("860x700")
        root.minsize(700, 560)

    main_frm = ttk.Frame(root, padding=15)
    main_frm.pack(fill=BOTH, expand=True)

    # 顶部标题区
    header_f = ttk.Frame(main_frm)
    header_f.pack(fill=X, pady=(0, 12))
    ttk.Label(header_f, text=PROJECT_NAME, font=("", 16, "bold")).pack(side="left")
    ttk.Label(header_f, text=f"v{__version__}", font=("", 10)).pack(side="left", padx=(8, 0))

    # 选项卡
    notebook = ttk.Notebook(main_frm)
    notebook.pack(fill=X, expand=False)

    # ===== 扫描整理 卡片 =====
    scan_frm = ttk.Frame(notebook, padding=12)
    notebook.add(scan_frm, text="  扫描整理  ")

    scan_card = ttk.Labelframe(scan_frm, text="扫描整理：按日期/类型/设备分类并移动", **_lf_style())
    scan_card.pack(fill=X, expand=False, pady=4)

    ttk.Label(scan_card, text="源文件夹（待整理的素材目录）:").pack(anchor=W, pady=(8, 4))
    src_var = ttk.StringVar(value=getattr(config, "source_path", "") or "")
    src_row = ttk.Frame(scan_card)
    src_row.pack(fill=X, pady=(0, 10))
    ttk.Entry(src_row, textvariable=src_var, width=50).pack(side="left", fill=X, expand=True, padx=(0, 8))

    def choose_src():
        d = filedialog.askdirectory(title="选择源文件夹")
        if d:
            src_var.set(d)

    ttk.Button(src_row, text="浏览…", command=choose_src, **_bs("secondary")).pack(side="right")

    ttk.Label(scan_card, text="输出根目录（留空则与源相同）:").pack(anchor=W, pady=(4, 4))
    out_var = ttk.StringVar(value=getattr(config, "output_path", "") or "")
    out_row = ttk.Frame(scan_card)
    out_row.pack(fill=X, pady=(0, 10))
    ttk.Entry(out_row, textvariable=out_var, width=50).pack(side="left", fill=X, expand=True, padx=(0, 8))

    def choose_out():
        d = filedialog.askdirectory(title="选择输出根目录")
        if d:
            out_var.set(d)

    ttk.Button(out_row, text="浏览…", command=choose_out, **_bs("secondary")).pack(side="right")

    dry_var = ttk.BooleanVar(value=False)
    ttk.Checkbutton(scan_card, text="试运行（仅扫描并报告，不移动文件）", variable=dry_var).pack(anchor=W, pady=(0, 8))

    delete_empty_var = ttk.BooleanVar(value=getattr(config, "delete_empty_folders", False))
    ttk.Checkbutton(scan_card, text="整理完成后清理目标目录中的空文件夹", variable=delete_empty_var).pack(anchor=W, pady=(0, 8))

    def format_scan_report(report):
        """将扫描/整理报告格式化为可输出到日志的完整报告文本。"""
        if not report or not isinstance(report, dict):
            return ""
        lines = [
            "========== 扫描/整理任务报告 ==========",
            f"模式: {'仅扫描（试运行）' if report.get('mode') == 'scan_only' else '扫描并整理'}",
            f"源目录: {report.get('source', '')}",
            f"输出目录: {report.get('output', '')}",
            f"发现媒体文件数: {report.get('total_media', 0)}",
            f"待处理主文件数: {report.get('to_process', 0)}",
            "----------------------------------------",
        ]
        entries = report.get("entries") or []
        move_n = sum(1 for e in entries if e[0] == "move")
        related_n = sum(1 for e in entries if e[0] == "related")
        skip_n = sum(1 for e in entries if e[0] == "skip")
        already_n = sum(1 for e in entries if e[0] == "already_processed")
        fail_n = sum(1 for e in entries if e[0].startswith("fail"))
        for act, src, dest in entries:
            if act == "move":
                lines.append(f"  [将移动] {Path(src).name} -> {dest}")
            elif act == "related":
                lines.append(f"  [关联]   {Path(src).name} -> {dest}")
            elif act == "skip":
                lines.append(f"  [跳过]   {Path(src).name} ({dest})")
            elif act == "already_processed":
                lines.append(f"  [已整理过] {Path(src).name} ({dest or '此前已整理'})")
            elif act.startswith("fail"):
                lines.append(f"  [失败]   {Path(src).name} - {dest}")
        lines.append("----------------------------------------")
        lines.append(f"统计: 主文件移动={move_n} 关联={related_n} 跳过={skip_n} 已整理过={already_n} 失败={fail_n}")
        lines.append("==========================================")
        return "\n".join(lines)

    def run_scan():
        config.source_path = src_var.get().strip()
        config.output_path = out_var.get().strip()
        config.delete_empty_folders = delete_empty_var.get()
        config.save_config()
        if not config.source_path:
            messagebox.showwarning("提示", "请选择源文件夹")
            return
        source = Path(config.source_path)
        if not source.exists():
            messagebox.showerror("错误", f"源路径不存在: {source}")
            return
        output = Path(config.output_path) if config.output_path else None
        scan_only = dry_var.get()

        def work():
            if scan_only:
                log_append("开始扫描（仅报告，不移动）…")
            else:
                log_append("开始整理…")
            try:
                organizer = MediaOrganizer(config)
                report = organizer.scan_and_organize(
                    source=source, output=output, dry_run=False, scan_only=scan_only
                )
                report_text = format_scan_report(report)
                def on_done():
                    if report_text:
                        for line in report_text.splitlines():
                            log_append(line)
                    if scan_only:
                        log_append("扫描完成。以上为将执行的操作预览。")
                        messagebox.showinfo("完成", "扫描完成，结果已输出到运行日志。")
                    else:
                        log_append("整理完成。以上为本次任务报告。")
                        messagebox.showinfo("完成", "整理完成，任务报告已输出到运行日志。")
                root.after(0, on_done)
            except Exception as e:
                root.after(0, lambda: (log_append("错误: " + str(e)), messagebox.showerror("错误", str(e))))

        threading.Thread(target=work, daemon=True).start()

    scan_btn = ttk.Button(scan_card, text="开始整理", command=run_scan, **_bs("success"))
    scan_btn.pack(anchor=W, pady=(4, 8))

    def update_scan_btn_text(*args):
        if dry_var.get():
            scan_btn.config(text="开始扫描")
        else:
            scan_btn.config(text="开始整理")
    dry_var.trace_add("write", update_scan_btn_text)

    # ===== 超级拷贝 卡片 =====
    copy_frm = ttk.Frame(notebook, padding=12)
    notebook.add(copy_frm, text="  超级拷贝  ")

    copy_card = ttk.Labelframe(
        copy_frm,
        text="超级拷贝：拷贝到目标 + 自动整理 + SHA256 哈希校验",
        **_lf_style(),
    )
    copy_card.pack(fill=X, expand=False, pady=4)

    ttk.Label(copy_card, text="源文件夹（待拷贝的素材目录）:").pack(anchor=W, pady=(8, 4))
    copy_src_var = ttk.StringVar(value=getattr(config, "super_copy_source", "") or "")
    copy_src_row = ttk.Frame(copy_card)
    copy_src_row.pack(fill=X, pady=(0, 10))
    ttk.Entry(copy_src_row, textvariable=copy_src_var, width=50).pack(side="left", fill=X, expand=True, padx=(0, 8))

    def choose_copy_src():
        d = filedialog.askdirectory(title="选择待拷贝的源文件夹")
        if d:
            copy_src_var.set(d)

    ttk.Button(copy_src_row, text="浏览…", command=choose_copy_src, **_bs("secondary")).pack(side="right")

    ttk.Label(copy_card, text="目标目录（拷贝到此处并自动整理、哈希校验）:").pack(anchor=W, pady=(4, 4))
    copy_tgt_var = ttk.StringVar(value=getattr(config, "super_copy_target", "") or "")
    copy_tgt_row = ttk.Frame(copy_card)
    copy_tgt_row.pack(fill=X, pady=(0, 10))
    ttk.Entry(copy_tgt_row, textvariable=copy_tgt_var, width=50).pack(side="left", fill=X, expand=True, padx=(0, 8))

    def choose_copy_tgt():
        d = filedialog.askdirectory(title="选择目标目录")
        if d:
            copy_tgt_var.set(d)

    ttk.Button(copy_tgt_row, text="浏览…", command=choose_copy_tgt, **_bs("secondary")).pack(side="right")

    copy_dry_var = ttk.BooleanVar(value=False)
    ttk.Checkbutton(copy_card, text="试运行（不实际拷贝）", variable=copy_dry_var).pack(anchor=W, pady=(0, 8))
    ttk.Checkbutton(copy_card, text="拷贝完成后清理目标目录中的空文件夹", variable=delete_empty_var).pack(anchor=W, pady=(0, 8))

    # 超级拷贝进度条与状态
    progress_frm = ttk.Frame(copy_card)
    progress_frm.pack(fill=X, pady=(0, 6))
    progress_label = ttk.Label(progress_frm, text="")
    progress_label.pack(anchor=W)
    copy_progress = ttk.Progressbar(progress_frm, mode="determinate", maximum=100, value=0)
    copy_progress.pack(fill=X, pady=(2, 0))

    def format_super_copy_report(stats_with_report):
        """将超级拷贝结果格式化为完整任务报告文本。"""
        ok = stats_with_report.get("ok", 0)
        fail = stats_with_report.get("fail", 0)
        skip = stats_with_report.get("skip", 0)
        report = stats_with_report.get("report") or {}
        media_ok = report.get("media_ok") or []
        media_skip = report.get("media_skip") or []
        media_fail = report.get("media_fail") or []
        other_ok = report.get("other_ok") or []
        other_fail = report.get("other_fail") or []
        lines = [
            "========== 超级拷贝任务报告 ==========",
            f"统计: 成功={ok} 失败={fail} 跳过={skip}",
            "----------------------------------------",
        ]
        if media_ok:
            lines.append("【媒体/关联 已拷贝】")
            for src, dest in media_ok:
                lines.append(f"  {Path(src).name} -> {Path(dest).name}")
        if media_skip:
            lines.append("【媒体 已跳过（目标已存在）】")
            for src, reason in media_skip:
                lines.append(f"  {Path(src).name} ({reason})")
        if media_fail:
            lines.append("【媒体/关联 拷贝失败】")
            for src, err in media_fail:
                lines.append(f"  {Path(src).name} - {err}")
        if other_ok:
            lines.append("【其他文件 已拷贝】")
            for rel in other_ok:
                lines.append(f"  {rel}")
        if other_fail:
            lines.append("【其他文件 拷贝失败】")
            for rel, err in other_fail:
                lines.append(f"  {rel} - {err}")
        lines.append("==========================================")
        return "\n".join(lines)

    def run_super_copy():
        config.super_copy_source = copy_src_var.get().strip()
        config.super_copy_target = copy_tgt_var.get().strip()
        config.delete_empty_folders = delete_empty_var.get()
        config.save_config()
        if not config.super_copy_source:
            messagebox.showwarning("提示", "请选择待拷贝的源文件夹")
            return
        if not config.super_copy_target:
            messagebox.showwarning("提示", "请选择目标目录")
            return
        source = Path(config.super_copy_source)
        target = Path(config.super_copy_target)
        if not source.exists():
            messagebox.showerror("错误", f"源路径不存在: {source}")
            return
        dry = copy_dry_var.get()

        def work():
            def progress_cb(phase, message, current, total):
                def update():
                    if total is not None and total > 0 and current is not None:
                        copy_progress["maximum"] = total
                        copy_progress["value"] = current
                        lbl = f"当前: {current} / {total}"
                        if message:
                            lbl += " · " + (message[:60] + "…" if len(message) > 60 else message)
                        progress_label.config(text=lbl)
                    if message:
                        log_append(message)
                try:
                    root.after(0, update)
                except Exception:
                    pass

            root.after(0, lambda: (copy_progress.config(value=0, maximum=100), progress_label.config(text="")))
            log_append("超级拷贝 开始…")
            try:
                organizer = MediaOrganizer(config)
                stats = organizer.super_copy_and_organize(
                    source=source, target=target, dry_run=dry, progress_cb=progress_cb
                )
                msg = f"超级拷贝完成: 成功={stats['ok']} 失败={stats['fail']} 跳过={stats['skip']}"
                detail = "\n完整任务报告已输出到运行日志。\n详见 " + get_log_file_path()
                if stats["ok"] == 0 and stats["fail"] == 0 and stats["skip"] == 0:
                    detail = "\n\n未发现可处理的媒体文件。请确认：\n1) 源目录下是否有 .jpg/.mp4/.mov 等图片/视频/音频；\n2) config.json 中的扩展名配置。" + detail
                report_text = format_super_copy_report(stats)

                def done():
                    total = copy_progress["maximum"]
                    if total and total > 0:
                        copy_progress["value"] = total
                        progress_label.config(text=f"完成: {total} / {total}")
                    log_append(msg)
                    if report_text:
                        for line in report_text.splitlines():
                            log_append(line)
                    messagebox.showinfo("完成", msg + detail)
                root.after(0, done)
            except Exception as e:
                root.after(0, lambda: (log_append("错误: " + str(e)), messagebox.showerror("错误", str(e))))

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(copy_card, text="开始超级拷贝", command=run_super_copy, **_bs("primary")).pack(anchor=W, pady=(4, 8))

    # ===== 共用日志区（卡片式）=====
    ttk.Separator(main_frm, orient="horizontal").pack(fill=X, pady=(12, 8))
    log_card = ttk.Labelframe(main_frm, text="运行日志", **_lf_style())
    log_card.pack(fill=BOTH, expand=True, pady=(0, 8))
    log_text = scrolledtext.ScrolledText(
        log_card,
        height=16,
        state=DISABLED,
        wrap="word",
        font=("Consolas", 9),
        bg=TEXT_BG,
        fg=TEXT_FG,
        insertbackground=TEXT_INSERT,
        relief="flat",
        padx=8,
        pady=8,
    )
    log_text.pack(fill=BOTH, expand=True)

    def log_append(msg: str):
        log_text.configure(state=NORMAL)
        log_text.insert(END, msg + "\n")
        log_text.see(END)
        log_text.configure(state=DISABLED)

    btn_row = ttk.Frame(main_frm)
    btn_row.pack(fill=X)
    ttk.Button(btn_row, text="关闭", command=root.destroy, **_bs("secondary")).pack(side="right")

    root.mainloop()


if __name__ == "__main__":
    main()
