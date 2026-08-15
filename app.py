"""图形界面模块：tkinter 主窗口与哈希对比窗口。

布局：墨黑标题带（包豪斯几何标识）、顶部（算法勾选 + 操作按钮）、中部（文件列表与结果表格）、
底部（进度条 + 状态栏）。视觉为包豪斯风格：暖纸底色、三原色点缀、扁平化控件。
哈希计算在后台线程池并行进行（多文件最多 4 线程），通过 queue 与界面通信，避免大文件计算时界面卡死。
可选依赖 ttkbootstrap：若已安装则 ttk 控件自动改用其 cosmo 主题（标题带等非 ttk 部分保持包豪斯风格）。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, ttk

import hash_core
from i18n import LANGUAGES, get_lang, init_language, save_config, set_lang, tr

APP_VERSION = "1.5.0"

# 对比结果配色（语义色）：一致=绿色、不一致=红色、缺失=橙色
C_GREEN = "#1e7e34"
C_RED = "#c0392b"
C_ORANGE = "#d2691e"
C_GRAY = "#8a8a8a"

# 包豪斯品牌色板：暖纸底、近黑、三原色
INK = "#1b1b1b"        # 标题带 / 表头 / 正文
PAPER = "#f4f1ea"      # 窗口底色（暖纸）
CARD = "#ffffff"       # 卡片白
LINE = "#d9d4c7"       # 边框 / 分隔线
BLUE = "#1e5aa8"       # 包豪斯蓝（主操作 / 进度 / 选中）
BLUE_DARK = "#174a87"  # 悬停深蓝
RED = "#d22630"        # 包豪斯红（取消 / 危险操作）
RED_DARK = "#ae1f28"   # 悬停深红
YELLOW = "#f2b500"     # 包豪斯黄（几何点缀）
MUTED = "#7a756a"      # 次要文字

_UI_FONT = "Microsoft YaHei UI"  # Windows 10/11 自带
_MONO_FONT = "Consolas"
_ZEBRA_BG = "#f7f5ef"  # 表格偶数行底色（斑马纹，与暖纸底协调）

ALGOS = hash_core.SUPPORTED_ALGORITHMS
LABEL = hash_core.ALGORITHM_LABELS


def _apply_icon(root) -> None:
    """设置窗口图标：开发模式用项目内的 app.ico；打包后用 exe 自身图标。"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(sys.executable)
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico"))
    for path in candidates:
        try:
            if os.path.exists(path):
                root.iconbitmap(default=path)
                return
        except tk.TclError:
            continue


def _apply_style(root, use_boot: bool) -> None:
    """统一界面字体与控件观感；未安装 ttkbootstrap 时基于 clam 主题应用包豪斯扁平风格。"""
    import tkinter.font as tkfont

    for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
        try:
            tkfont.nametofont(name).configure(family=_UI_FONT, size=9)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkFixedFont").configure(family=_MONO_FONT, size=9)
    except tk.TclError:
        pass
    if use_boot:
        return
    style = ttk.Style(root)
    # ---- 基础：暖纸底 + 近黑文字 ----
    style.configure("TFrame", background=PAPER)
    style.configure("TLabel", background=CARD, foreground=INK)
    style.configure("Status.TLabel", background=PAPER, foreground=INK)
    style.configure("Hint.TLabel", background=CARD, foreground=MUTED)
    style.configure("TSeparator", background=LINE)
    # ---- 卡片（LabelFrame）：白底细边 ----
    style.configure("TLabelframe", background=CARD, bordercolor=LINE, borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=CARD, foreground=INK, font=(_UI_FONT, 9, "bold"))
    # ---- 按钮：扁平；主操作实心蓝、危险操作实心红 ----
    style.configure("TButton", background=CARD, foreground=INK, bordercolor=LINE,
                    borderwidth=1, relief="flat", padding=(12, 6), font=(_UI_FONT, 9))
    style.map("TButton",
              background=[("pressed", "#e2ded4"), ("active", "#edeae2"), ("disabled", "#e7e3d9")],
              foreground=[("disabled", MUTED)])
    style.configure("Accent.TButton", background=BLUE, foreground="#ffffff",
                    borderwidth=0, padding=(14, 6), font=(_UI_FONT, 9, "bold"))
    style.map("Accent.TButton",
              background=[("pressed", "#123c6e"), ("active", BLUE_DARK), ("disabled", "#e7e3d9")],
              foreground=[("disabled", MUTED)])
    style.configure("Danger.TButton", background=RED, foreground="#ffffff",
                    borderwidth=0, padding=(14, 6), font=(_UI_FONT, 9, "bold"))
    style.map("Danger.TButton",
              background=[("pressed", "#8f1a22"), ("active", RED_DARK), ("disabled", "#e7e3d9")],
              foreground=[("disabled", MUTED)])
    # ---- 勾选 / 单选 ----
    style.configure("TCheckbutton", background=CARD, foreground=INK)
    style.map("TCheckbutton", background=[("active", "#edeae2")])
    style.configure("TRadiobutton", background=PAPER, foreground=INK)
    style.map("TRadiobutton", background=[("active", "#edeae2")])
    # ---- 表格：白底、墨黑表头、蓝色选中 ----
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                    borderwidth=0, rowheight=28, font=(_UI_FONT, 9))
    style.configure("Treeview.Heading", background=INK, foreground="#ffffff",
                    font=(_UI_FONT, 9, "bold"), padding=(8, 6), relief="flat", borderwidth=0)
    style.map("Treeview.Heading", background=[("active", "#333333")])
    style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "#ffffff")])
    # ---- 输入框 / 下拉框：白底，聚焦时蓝框 ----
    style.configure("TEntry", fieldbackground=CARD, foreground=INK, bordercolor=LINE,
                    insertcolor=INK, padding=(4, 3))
    style.map("TEntry", bordercolor=[("focus", BLUE)])
    style.configure("TCombobox", fieldbackground=CARD, foreground=INK, bordercolor=LINE,
                    padding=(4, 3))
    # disabled 必须排在 readonly 之前（style map 按首个匹配生效），否则禁用态无视觉反馈
    style.map("TCombobox", bordercolor=[("focus", BLUE)],
              fieldbackground=[("disabled", "#e7e3d9"), ("readonly", CARD)],
              foreground=[("disabled", MUTED), ("readonly", INK)])
    # ---- 滚动条 / 进度条 / 标签页 ----
    style.configure("TScrollbar", background="#e7e3d9", troughcolor=PAPER, bordercolor=PAPER,
                    arrowcolor=INK, borderwidth=0, relief="flat")
    style.map("TScrollbar", background=[("active", "#d9d4c7"), ("pressed", LINE)])
    style.configure("Horizontal.TProgressbar", troughcolor="#e7e3d9", background=BLUE,
                    bordercolor="#e7e3d9", lightcolor=BLUE, darkcolor=BLUE, thickness=12)
    style.configure("TNotebook", background=PAPER, borderwidth=0, tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", background="#e7e3d9", foreground=INK, padding=(16, 7))
    style.map("TNotebook.Tab", background=[("selected", CARD)])


def _styled_menu(master) -> tk.Menu:
    """创建与包豪斯风格一致的下拉/右键菜单（经典 tk.Menu，不受 ttk 主题控制）。"""
    return tk.Menu(
        master, tearoff=0, bg=CARD, fg=INK, activebackground=BLUE, activeforeground="#ffffff",
        disabledforeground=MUTED, relief="flat", bd=1, activeborderwidth=0, selectcolor=INK,
    )


def _root_with_style():
    """创建根窗口：优先使用可选的 ttkbootstrap 主题，否则回退到内置 clam 主题（包豪斯风格）。"""
    try:
        import ttkbootstrap as tb  # 可选第三方库，仅用于美化

        root, use_boot = tb.Window(themename="cosmo"), True
    except Exception:
        root, use_boot = tk.Tk(), False
        root.configure(bg=PAPER)
        try:
            ttk.Style(root).theme_use("clam")
        except tk.TclError:
            pass
    _apply_icon(root)
    _apply_style(root, use_boot)
    return root, use_boot


class HashToolApp:
    """主窗口。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.files: list[str] = []
        self._seen: set[str] = set()
        self.results: dict[str, hash_core.HashResult] = {}
        self.worker: threading.Thread | None = None
        self.cancel_event: threading.Event | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.tracker = hash_core.ProgressTracker()  # 进度核算（纯逻辑，见 hash_core）
        self.total_files = 0
        self.compute_start = 0.0
        self.drop_target = None
        self.compare_win = None
        self.export_dlg = None
        self.add_worker = None  # 后台目录扫描线程（添加文件夹时）
        self._scanning = False  # 目录扫描进行中（含结果已得出、待轮询回插表格的窗口期）

        root.title(f"{tr('app_title')} v{APP_VERSION}")
        root.minsize(900, 600)
        self._center(root, 1120, 720)
        self._build_menu()
        self._build_ui()
        self._setup_dnd()
        self.status(tr("st_ready"))

    # ------------------------------------------------------------------ 基础

    @staticmethod
    def _center(win, w: int, h: int) -> None:
        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() - w) // 2)
        y = max(0, (win.winfo_screenheight() - h) // 3)
        win.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _zebra(index: int) -> tuple:
        """按行号返回斑马纹标签（偶数行带浅底色）。"""
        return ("even",) if index % 2 == 0 else ()

    @staticmethod
    def _empty_row(path: str, status: str) -> tuple:
        """生成一行初始表格值（大小/哈希/耗时留空），列数随 ALGOS 自动适配，避免硬编码空串个数。"""
        return (os.path.basename(path), path, "") + ("",) * len(ALGOS) + ("", status)

    def _retag_zebra(self) -> None:
        """删除行后重排斑马纹，保留各行已有的状态标签。"""
        for i, iid in enumerate(self.tree.get_children()):
            state = tuple(t for t in self.tree.item(iid, "tags") if t != "even")
            self.tree.item(iid, tags=self._zebra(i) + state)

    def status(self, text: str) -> None:
        self.status_var.set(text)

    def _copy_to_clipboard(self, text: str) -> bool:
        """复制文本到剪贴板；剪贴板被其他程序占用时（TclError）提示并返回 False。"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            self.status(tr("st_copy_fail"))
            return False
        return True

    # ------------------------------------------------------------------ 菜单

    def _build_menu(self) -> None:
        root = self.root
        menubar = _styled_menu(root)
        m_file = _styled_menu(menubar)
        m_file.add_command(label=tr("menu_add_files"), accelerator="Ctrl+O", command=self.add_files_dialog)
        m_file.add_command(label=tr("menu_add_folder"), accelerator="Ctrl+Shift+O", command=self.add_folder_dialog)
        m_file.add_separator()
        m_file.add_command(label=tr("menu_export"), accelerator="Ctrl+S", command=self.export_results)
        m_file.add_separator()
        m_file.add_command(label=tr("menu_exit"), command=self._on_close)
        menubar.add_cascade(label=tr("menu_file"), menu=m_file)

        m_calc = _styled_menu(menubar)
        m_calc.add_command(label=tr("menu_start"), accelerator="F5", command=self.start_compute)
        m_calc.add_command(label=tr("menu_cancel"), accelerator="Esc", command=self.cancel_compute)
        menubar.add_cascade(label=tr("menu_calc"), menu=m_calc)

        m_tool = _styled_menu(menubar)
        m_tool.add_command(label=tr("menu_compare"), accelerator="Ctrl+D", command=self.open_compare)
        menubar.add_cascade(label=tr("menu_tools"), menu=m_tool)

        m_lang = _styled_menu(menubar)
        self.var_lang = tk.StringVar(value=get_lang())
        for code, name in LANGUAGES.items():
            m_lang.add_radiobutton(label=name, value=code, variable=self.var_lang,
                                   command=lambda c=code: self.switch_language(c))
        menubar.add_cascade(label=tr("menu_lang"), menu=m_lang)

        m_help = _styled_menu(menubar)
        m_help.add_command(label=tr("menu_help_item"), command=self._show_help)
        m_help.add_command(label=tr("menu_about"), command=self._show_about)
        menubar.add_cascade(label=tr("menu_help"), menu=m_help)
        root.config(menu=menubar)

        root.bind("<Control-o>", lambda _e: self.add_files_dialog())
        root.bind("<Control-Shift-o>", lambda _e: self.add_folder_dialog())
        root.bind("<Control-s>", lambda _e: self.export_results())
        root.bind("<Control-d>", lambda _e: self.open_compare())
        root.bind("<F5>", lambda _e: self.start_compute())
        root.bind("<Escape>", lambda _e: self.cancel_compute())

    # ------------------------------------------------------------------ 界面

    def _build_ui(self) -> None:
        root = self.root
        # ---------- 包豪斯标题带：墨黑底 + 红圆/黄三角/蓝方块几何标识 ----------
        header = tk.Frame(root, bg=INK, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        shapes = tk.Canvas(header, width=104, height=56, bg=INK, highlightthickness=0, bd=0)
        shapes.create_oval(10, 16, 34, 40, fill=RED, outline="")
        shapes.create_polygon(44, 40, 56, 16, 68, 40, fill=YELLOW, outline="")
        shapes.create_rectangle(76, 16, 100, 40, fill=BLUE, outline="")
        shapes.pack(side="left", padx=(10, 2))
        tk.Label(header, text=tr("app_title"), bg=INK, fg="#ffffff",
                 font=(_UI_FONT, 13, "bold")).pack(side="left", padx=8)
        tk.Label(header, text=f"v{APP_VERSION}", bg=INK, fg="#9b978d",
                 font=(_UI_FONT, 9)).pack(side="right", padx=14)
        # ---------- 顶部：算法勾选与操作按钮 ----------
        top = ttk.LabelFrame(root, text=tr("frame_algos"), padding=(10, 6))
        top.pack(fill="x", padx=8, pady=(8, 4))
        algo_row = ttk.Frame(top)
        algo_row.pack(fill="x")
        self.algo_vars: dict[str, tk.BooleanVar] = {}
        for algo in ALGOS:
            var = tk.BooleanVar(value=(algo == "sha256"))
            self.algo_vars[algo] = var
            ttk.Checkbutton(algo_row, text=LABEL[algo], variable=var).pack(side="left", padx=(0, 14))

        btn_row1 = ttk.Frame(top)
        btn_row1.pack(fill="x", pady=(6, 0))
        self.btn_add_files = ttk.Button(btn_row1, text=tr("menu_add_files"), command=self.add_files_dialog)
        self.btn_add_folder = ttk.Button(btn_row1, text=tr("menu_add_folder"), command=self.add_folder_dialog)
        self.btn_clear = ttk.Button(btn_row1, text=tr("btn_clear"), command=self.clear_list)
        self.btn_remove = ttk.Button(btn_row1, text=tr("btn_remove"), command=self.remove_selected)
        self.btn_export = ttk.Button(btn_row1, text=tr("menu_export"), command=self.export_results)
        self.btn_compare = ttk.Button(btn_row1, text=tr("menu_compare"), command=self.open_compare)
        for btn in (self.btn_add_files, self.btn_add_folder, self.btn_clear, self.btn_remove, self.btn_export, self.btn_compare):
            btn.pack(side="left", padx=(0, 6), ipadx=3)

        btn_row2 = ttk.Frame(top)
        btn_row2.pack(fill="x", pady=(6, 0))
        self.btn_start = ttk.Button(btn_row2, text=tr("btn_start"), command=self.start_compute,
                                    style="Accent.TButton")
        self.btn_cancel = ttk.Button(btn_row2, text=tr("btn_cancel"), command=self.cancel_compute,
                                     state="disabled", style="Danger.TButton")
        self.btn_start.pack(side="left", padx=(0, 6), ipadx=3)
        self.btn_cancel.pack(side="left", padx=(0, 6), ipadx=3)
        ttk.Label(btn_row2, text=tr("lbl_threads")).pack(side="left", padx=(14, 0))
        self.var_threads = tk.StringVar(value=tr("threads_auto"))
        self.cb_threads = ttk.Combobox(
            btn_row2, textvariable=self.var_threads, state="readonly", width=12,
            values=(tr("threads_auto"), "1", "2", "4"),
        )
        self.cb_threads.pack(side="left", padx=(0, 6))
        ttk.Label(btn_row2, text=tr("hint_dnd"), style="Hint.TLabel").pack(side="right")

        # ---------- 中部：文件列表与结果表格 ----------
        mid = ttk.Frame(root)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        self.columns = ("name", "path", "size") + ALGOS + ("elapsed", "status")
        self.tree = ttk.Treeview(mid, columns=self.columns, show="headings", selectmode="extended")
        titles = {"name": tr("col_name"), "path": tr("col_path"), "size": tr("col_size"),
                  "elapsed": tr("col_elapsed"), "status": tr("col_status")}
        widths = {"name": 180, "path": 340, "size": 90, "elapsed": 80, "status": 200}
        for c in self.columns:
            self.tree.heading(c, text=titles.get(c, "") or LABEL.get(c, c))
            self.tree.column(c, width=widths.get(c, 250), minwidth=40, stretch=(c == "path"), anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)
        self.tree.tag_configure("error", foreground=C_RED)
        self.tree.tag_configure("cancelled", foreground=C_GRAY)
        self.tree.tag_configure("computing", foreground=C_ORANGE)
        self.tree.tag_configure("even", background=_ZEBRA_BG)  # 斑马纹，仅设背景，可与状态标签叠加
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)

        # ---------- 底部：进度条 + 状态栏 ----------
        bottom = ttk.Frame(root, padding=(8, 0, 8, 6))
        bottom.pack(fill="x")
        ttk.Separator(bottom, orient="horizontal").pack(fill="x", pady=(0, 6))
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status_var, anchor="w", style="Status.TLabel").pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------ 拖拽

    def _setup_dnd(self) -> None:
        try:
            from dnd import DropTarget

            self.drop_target = DropTarget(self.root, self._on_drop)
            if not self.drop_target.attach():
                self.drop_target = None
        except Exception:
            self.drop_target = None

    def _on_drop(self, paths) -> None:
        self.add_paths(paths)

    # ------------------------------------------------------------------ 添加/移除文件

    def add_paths(self, paths) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.status(tr("st_busy_add"))
            return
        if self._scanning:
            self.status(tr("st_busy_scan"))
            return
        if any(os.path.isdir(p) for p in paths):
            # 目录递归遍历可能耗时（大目录），放后台线程，结果经队列回主线程，避免界面冻结。
            # 队列用局部引用随轮询传递：扫描结束到结果被消费之间有窗口期，
            # 若挂到 self 上，窗口期内的下一次扫描会顶掉引用、丢失前一次结果。
            self.status(tr("st_busy_scan"))
            self._scanning = True
            scan_q: queue.Queue = queue.Queue()
            self.add_worker = threading.Thread(
                target=lambda: scan_q.put(hash_core.collect_files(paths)),
                daemon=True,
            )
            self.add_worker.start()
            self.root.after(50, lambda: self._poll_add(scan_q))
        else:
            self._finish_add(*hash_core.collect_files(paths))

    def _poll_add(self, scan_q: queue.Queue) -> None:
        try:
            collected = scan_q.get_nowait()
        except queue.Empty:
            self.root.after(50, lambda: self._poll_add(scan_q))
            return
        self.add_worker = None
        self._scanning = False  # 结果消费完毕才算扫描结束，窗口期内 _scanning 保持拦截
        self._finish_add(*collected)

    def _finish_add(self, files, errors) -> None:
        added = 0
        for f in files:
            key = os.path.normcase(os.path.normpath(f))
            if key in self._seen:
                continue
            self._seen.add(key)
            self.files.append(f)
            # 斑马纹取文件序号（O(1)）；不要每行都 get_children() 数行数（每次 O(n)，累计 O(n²)）
            self.tree.insert(
                "", "end", iid=f,
                values=self._empty_row(f, tr("st_waiting")),
                tags=self._zebra(len(self.files) - 1),
            )
            added += 1
        msg = tr("st_added", added=added, total=len(self.files))
        if errors:
            msg += tr("st_added_errors", n=len(errors))
            self.status(msg)
            messagebox.showwarning(
                tr("warn_partial_title"),
                "\n".join(errors[:5]) + ("\n…" if len(errors) > 5 else ""),
                parent=self.root,
            )
        else:
            self.status(msg)

    def add_files_dialog(self) -> None:
        paths = filedialog.askopenfilenames(parent=self.root, title=tr("menu_add_files"))
        if paths:
            self.add_paths(paths)

    def add_folder_dialog(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title=tr("menu_add_folder"))
        if path:
            self.add_paths([path])

    def clear_list(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if self._scanning:
            # 扫描结果尚未回插，此时清空会被随后到达的结果“复活”，先拦截
            self.status(tr("st_busy_scan"))
            return
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self._seen.clear()
        self.results.clear()
        self.tracker = hash_core.ProgressTracker()
        self.total_files = 0
        self.progress["value"] = 0
        self.status(tr("st_cleared"))

    def remove_selected(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if self._scanning:
            # 与 clear_list 同理：被移除的文件若在本次扫描范围内，结果回插时会被“复活”，先拦截
            self.status(tr("st_busy_scan"))
            return
        iids = self.tree.selection()
        if not iids:
            self.status(tr("st_none_selected"))
            return
        for iid in iids:
            self.tree.delete(iid)
            self._seen.discard(os.path.normcase(os.path.normpath(iid)))
            if iid in self.files:
                self.files.remove(iid)
            self.results.pop(iid, None)
        self._retag_zebra()
        self.status(tr("st_removed", n=len(iids), total=len(self.files)))

    # ------------------------------------------------------------------ 计算

    def checked_algorithms(self) -> list[str]:
        return [a for a in ALGOS if self.algo_vars[a].get()]

    def start_compute(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if self._scanning:
            self.status(tr("st_busy_scan"))
            return
        algos = self.checked_algorithms()
        if not self.files:
            messagebox.showwarning(tr("msg_warn"), tr("warn_no_files"), parent=self.root)
            return
        if not algos:
            messagebox.showwarning(tr("msg_warn"), tr("warn_no_algos"), parent=self.root)
            return
        for f in self.files:
            self.tree.item(
                f, values=self._empty_row(f, tr("st_waiting")),
                tags=self._zebra(self.tree.index(f)),
            )
        self.results.clear()
        self.tracker = hash_core.ProgressTracker()
        self.total_files = len(self.files)
        self.progress["value"] = 0
        self.cancel_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.compute_start = time.perf_counter()
        self._set_computing(True)
        self.status(tr("st_started"))
        threads_sel = self.var_threads.get()
        max_threads = int(threads_sel) if threads_sel.isdigit() else None
        self.worker = threading.Thread(
            target=self._compute_worker,
            args=(list(self.files), algos, self.cancel_event, self.msg_queue, max_threads),
            daemon=True,
        )
        self.worker.start()
        self.root.after(50, self._poll_queue)

    @staticmethod
    def _resolve_worker_count(file_count: int, max_threads: int | None = None) -> int:
        """解析并行线程数：显式指定则按指定值，否则自动（不超过 4、CPU 核数与文件数）。"""
        if max_threads:
            return max(1, min(int(max_threads), file_count))
        return max(1, min(4, os.cpu_count() or 1, file_count))

    @staticmethod
    def _compute_worker(files, algos, cancel_event, msg_queue, max_threads: int | None = None) -> None:
        """多文件并行计算：hashlib 处理大块数据时会释放 GIL，多线程可获得真实的多核加速。"""
        try:
            total_bytes = 0
            for f in files:
                try:
                    if os.path.isfile(f):
                        total_bytes += os.path.getsize(f)
                except OSError:
                    pass
            msg_queue.put(("total", len(files), total_bytes))

            def compute_one(path: str) -> hash_core.HashResult:
                msg_queue.put(("start", path))
                calc = hash_core.HashCalculator(
                    algos,
                    cancel_event=cancel_event,
                    progress_callback=lambda p, done, size: msg_queue.put(("progress", p, done, size)),
                )
                return calc.compute_file(path)

            workers = HashToolApp._resolve_worker_count(len(files), max_threads)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_path = {pool.submit(compute_one, f): f for f in files}
                for future in as_completed(future_to_path):
                    try:
                        result = future.result()
                    except Exception as exc:  # compute_file 不应抛异常，兜底防止结果丢失
                        result = hash_core.HashResult(path=future_to_path[future], error=tr("err_compute", exc=exc))
                    msg_queue.put(("result", result))
        finally:
            # 兜底：worker 内任何意外异常都必须发送 done，否则界面永久卡在“计算中”
            msg_queue.put(("done",))

    def cancel_compute(self) -> None:
        if self.cancel_event is not None and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.status(tr("st_cancelling"))

    def _set_computing(self, computing: bool) -> None:
        state = ["disabled"] if computing else ["!disabled"]
        for btn in (self.btn_add_files, self.btn_add_folder, self.btn_clear, self.btn_remove,
                    self.btn_start, self.btn_export, self.btn_compare):
            btn.state(state)
        self.btn_cancel.state(["!disabled"] if computing else ["disabled"])
        # 线程数在计算开始时读取，计算期间锁定下拉框，避免误以为即时生效
        self.cb_threads.configure(state="disabled" if computing else "readonly")

    def _poll_queue(self) -> None:
        finished = False
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "total":
                    self.total_files = msg[1]
                    self.tracker.set_total(msg[2])
                elif kind == "start":
                    self._mark_computing(msg[1])
                elif kind == "progress":
                    self.tracker.on_progress(msg[1], msg[2])
                    self._update_progress()
                elif kind == "result":
                    self._apply_result(msg[1])
                elif kind == "done":
                    finished = True
        except queue.Empty:
            pass
        if finished:
            self._finish_compute()
        else:
            self.root.after(50, self._poll_queue)

    def _mark_computing(self, path: str) -> None:
        self.tree.item(
            path, values=self._empty_row(path, tr("st_computing")),
            tags=self._zebra(self.tree.index(path)) + ("computing",),
        )

    def _render_row(self, r: hash_core.HashResult) -> None:
        """按当前语言渲染一行结果（不触碰进度核算，供语言切换后重绘使用）。"""
        size_str = hash_core.human_size(r.size) if (r.size or r.ok) else ""
        hashes = tuple(r.get(a) for a in ALGOS)
        zebra = self._zebra(self.tree.index(r.path))
        if r.error:
            values = (os.path.basename(r.path), r.path, size_str, *hashes, "",
                      tr("st_error_fmt", msg=r.error))
            tags = zebra + ("error",)
        elif r.cancelled:
            values = (os.path.basename(r.path), r.path, size_str, *hashes, "", tr("st_cancelled"))
            tags = zebra + ("cancelled",)
        else:
            elapsed_str = f"{r.elapsed:.2f} s" if r.elapsed >= 1 else f"{r.elapsed * 1000:.0f} ms"
            values = (os.path.basename(r.path), r.path, size_str, *hashes, elapsed_str, tr("st_done"))
            tags = zebra
        self.tree.item(r.path, values=values, tags=tags)

    def _apply_result(self, r: hash_core.HashResult) -> None:
        self.results[r.path] = r
        self.tracker.on_result(r)
        self._render_row(r)
        self._update_progress()

    def _update_progress(self) -> None:
        if self.tracker.total_bytes > 0:
            pct = self.tracker.percent
            self.progress["value"] = pct
            self.status_var.set(tr("st_computing_pct", pct=pct, done=self.tracker.finished_count,
                                   total=self.total_files))
        else:
            self.status_var.set(tr("st_computing_count", done=self.tracker.finished_count,
                                   total=self.total_files))

    def _finish_compute(self) -> None:
        self._set_computing(False)
        self.worker = None
        elapsed = time.perf_counter() - self.compute_start
        ok_n = sum(1 for r in self.results.values() if r.ok)
        err_n = sum(1 for r in self.results.values() if r.error)
        canc_n = sum(1 for r in self.results.values() if r.cancelled)
        if canc_n:
            msg = tr("st_done_cancelled", ok=ok_n, total=self.total_files, secs=elapsed)
        elif err_n:
            msg = tr("st_done_errors", total=self.total_files, ok=ok_n, err=err_n, secs=elapsed)
        else:
            msg = tr("st_done_ok", total=self.total_files,
                     size=hash_core.human_size(self.tracker.finished_bytes), secs=elapsed)
        if not canc_n and ok_n == self.total_files:
            self.progress["value"] = 100
        self.status(msg)

    # ------------------------------------------------------------------ 复制

    def _on_double_click(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row or not col:
            return
        self._copy_cell(row, int(col[1:]) - 1)

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        # 点击位置在最后一列右侧的空白区域时 identify_column 返回 ""，需防御
        col = self.tree.identify_column(event.x)
        col_idx = int(col[1:]) - 1 if col.startswith("#") else -1
        values = self.tree.item(iid, "values")
        cell_text = values[col_idx] if 0 <= col_idx < len(values) else ""
        menu = _styled_menu(self.root)
        if cell_text:
            menu.add_command(label=tr("ctx_copy_cell"), command=lambda: self._copy_cell(iid, col_idx))
        menu.add_command(label=tr("ctx_copy_row"), command=lambda: self._copy_row_hashes(iid))
        menu.add_separator()
        menu.add_command(label=tr("ctx_open_folder"), command=lambda: self._open_in_explorer(iid))
        # 计算进行中 remove_row 不会执行，直接置灰让行为可预期（与添加按钮的禁用一致）
        busy = self.worker is not None and self.worker.is_alive()
        menu.add_command(label=tr("ctx_remove"), command=lambda: self.remove_row(iid),
                         state="disabled" if busy else "normal")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_cell(self, iid, col_idx) -> None:
        values = self.tree.item(iid, "values")
        text = values[col_idx] if 0 <= col_idx < len(values) else ""
        if text and self._copy_to_clipboard(text):
            self.status(tr("st_copied", text=text))

    def _copy_row_hashes(self, iid) -> None:
        result = self.results.get(iid)
        if result is None or not result.ok:
            self.status(tr("st_not_computed"))
            return
        text = "\n".join(f"{LABEL[a]}: {result.get(a)}" for a in ALGOS if result.get(a))
        if text and self._copy_to_clipboard(text):
            self.status(tr("st_copied_row"))

    def _open_in_explorer(self, iid) -> None:
        if not os.path.exists(iid):
            self.status(tr("st_not_found"))
            return
        try:
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(iid)}"])
        except OSError as exc:
            messagebox.showerror(tr("msg_error"), tr("err_open_explorer", err=exc), parent=self.root)

    def remove_row(self, iid) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if self._scanning:
            self.status(tr("st_busy_scan"))
            return
        self.tree.delete(iid)
        self._seen.discard(os.path.normcase(os.path.normpath(iid)))
        if iid in self.files:
            self.files.remove(iid)
        self.results.pop(iid, None)
        self._retag_zebra()
        self.status(tr("st_removed", n=1, total=len(self.files)))

    # ------------------------------------------------------------------ 导出

    def export_results(self) -> None:
        if not any(r.ok for r in self.results.values()):
            messagebox.showwarning(tr("msg_warn"), tr("warn_no_results"), parent=self.root)
            return
        # 防重入：对话框已打开则提到前台，避免连按 Ctrl+S 叠出多个各自抢 grab 的对话框
        if self.export_dlg is not None and self.export_dlg.winfo_exists():
            self.export_dlg.lift()
            return
        self.export_dlg = ExportDialog(self.root, self.results, self.checked_algorithms())

    # ------------------------------------------------------------------ 对比窗口

    def open_compare(self) -> None:
        if self.compare_win is not None and self.compare_win.winfo_exists():
            self.compare_win.deiconify()
            self.compare_win.lift()
            return
        self.compare_win = CompareWindow(self.root)
        self.compare_win.bind("<Destroy>", self._on_compare_closed, add="+")

    def _on_compare_closed(self, event) -> None:
        if event.widget is self.compare_win:
            self.compare_win = None

    # ------------------------------------------------------------------ 其他

    def _show_help(self) -> None:
        messagebox.showinfo(tr("menu_help_item"), tr("help_text"), parent=self.root)

    def _show_about(self) -> None:
        messagebox.showinfo(
            tr("menu_about"),
            tr("about_text", title=tr("app_title"), version=APP_VERSION),
            parent=self.root,
        )

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(tr("confirm_exit_title"), tr("confirm_exit_msg"), parent=self.root):
                return
            if self.cancel_event is not None:
                self.cancel_event.set()
        if self.drop_target is not None:
            self.drop_target.detach()
        self.root.destroy()

    # ------------------------------------------------------------------ 语言

    def switch_language(self, lang: str) -> None:
        """切换界面语言：立即重建主窗口与对比窗口，并持久化选择。"""
        set_lang(lang)
        save_config(lang)
        self.apply_language()
        if self.compare_win is not None and self.compare_win.winfo_exists():
            self.compare_win.apply_language()
        self.status(tr("st_lang_changed", lang=LANGUAGES.get(lang, lang)))

    def apply_language(self) -> None:
        """按当前语言重建主界面，保留文件列表、计算结果与勾选状态。"""
        saved_algos = self.checked_algorithms()
        saved_threads = self.var_threads.get()
        saved_progress = self.progress["value"]
        computing = self.worker is not None and self.worker.is_alive()
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                continue  # 对比窗口是独立 Toplevel，由 compare_win.apply_language 单独刷新
            w.destroy()
        self._build_menu()
        self._build_ui()
        self.root.title(f"{tr('app_title')} v{APP_VERSION}")
        for a in saved_algos:
            self.algo_vars[a].set(True)
        # 数字选项原样恢复；"自动"必须用新语言的文案，否则显示陈旧语言的文本
        self.var_threads.set(saved_threads if saved_threads.isdigit() else tr("threads_auto"))
        self.progress["value"] = saved_progress
        for i, f in enumerate(self.files):
            self.tree.insert(
                "", "end", iid=f,
                values=self._empty_row(f, tr("st_waiting")),
                tags=self._zebra(i),
            )
        for r in self.results.values():
            if self.tree.exists(r.path):
                self._render_row(r)
        if computing:
            # 重建把所有行重置为“等待计算”，给仍在计算中的文件补回“计算中”状态
            for path in self.tracker.in_progress:
                if self.tree.exists(path):
                    self._mark_computing(path)
        self._set_computing(computing)


class ExportDialog(tk.Toplevel):
    """导出结果对话框：CSV 或 TXT（标准 SUM 格式）。"""

    def __init__(self, master, results, checked_algos):
        super().__init__(master)
        self.title(tr("dlg_export_title"))
        self.resizable(False, False)
        self.transient(master)
        self.configure(background=PAPER)
        self.results = results
        self.algos = checked_algos or list(ALGOS)
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=tr("dlg_format")).grid(row=0, column=0, sticky="w")
        self.fmt = tk.StringVar(value="csv")
        ttk.Radiobutton(f, text=tr("dlg_csv_opt"), variable=self.fmt, value="csv").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Radiobutton(f, text=tr("dlg_txt_opt"), variable=self.fmt, value="txt").grid(row=2, column=0, sticky="w", pady=2)
        row3 = ttk.Frame(f)
        row3.grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(row3, text=tr("dlg_txt_algo")).pack(side="left")
        self.var_algo = tk.StringVar(value=LABEL[self.algos[0]])
        cb = ttk.Combobox(row3, textvariable=self.var_algo, state="readonly", width=10,
                          values=[LABEL[a] for a in self.algos])
        cb.pack(side="left", padx=6)
        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, pady=(14, 0))
        ttk.Button(btns, text=tr("dlg_btn_export"), command=self.do_export).pack(side="left", padx=4)
        ttk.Button(btns, text=tr("dlg_btn_cancel"), command=self.destroy).pack(side="left", padx=4)
        self.grab_set()

    def do_export(self) -> None:
        try:
            if self.fmt.get() == "csv":
                content = hash_core.format_export_csv(self.results.values(), self.algos)
                path = filedialog.asksaveasfilename(
                    parent=self, title=tr("dlg_export_csv_title"), defaultextension=".csv",
                    initialfile=tr("dlg_initial_csv"), filetypes=[("CSV", "*.csv")],
                )
                if not path:
                    return
                with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                    fh.write(content)
            else:
                algo_label = self.var_algo.get()
                algo = next((a for a in self.algos if LABEL[a] == algo_label), None)
                if algo is None:
                    messagebox.showwarning(tr("msg_warn"), tr("dlg_pick_algo"), parent=self)
                    return
                content = hash_core.format_export_txt(self.results.values(), algo)
                path = filedialog.asksaveasfilename(
                    parent=self, title=tr("dlg_export_txt_title"), defaultextension=".txt",
                    initialfile=tr("dlg_initial_txt", algo=LABEL[algo]), filetypes=[("TXT", "*.txt")],
                )
                if not path:
                    return
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
        except OSError as exc:
            messagebox.showerror(tr("msg_error"),
                                 tr("dlg_fail", err=hash_core.describe_error(exc, getattr(exc, "filename", ""))),
                                 parent=self)
            return
        self.destroy()
        messagebox.showinfo(tr("dlg_ok_title"), tr("dlg_ok_msg", path=path), parent=self.master)


class CompareWindow(tk.Toplevel):
    """哈希对比窗口：单文件校验 / 两文件互比 / 批量比对。"""

    def __init__(self, master):
        super().__init__(master)
        self.title(tr("cw_title"))
        self.minsize(780, 540)
        self.configure(background=PAPER)
        HashToolApp._center(self, 880, 660)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_verify = VerifyTab(self.nb)
        self.tab_two = TwoFileTab(self.nb)
        self.tab_batch = BatchTab(self.nb)
        self.nb.add(self.tab_verify, text=tr("tab_verify"))
        self.nb.add(self.tab_two, text=tr("tab_two"))
        self.nb.add(self.tab_batch, text=tr("tab_batch"))
        self.bind("<Destroy>", self._on_destroy)

    def apply_language(self) -> None:
        """按新语言重建三个标签页，恢复用户输入与已有批量结果。"""
        self.title(tr("cw_title"))
        v_file = self.tab_verify.var_file.get()
        v_hash = self.tab_verify.var_hash.get()
        # 与 _on_destroy 一致：重建前统一取消三个标签页的后台线程，
        # 否则被遗漏的 worker 会白算剩余文件，并向已销毁的控件发消息
        for tab in (self.tab_verify, self.tab_two, self.tab_batch):
            if tab.cancel_event is not None:
                tab.cancel_event.set()
        t_a = self.tab_two.var_file_a.get()
        t_b = self.tab_two.var_file_b.get()
        t_algos = self.tab_two._checked()
        b_list = self.tab_batch.var_list.get()
        b_dir = self.tab_batch.var_dir.get()
        b_results = self.tab_batch.results
        self.tab_verify.destroy()
        self.tab_two.destroy()
        self.tab_batch.destroy()
        self.tab_verify = VerifyTab(self.nb)
        self.tab_two = TwoFileTab(self.nb)
        self.tab_batch = BatchTab(self.nb)
        self.nb.add(self.tab_verify, text=tr("tab_verify"))
        self.nb.add(self.tab_two, text=tr("tab_two"))
        self.nb.add(self.tab_batch, text=tr("tab_batch"))
        self.tab_verify.var_file.set(v_file)
        self.tab_verify.var_hash.set(v_hash)
        self.tab_two.var_file_a.set(t_a)
        self.tab_two.var_file_b.set(t_b)
        for a in t_algos:
            self.tab_two.alg_vars[a].set(True)
        self.tab_batch.var_list.set(b_list)
        self.tab_batch.var_dir.set(b_dir)
        self.tab_batch.results = b_results
        if b_results:
            self.tab_batch._fill_results()
            self.tab_batch.btn_export.state(["!disabled"])

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        for tab in (self.tab_verify, self.tab_two, self.tab_batch):
            if tab.cancel_event is not None:
                tab.cancel_event.set()


class VerifyTab(ttk.Frame):
    """模式一：单文件校验——粘贴哈希值，自动识别算法并与文件计算结果对比。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root = self.winfo_toplevel()
        self.queue: queue.Queue = queue.Queue()
        self.worker = None
        self.cancel_event = None
        frame = ttk.LabelFrame(self, text=tr("vf_frame"), padding=10)
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=tr("vf_lbl_file")).grid(row=0, column=0, sticky="e", pady=4)
        self.var_file = tk.StringVar()
        ttk.Entry(frame, textvariable=self.var_file).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text=tr("vf_btn_browse"), command=self._browse).grid(row=0, column=2)
        ttk.Label(frame, text=tr("vf_lbl_hash")).grid(row=1, column=0, sticky="e", pady=4)
        self.var_hash = tk.StringVar()
        ttk.Entry(frame, textvariable=self.var_hash, width=60).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text=tr("vf_btn_paste"), command=self._paste).grid(row=1, column=2, padx=(6, 0))
        self.var_hash.trace_add("write", lambda *_: self._update_hint())
        self.var_alg = tk.StringVar(value=tr("vf_alg_none", hint=tr("vf_alg_hint")))
        self.lbl_alg = ttk.Label(frame, textvariable=self.var_alg, foreground=MUTED)
        self.lbl_alg.grid(row=2, column=1, sticky="w", padx=6)
        btns = ttk.Frame(frame)
        btns.grid(row=3, column=0, columnspan=3, pady=(8, 0))
        self.btn_start = ttk.Button(btns, text=tr("vf_btn_start"), command=self.start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_cancel = ttk.Button(btns, text=tr("dlg_btn_cancel"), command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)
        res = ttk.LabelFrame(self, text=tr("vf_result_frame"), padding=12)
        res.pack(fill="both", expand=True, pady=(10, 0))
        self.var_result = tk.StringVar(value="")
        self.lbl_result = ttk.Label(res, textvariable=self.var_result,
                                    font=(_UI_FONT, 16, "bold"), anchor="center")
        self.lbl_result.pack(fill="x")
        self.var_detail = tk.StringVar(value="")
        ttk.Label(res, textvariable=self.var_detail, anchor="center", justify="center").pack(fill="x", pady=(10, 0))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(parent=self, title=tr("dlg_pick_file"))
        if path:
            self.var_file.set(path)

    def _paste(self) -> None:
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showwarning(tr("msg_warn"), tr("vf_warn_empty_clip"), parent=self)
            return
        if text:
            self.var_hash.set(text)

    def _update_hint(self) -> None:
        algo = hash_core.detect_algorithm(self.var_hash.get())
        if algo:
            self.var_alg.set(tr("vf_alg_known", algo=LABEL[algo]))
            self.lbl_alg.configure(foreground=C_GREEN)
        else:
            self.var_alg.set(tr("vf_alg_none", hint=tr("vf_alg_hint")))
            self.lbl_alg.configure(foreground=MUTED)

    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        path = self.var_file.get().strip()
        raw = self.var_hash.get().strip()
        if not path:
            messagebox.showwarning(tr("msg_warn"), tr("vf_warn_no_file"), parent=self)
            return
        if not raw:
            messagebox.showwarning(tr("msg_warn"), tr("vf_warn_no_hash"), parent=self)
            return
        if not os.path.isfile(path):
            messagebox.showerror(tr("msg_error"), tr("vf_err_file_missing"), parent=self)
            return
        algo = hash_core.detect_algorithm(raw)
        if algo is None:
            self.lbl_result.configure(foreground=C_RED)
            self.var_result.set(tr("vf_res_bad_algo"))
            self.var_detail.set(tr("vf_res_check_len", hint=tr("vf_alg_hint")))
            return
        expected = hash_core.normalize_hash_text(raw)
        self.cancel_event = threading.Event()
        self.btn_start.state(["disabled"])
        self.btn_cancel.state(["!disabled"])
        self.lbl_result.configure(foreground=MUTED)
        self.var_result.set(tr("vf_computing"))
        self.var_detail.set("")
        self.worker = threading.Thread(target=self._worker, args=(path, algo, expected), daemon=True)
        self.worker.start()
        self.after(50, self._poll)

    def _worker(self, path, algo, expected) -> None:
        try:
            result = hash_core.HashCalculator([algo], cancel_event=self.cancel_event).compute_file(path)
            self.queue.put(("result", algo, expected, result))
        finally:
            # 兜底：任何意外异常都必须发送 done，否则界面按钮永久禁用、轮询空转
            self.queue.put(("done",))

    def _poll(self) -> None:
        # after 定时器不随控件销毁而自动取消：先确认标签页仍存在，再触碰控件
        if not self.winfo_exists():
            return
        finished = False
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "result":
                    self._show(*msg[1:])
                else:
                    finished = True
        except queue.Empty:
            pass
        if finished:
            self.worker = None
            self.btn_start.state(["!disabled"])
            self.btn_cancel.state(["disabled"])
        else:
            self.after(50, self._poll)

    def _show(self, algo, expected, result) -> None:
        if result.cancelled:
            self.lbl_result.configure(foreground=MUTED)
            self.var_result.set(tr("vf_res_cancelled"))
            self.var_detail.set("")
            return
        if result.error:
            self.lbl_result.configure(foreground=C_RED)
            self.var_result.set(tr("vf_res_fail"))
            self.var_detail.set(result.error)
            return
        actual = result.get(algo)
        if actual == expected:
            self.lbl_result.configure(foreground=C_GREEN)
            self.var_result.set(tr("vf_res_match"))
        else:
            self.lbl_result.configure(foreground=C_RED)
            self.var_result.set(tr("vf_res_mismatch"))
        self.var_detail.set(tr("vf_detail", algo=LABEL[algo], expected=expected, actual=actual))

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()


class TwoFileTab(ttk.Frame):
    """模式二：两文件互比——直接对比同算法的哈希值是否相同。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root = self.winfo_toplevel()
        self.queue: queue.Queue = queue.Queue()
        self.worker = None
        self.cancel_event = None
        top = ttk.LabelFrame(self, text=tr("tf_frame"), padding=10)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        self.var_file_a = tk.StringVar()
        self.var_file_b = tk.StringVar()
        for row, (title, var) in enumerate(((tr("tf_file_a"), self.var_file_a), (tr("tf_file_b"), self.var_file_b))):
            ttk.Label(top, text=title).grid(row=row, column=0, sticky="e", pady=4)
            ttk.Entry(top, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6)
            ttk.Button(top, text=tr("vf_btn_browse"), command=lambda v=var: self._browse(v)).grid(row=row, column=2)
        algo_row = ttk.Frame(top)
        algo_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(algo_row, text=tr("tf_lbl_algos")).pack(side="left")
        self.alg_vars: dict[str, tk.BooleanVar] = {}
        for algo in ALGOS:
            var = tk.BooleanVar(value=(algo == "sha256"))
            self.alg_vars[algo] = var
            ttk.Checkbutton(algo_row, text=LABEL[algo], variable=var).pack(side="left", padx=(8, 0))
        ttk.Button(algo_row, text=tr("tf_btn_all"), command=lambda: self._set_all(True)).pack(side="left", padx=(12, 0))
        ttk.Button(algo_row, text=tr("tf_btn_none"), command=lambda: self._set_all(False)).pack(side="left", padx=(4, 0))
        btns = ttk.Frame(top)
        btns.grid(row=3, column=0, columnspan=3, pady=(8, 0))
        self.btn_start = ttk.Button(btns, text=tr("tf_btn_start"), command=self.start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_cancel = ttk.Button(btns, text=tr("dlg_btn_cancel"), command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)
        result_frame = ttk.LabelFrame(self, text=tr("tf_result_frame"), padding=8)
        result_frame.pack(fill="both", expand=True, pady=(8, 0))
        # 哈希值用等宽字体显示，便于逐位核对
        self.text = tk.Text(result_frame, height=12, wrap="none", state="disabled",
                            font=(_MONO_FONT, 9), bg=CARD, fg=INK, relief="flat",
                            highlightthickness=1, highlightbackground=LINE, highlightcolor=BLUE,
                            selectbackground=BLUE, selectforeground="#ffffff", padx=6, pady=4)
        vsb = ttk.Scrollbar(result_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self.text.tag_configure("pass", foreground=C_GREEN)
        self.text.tag_configure("fail", foreground=C_RED)
        self.text.tag_configure("head", foreground=MUTED)

    def _browse(self, var) -> None:
        path = filedialog.askopenfilename(parent=self, title=tr("dlg_pick_file"))
        if path:
            var.set(path)

    def _set_all(self, value: bool) -> None:
        for var in self.alg_vars.values():
            var.set(value)

    def _checked(self) -> list[str]:
        return [a for a in ALGOS if self.alg_vars[a].get()]

    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        path_a = self.var_file_a.get().strip()
        path_b = self.var_file_b.get().strip()
        if not path_a or not path_b:
            messagebox.showwarning(tr("msg_warn"), tr("tf_warn_two_files"), parent=self)
            return
        algos = self._checked()
        if not algos:
            messagebox.showwarning(tr("msg_warn"), tr("tf_warn_algos"), parent=self)
            return
        for path in (path_a, path_b):
            if not os.path.isfile(path):
                messagebox.showerror(tr("msg_error"), f"{tr('vf_err_file_missing')}\n{path}", parent=self)
                return
        self.cancel_event = threading.Event()
        self.btn_start.state(["disabled"])
        self.btn_cancel.state(["!disabled"])
        self._write_text(tr("tf_computing") + "\n", "head")
        self.worker = threading.Thread(target=self._worker, args=(path_a, path_b, algos), daemon=True)
        self.worker.start()
        self.after(50, self._poll)

    def _worker(self, path_a, path_b, algos) -> None:
        try:
            result_a = hash_core.HashCalculator(algos, cancel_event=self.cancel_event).compute_file(path_a)
            result_b = hash_core.HashCalculator(algos, cancel_event=self.cancel_event).compute_file(path_b)
            # 算法列表随结果一并回传，避免计算期间用户改动勾选导致显示错乱
            self.queue.put(("result", result_a, result_b, algos))
        finally:
            # 兜底：任何意外异常都必须发送 done，否则界面按钮永久禁用、轮询空转
            self.queue.put(("done",))

    def _poll(self) -> None:
        # after 定时器不随控件销毁而自动取消：先确认标签页仍存在，再触碰控件
        if not self.winfo_exists():
            return
        finished = False
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "result":
                    self._show(msg[1], msg[2], msg[3])
                else:
                    finished = True
        except queue.Empty:
            pass
        if finished:
            self.worker = None
            self.btn_start.state(["!disabled"])
            self.btn_cancel.state(["disabled"])
        else:
            self.after(50, self._poll)

    def _write_text(self, content: str, tag: str = "") -> None:
        self.text.configure(state="normal")
        if tag:
            self.text.insert("end", content, tag)
        else:
            self.text.insert("end", content)
        self.text.configure(state="disabled")

    def _show(self, r_a, r_b, algos) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if r_a.cancelled or r_b.cancelled:
            self._write_text(tr("vf_res_cancelled") + "\n", "head")
            return
        if r_a.error or r_b.error:
            err = r_a.error or r_b.error
            self._write_text(f"✘ {err}\n", "fail")
            return
        diffs = []
        for algo in algos:
            a, b = r_a.get(algo), r_b.get(algo)
            if a != b:
                diffs.append(algo)
        if not diffs:
            self.text.insert("1.0", tr("tf_res_all", n=len(algos)) + "\n\n", "pass")
        else:
            self.text.insert("1.0", tr("tf_res_diff", algos=", ".join(LABEL[a] for a in diffs)) + "\n\n", "fail")
        for algo in algos:
            a, b = r_a.get(algo), r_b.get(algo)
            same = a == b
            self._write_text(f"{LABEL[algo]}: ", "head")
            self._write_text((tr("tf_res_match") if same else tr("tf_res_mismatch")) + "\n",
                             "pass" if same else "fail")
            self._write_text(tr("tf_val_a", h=a) + "\n" + tr("tf_val_b", h=b) + "\n\n")
        self.text.configure(state="disabled")

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()


class BatchTab(ttk.Frame):
    """模式三：批量比对——导入哈希清单，批量校验目录下的文件。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root = self.winfo_toplevel()
        self.queue: queue.Queue = queue.Queue()
        self.worker = None
        self.cancel_event = None
        self.results: list[hash_core.BatchResultItem] = []
        top = ttk.LabelFrame(self, text=tr("bt_frame"), padding=10)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=tr("bt_lbl_list")).grid(row=0, column=0, sticky="e", pady=4)
        self.var_list = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_list).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text=tr("vf_btn_browse"), command=self._browse_list).grid(row=0, column=2)
        ttk.Label(top, text=tr("bt_lbl_dir")).grid(row=1, column=0, sticky="e", pady=4)
        self.var_dir = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_dir).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(top, text=tr("vf_btn_browse"), command=self._browse_dir).grid(row=1, column=2)
        ttk.Label(top, text=tr("bt_hint_format"),
                  foreground=MUTED).grid(row=2, column=1, sticky="w", padx=6, pady=(2, 0))
        btns = ttk.Frame(top)
        btns.grid(row=3, column=0, columnspan=3, pady=(8, 0))
        self.btn_start = ttk.Button(btns, text=tr("bt_btn_start"), command=self.start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_cancel = ttk.Button(btns, text=tr("dlg_btn_cancel"), command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)
        self.btn_export = ttk.Button(btns, text=tr("bt_btn_export"), command=self.export_results, state="disabled")
        self.btn_export.pack(side="left", padx=4)
        self.var_summary = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.var_summary, foreground=C_ORANGE).grid(
            row=4, column=0, columnspan=3, pady=(4, 0))
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("line", "name", "algo", "expected", "actual", "status")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings")
        titles = {"line": tr("col_line"), "name": tr("col_name"), "algo": tr("col_algo"),
                  "expected": tr("col_expected"), "actual": tr("col_actual"), "status": tr("col_status")}
        widths = {"line": 60, "name": 200, "algo": 80, "expected": 240, "actual": 240, "status": 200}
        for c in cols:
            self.tree.heading(c, text=titles[c])
            self.tree.column(c, width=widths[c], minwidth=40,
                             stretch=(c in ("name", "expected", "actual", "status")), anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)
        for tag, color in (("pass", C_GREEN), ("fail", C_RED), ("missing", C_ORANGE), ("cancelled", C_GRAY)):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure("even", background=_ZEBRA_BG)
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill="x", pady=(6, 0))

    def _browse_list(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title=tr("bt_lbl_list"),
            filetypes=[(tr("ft_hash_list"), "*.txt *.md5 *.sha1 *.sha256 *.sha512 *.sum"),
                       (tr("ft_all_files"), "*.*")],
        )
        if path:
            self.var_list.set(path)
            if not self.var_dir.get().strip():
                self.var_dir.set(os.path.dirname(path))

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(parent=self, title=tr("bt_lbl_dir"))
        if path:
            self.var_dir.set(path)

    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        list_path = self.var_list.get().strip()
        base_dir = self.var_dir.get().strip()
        if not list_path or not os.path.isfile(list_path):
            messagebox.showwarning(tr("msg_warn"), tr("bt_warn_list"), parent=self)
            return
        if not base_dir or not os.path.isdir(base_dir):
            messagebox.showwarning(tr("msg_warn"), tr("bt_warn_dir"), parent=self)
            return
        try:
            text = hash_core.read_text_file(list_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr("msg_error"), tr("bt_err_read", err=exc), parent=self)
            return
        items = hash_core.parse_hash_list(text)
        if not items:
            messagebox.showerror(
                tr("msg_error"),
                tr("bt_err_empty",
                   example="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  abc.txt"),
                parent=self,
            )
            return
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.var_summary.set(tr("bt_summary_start", n=len(items)))
        self.progress["value"] = 0
        self.cancel_event = threading.Event()
        self.btn_start.state(["disabled"])
        self.btn_cancel.state(["!disabled"])
        self.btn_export.state(["disabled"])
        self.worker = threading.Thread(target=self._worker, args=(items, base_dir), daemon=True)
        self.worker.start()
        self.after(50, self._poll)

    def _worker(self, items, base_dir) -> None:
        try:
            results = hash_core.verify_batch(
                items,
                base_dir,
                progress_callback=lambda idx, total, done, size: self.queue.put(("progress", idx, total, done, size)),
                cancel_event=self.cancel_event,
            )
            self.queue.put(("result", results))
        finally:
            # 兜底：任何意外异常都必须发送 done，否则界面按钮永久禁用、轮询空转
            self.queue.put(("done",))

    def _poll(self) -> None:
        # after 定时器不随控件销毁而自动取消：先确认标签页仍存在，再触碰控件
        if not self.winfo_exists():
            return
        finished = False
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "progress":
                    _, idx, total, done, size = msg
                    if total > 0:
                        if size > 0:
                            self.progress["value"] = (idx + done / size) / total * 100
                        else:
                            self.progress["value"] = (idx + 1) / total * 100
                elif msg[0] == "result":
                    self.results = msg[1]
                    self._fill_results()
                else:
                    finished = True
        except queue.Empty:
            pass
        if finished:
            self.worker = None
            self.btn_start.state(["!disabled"])
            self.btn_cancel.state(["disabled"])
            if self.results:
                self.btn_export.state(["!disabled"])
        else:
            self.after(50, self._poll)

    def _fill_results(self) -> None:
        counts: dict[str, int] = {}
        for idx, r in enumerate(self.results):
            it = r.item
            status_text = hash_core.batch_status_text(r.status)
            if r.status == "error" and r.error:
                status_text = tr("bt_st_error_fmt", msg=r.error)
            tag = {"pass": "pass", "fail": "fail", "missing": "missing", "error": "fail",
                   "bad_format": "missing", "cancelled": "cancelled"}[r.status]
            zebra = ("even",) if idx % 2 == 0 else ()
            self.tree.insert(
                "", "end", iid=f"row{idx}",
                values=(it.line_no, it.filename, LABEL.get(it.algorithm or "", ""),
                        it.expected_hash, r.actual_hash, status_text),
                tags=zebra + (tag,),
            )
            counts[r.status] = counts.get(r.status, 0) + 1
        self.progress["value"] = 100
        parts = []
        for status, key in (("pass", "bt_st_pass"), ("fail", "bt_st_fail"), ("missing", "bt_st_missing"),
                            ("error", "bt_st_error"), ("bad_format", "bt_st_bad"), ("cancelled", "bt_st_cancelled")):
            if counts.get(status):
                parts.append(f"{tr(key)} {counts[status]}")
        self.var_summary.set(tr("bt_summary_done", parts=", ".join(parts), n=len(self.results)))

    def export_results(self) -> None:
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=tr("bt_export_title"), defaultextension=".csv",
            initialfile=tr("bt_initial_csv"), filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(hash_core.format_batch_csv(self.results))
        except OSError as exc:
            messagebox.showerror(tr("msg_error"), tr("dlg_fail", err=exc), parent=self)
            return
        messagebox.showinfo(tr("dlg_ok_title"), tr("dlg_ok_msg", path=path), parent=self)

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.var_summary.set(tr("bt_cancelling"))


def launch(smoke: bool = False) -> None:
    init_language()
    root, _ = _root_with_style()
    app = HashToolApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    if smoke:
        root.after(1500, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    launch()
