"""国际化模块：中英双语字符串表（零第三方依赖）。

用法：
    from i18n import tr, set_lang, get_lang, init_language
    tr("key", n=3)              # 按当前语言取字符串并格式化
    set_lang("en")              # 切换语言
    init_language()             # 启动时读取配置/检测系统语言

配置保存在 %APPDATA%\\HashTool\\config.json（1.5.0 之前的中文目录配置自动迁移）；读写失败时静默回退，不影响运行。
"""
from __future__ import annotations

import json
import locale
import os

LANGUAGES: dict[str, str] = {"zh": "中文", "en": "English"}

_current = "zh"

_STRINGS: dict[str, dict[str, str]] = {
    # ---------------- 窗口 / 菜单 ----------------
    "app_title": {"zh": "文件哈希值获取与对比工具", "en": "File Hash Calculator & Verifier"},
    "menu_file": {"zh": "文件", "en": "File"},
    "menu_calc": {"zh": "计算", "en": "Compute"},
    "menu_tools": {"zh": "工具", "en": "Tools"},
    "menu_lang": {"zh": "语言", "en": "Language"},
    "menu_help": {"zh": "帮助", "en": "Help"},
    "menu_add_files": {"zh": "添加文件…", "en": "Add Files…"},
    "menu_add_folder": {"zh": "添加文件夹…", "en": "Add Folder…"},
    "menu_export": {"zh": "导出结果…", "en": "Export Results…"},
    "menu_exit": {"zh": "退出", "en": "Exit"},
    "menu_start": {"zh": "开始计算", "en": "Start"},
    "menu_cancel": {"zh": "取消计算", "en": "Cancel"},
    "menu_compare": {"zh": "哈希对比…", "en": "Hash Compare…"},
    "menu_help_item": {"zh": "使用说明", "en": "Help"},
    "menu_about": {"zh": "关于", "en": "About"},
    # ---------------- 主窗口 ----------------
    "frame_algos": {"zh": " 算法与操作 ", "en": " Algorithms & Actions "},
    "btn_clear": {"zh": "清空列表", "en": "Clear List"},
    "btn_remove": {"zh": "移除选中", "en": "Remove Selected"},
    "btn_start": {"zh": "开始计算 (F5)", "en": "Start (F5)"},
    "btn_cancel": {"zh": "取消计算 (Esc)", "en": "Cancel (Esc)"},
    "lbl_threads": {"zh": "并行线程数：", "en": "Threads:"},
    "threads_auto": {"zh": "自动（最多 4）", "en": "Auto (max 4)"},
    "hint_dnd": {"zh": "提示：支持把文件/文件夹直接拖进窗口", "en": "Hint: drag & drop files or folders here"},
    "col_name": {"zh": "文件名", "en": "File Name"},
    "col_path": {"zh": "完整路径", "en": "Full Path"},
    "col_size": {"zh": "文件大小", "en": "Size"},
    "col_elapsed": {"zh": "耗时", "en": "Time"},
    "col_status": {"zh": "状态", "en": "Status"},
    "st_waiting": {"zh": "等待计算", "en": "Waiting"},
    "st_computing": {"zh": "计算中…", "en": "Computing…"},
    "st_done": {"zh": "完成", "en": "Done"},
    "st_cancelled": {"zh": "已取消", "en": "Cancelled"},
    "st_error_fmt": {"zh": "错误：{msg}", "en": "Error: {msg}"},
    "st_ready": {"zh": "就绪。可点击“添加文件/添加文件夹”，或直接把文件、文件夹拖进窗口。",
                 "en": "Ready. Click \"Add Files\"/\"Add Folder\", or drag & drop files/folders into the window."},
    "st_added": {"zh": "已添加 {added} 个文件，当前共 {total} 个。", "en": "Added {added} file(s); {total} in total."},
    "st_added_errors": {"zh": " 有 {n} 个路径无法读取。", "en": " {n} path(s) could not be read."},
    "warn_partial_title": {"zh": "部分路径无法添加", "en": "Some Paths Could Not Be Added"},
    "st_cleared": {"zh": "列表已清空。", "en": "List cleared."},
    "st_none_selected": {"zh": "未选中任何行。", "en": "No rows selected."},
    "st_removed": {"zh": "已移除 {n} 个文件（当前共 {total} 个）。", "en": "Removed {n} file(s); {total} left."},
    "st_busy_add": {"zh": "正在计算中，请先等待完成或取消后再添加文件。",
                    "en": "Computing in progress; wait or cancel before adding files."},
    "st_busy_scan": {"zh": "正在扫描文件夹，请稍候…", "en": "Scanning folder, please wait…"},
    "st_started": {"zh": "开始计算…", "en": "Started…"},
    "st_cancelling": {"zh": "正在取消…（当前数据块处理完后停止）", "en": "Cancelling… (stops after the current chunk)"},
    "st_computing_pct": {"zh": "正在计算… {pct:.1f}%（已完成 {done}/{total} 个文件）",
                         "en": "Computing… {pct:.1f}% ({done}/{total} files done)"},
    "st_computing_count": {"zh": "正在计算…（已完成 {done}/{total} 个文件）",
                           "en": "Computing… ({done}/{total} files done)"},
    "st_done_cancelled": {"zh": "已取消：完成 {ok}/{total} 个文件，用时 {secs:.1f} 秒。",
                          "en": "Cancelled: {ok}/{total} files done in {secs:.1f}s."},
    "st_done_errors": {"zh": "计算结束：共 {total} 个文件，成功 {ok} 个、失败 {err} 个，用时 {secs:.1f} 秒。失败原因见“状态”列（红色）。",
                       "en": "Finished: {total} files; {ok} OK, {err} failed in {secs:.1f}s. See the red \"Status\" column."},
    "st_done_ok": {"zh": "计算完成：共 {total} 个文件（{size}），全部成功，用时 {secs:.1f} 秒。",
                   "en": "Done: {total} files ({size}) all succeeded in {secs:.1f}s."},
    "st_copied": {"zh": "已复制：{text}", "en": "Copied: {text}"},
    "st_not_computed": {"zh": "该文件尚未计算完成，无法复制。", "en": "This file has not been computed yet."},
    "st_copied_row": {"zh": "已复制该行全部哈希值。", "en": "All hashes of this row copied."},
    "st_copy_fail": {"zh": "复制失败：剪贴板正被其他程序占用，请重试。",
                     "en": "Copy failed: the clipboard is busy, please retry."},
    "st_not_found": {"zh": "文件不存在，无法定位。", "en": "File not found."},
    "st_lang_changed": {"zh": "界面语言已切换为：{lang}", "en": "UI language switched to: {lang}"},
    "ctx_copy_cell": {"zh": "复制此单元格", "en": "Copy This Cell"},
    "ctx_copy_row": {"zh": "复制整行所有哈希", "en": "Copy All Hashes in This Row"},
    "ctx_open_folder": {"zh": "打开文件所在文件夹", "en": "Open Containing Folder"},
    "ctx_remove": {"zh": "从列表移除", "en": "Remove from List"},
    # ---------------- 弹窗通用 ----------------
    "msg_info": {"zh": "提示", "en": "Info"},
    "msg_warn": {"zh": "警告", "en": "Warning"},
    "msg_error": {"zh": "错误", "en": "Error"},
    "warn_no_files": {"zh": "请先添加文件。", "en": "Please add files first."},
    "warn_no_algos": {"zh": "请至少勾选一种哈希算法。", "en": "Select at least one algorithm."},
    "warn_no_results": {"zh": "没有可导出的计算结果，请先计算。", "en": "No results to export. Compute first."},
    "confirm_exit_title": {"zh": "确认退出", "en": "Confirm Exit"},
    "confirm_exit_msg": {"zh": "正在计算中，确定要退出吗？", "en": "Computing in progress. Exit anyway?"},
    # ---------------- 帮助 / 关于 ----------------
    "help_text": {
        "zh": "使用说明\n\n"
              "1. 勾选需要计算的哈希算法（可多选），默认 SHA-256。\n"
              "2. 添加文件：点击“添加文件/添加文件夹”，或直接把文件、文件夹拖进窗口。\n"
              "3. 点击“开始计算”，可随时“取消”；结果显示在表格中。\n"
              "4. 复制哈希：双击某个哈希单元格，或右键选择“复制此单元格”。\n"
              "5. 导出：点击“导出结果”，可导出 CSV 或标准 SUM 格式 TXT。\n"
              "6. 哈希对比：菜单“工具 → 哈希对比”，支持三种模式：\n"
              "   · 单文件校验：粘贴哈希值，按长度自动识别算法并比对；\n"
              "   · 两文件互比：选择两个文件，对比所选算法的哈希是否相同；\n"
              "   · 批量比对：导入哈希清单（每行“哈希值  文件名”），批量校验目录下的文件。\n"
              "7. 语言：菜单“语言”可切换中文 / English，选择会被记住。",
        "en": "Help\n\n"
              "1. Tick the hash algorithms to compute (multi-select); SHA-256 by default.\n"
              "2. Add files: click \"Add Files\"/\"Add Folder\", or drag & drop files/folders into the window.\n"
              "3. Click \"Start\" to compute; \"Cancel\" stops anytime. Results appear in the table.\n"
              "4. Copy a hash: double-click its cell, or right-click and choose \"Copy This Cell\".\n"
              "5. Export: click \"Export Results\" to write CSV or standard SUM-format TXT.\n"
              "6. Compare: menu \"Tools → Hash Compare\" offers three modes:\n"
              "   · Verify Single File: paste a hash; the algorithm is detected by length;\n"
              "   · Compare Two Files: compare the selected algorithms between two files;\n"
              "   · Batch Verify: import a hash list (\"hash  filename\" per line) and verify a folder.\n"
              "7. Language: switch between 中文 / English in the \"Language\" menu; the choice is remembered.",
    },
    "about_text": {
        "zh": "{title}\n\n版本：{version}\n运行环境：Windows 10/11 64 位\n"
              "技术：Python + tkinter，除可选主题库外无第三方运行时依赖",
        "en": "{title}\n\nVersion: {version}\nOS: Windows 10/11 64-bit\n"
              "Tech: Python + tkinter; no third-party runtime dependencies (optional theme lib excluded)",
    },
    # ---------------- 导出对话框 ----------------
    "dlg_export_title": {"zh": "导出计算结果", "en": "Export Results"},
    "dlg_format": {"zh": "导出格式：", "en": "Format:"},
    "dlg_csv_opt": {"zh": "CSV（可用 Excel 打开）", "en": "CSV (opens in Excel)"},
    "dlg_txt_opt": {"zh": "TXT（标准 SUM 格式，可被其他校验工具识别）", "en": "TXT (standard SUM format)"},
    "dlg_txt_algo": {"zh": "TXT 导出算法：", "en": "TXT algorithm:"},
    "dlg_btn_export": {"zh": "导出…", "en": "Export…"},
    "dlg_btn_cancel": {"zh": "取消", "en": "Cancel"},
    "dlg_export_csv_title": {"zh": "导出 CSV", "en": "Export CSV"},
    "dlg_export_txt_title": {"zh": "导出 TXT（SUM 格式）", "en": "Export TXT (SUM format)"},
    "dlg_initial_csv": {"zh": "哈希计算结果.csv", "en": "hash_results.csv"},
    "dlg_initial_txt": {"zh": "哈希结果_{algo}.txt", "en": "hash_{algo}.txt"},
    "dlg_ok_title": {"zh": "导出成功", "en": "Export Succeeded"},
    "dlg_ok_msg": {"zh": "已导出到：\n{path}", "en": "Exported to:\n{path}"},
    "dlg_fail": {"zh": "导出失败：{err}", "en": "Export failed: {err}"},
    "dlg_pick_algo": {"zh": "请选择要导出的算法。", "en": "Select an algorithm to export."},
    # ---------------- 对比窗口 ----------------
    "cw_title": {"zh": "哈希对比", "en": "Hash Compare"},
    "tab_verify": {"zh": " 单文件校验 ", "en": " Verify Single File "},
    "tab_two": {"zh": " 两文件互比 ", "en": " Compare Two Files "},
    "tab_batch": {"zh": " 批量比对 ", "en": " Batch Verify "},
    # -- 模式一：单文件校验 --
    "vf_frame": {"zh": "单文件校验：粘贴哈希值，按长度自动识别算法并与文件计算结果对比",
                 "en": "Verify: paste a hash; the algorithm is detected by length and compared with the file"},
    "vf_lbl_file": {"zh": "文件：", "en": "File:"},
    "vf_lbl_hash": {"zh": "哈希值：", "en": "Hash:"},
    "vf_btn_browse": {"zh": "浏览…", "en": "Browse…"},
    "vf_btn_paste": {"zh": "从剪贴板粘贴", "en": "Paste"},
    "vf_alg_hint": {"zh": "（32=MD5，40=SHA-1，64=SHA-256，128=SHA-512，8=CRC32）",
                    "en": "(32=MD5, 40=SHA-1, 64=SHA-256, 128=SHA-512, 8=CRC32)"},
    "vf_alg_none": {"zh": "算法：未识别 {hint}", "en": "Algorithm: not recognized {hint}"},
    "vf_alg_known": {"zh": "算法：{algo}（已自动识别）", "en": "Algorithm: {algo} (auto-detected)"},
    "vf_btn_start": {"zh": "开始校验", "en": "Verify"},
    "vf_result_frame": {"zh": "校验结果", "en": "Result"},
    "vf_res_match": {"zh": "✔ 一致", "en": "✔ Match"},
    "vf_res_mismatch": {"zh": "✘ 不一致", "en": "✘ Mismatch"},
    "vf_res_cancelled": {"zh": "已取消", "en": "Cancelled"},
    "vf_res_fail": {"zh": "✘ 校验失败：文件无法读取", "en": "✘ Verify failed: file unreadable"},
    "vf_res_bad_algo": {"zh": "✘ 无法识别哈希算法", "en": "✘ Unrecognized hash algorithm"},
    "vf_res_check_len": {"zh": "请检查输入的长度：{hint}", "en": "Check the input length: {hint}"},
    "vf_detail": {"zh": "{algo}\n期望值：{expected}\n计算值：{actual}", "en": "{algo}\nExpected: {expected}\nActual: {actual}"},
    "vf_computing": {"zh": "正在计算文件哈希…", "en": "Computing file hash…"},
    "vf_warn_no_file": {"zh": "请先选择要校验的文件。", "en": "Select a file to verify."},
    "vf_warn_no_hash": {"zh": "请粘贴或输入期望的哈希值。", "en": "Paste or enter the expected hash."},
    "vf_err_file_missing": {"zh": "文件不存在或无法访问。", "en": "File missing or inaccessible."},
    "vf_warn_empty_clip": {"zh": "剪贴板中没有文本内容。", "en": "No text on the clipboard."},
    # -- 模式二：两文件互比 --
    "tf_frame": {"zh": "两文件互比：选择两个文件，对比所选算法的哈希值",
                 "en": "Compare two files with the selected algorithms"},
    "tf_file_a": {"zh": "文件 A：", "en": "File A:"},
    "tf_file_b": {"zh": "文件 B：", "en": "File B:"},
    "tf_lbl_algos": {"zh": "对比算法：", "en": "Algorithms:"},
    "tf_btn_all": {"zh": "全选", "en": "All"},
    "tf_btn_none": {"zh": "全不选", "en": "None"},
    "tf_btn_start": {"zh": "开始对比", "en": "Compare"},
    "tf_result_frame": {"zh": "对比结果", "en": "Result"},
    "tf_computing": {"zh": "正在计算两个文件的哈希…", "en": "Computing hashes of both files…"},
    "tf_res_all": {"zh": "✔ 两个文件完全相同（对比 {n} 个算法均一致）", "en": "✔ Files are identical (all {n} algorithms match)"},
    "tf_res_diff": {"zh": "✘ 存在不一致：{algos}", "en": "✘ Mismatch in: {algos}"},
    "tf_res_match": {"zh": "一致", "en": "Match"},
    "tf_res_mismatch": {"zh": "不一致", "en": "Mismatch"},
    "tf_val_a": {"zh": "  文件 A：{h}", "en": "  File A: {h}"},
    "tf_val_b": {"zh": "  文件 B：{h}", "en": "  File B: {h}"},
    "tf_warn_two_files": {"zh": "请选择两个要对比的文件。", "en": "Select two files to compare."},
    "tf_warn_algos": {"zh": "请至少勾选一种对比算法。", "en": "Select at least one algorithm."},
    # -- 模式三：批量比对 --
    "bt_frame": {"zh": "批量比对：导入哈希清单，校验目录下的文件",
                 "en": "Batch verify: import a hash list and verify files in a folder"},
    "bt_lbl_list": {"zh": "清单文件：", "en": "List file:"},
    "bt_lbl_dir": {"zh": "目标目录：", "en": "Target folder:"},
    "bt_hint_format": {"zh": "清单格式：每行“哈希值  文件名”（兼容 MD5Sum/SHA256SUM 格式），支持 # 注释",
                       "en": "List format: \"hash  filename\" per line (MD5Sum/SHA256SUM compatible); # comments supported"},
    "bt_btn_start": {"zh": "开始比对", "en": "Start"},
    "bt_btn_export": {"zh": "导出比对结果…", "en": "Export results…"},
    "bt_summary_start": {"zh": "清单共 {n} 条，正在比对…", "en": "{n} entries; verifying…"},
    "bt_summary_done": {"zh": "比对完成：{parts}（共 {n} 条）", "en": "Done: {parts} ({n} entries total)"},
    "bt_st_pass": {"zh": "通过", "en": "Passed"},
    "bt_st_fail": {"zh": "失败", "en": "Failed"},
    "bt_st_missing": {"zh": "文件缺失", "en": "Missing"},
    "bt_st_error": {"zh": "错误", "en": "Error"},
    "bt_st_bad": {"zh": "格式错误", "en": "Bad format"},
    "bt_st_cancelled": {"zh": "已取消", "en": "Cancelled"},
    "bt_st_error_fmt": {"zh": "错误：{msg}", "en": "Error: {msg}"},
    "bt_cancelling": {"zh": "正在取消…", "en": "Cancelling…"},
    "bt_warn_list": {"zh": "请选择有效的哈希清单文件。", "en": "Select a valid hash list file."},
    "bt_warn_dir": {"zh": "请选择要校验文件所在的目标目录。", "en": "Select the target folder."},
    "bt_err_read": {"zh": "读取清单文件失败：{err}", "en": "Failed to read list file: {err}"},
    "bt_err_empty": {"zh": "清单中没有解析到有效条目。\n\n格式：每行“哈希值  文件名”，例如：\n{example}",
                     "en": "No valid entries in the list.\n\nFormat: \"hash  filename\" per line, e.g.:\n{example}"},
    "bt_export_title": {"zh": "导出比对结果", "en": "Export Verify Results"},
    "bt_initial_csv": {"zh": "比对结果.csv", "en": "verify_results.csv"},
    "ft_hash_list": {"zh": "清单文件", "en": "Hash List"},
    "ft_all_files": {"zh": "所有文件", "en": "All Files"},
    "dlg_pick_file": {"zh": "选择文件", "en": "Select File"},
    "err_open_explorer": {"zh": "无法打开资源管理器：{err}", "en": "Failed to open Explorer: {err}"},
    "col_line": {"zh": "行号", "en": "Line"},
    "col_algo": {"zh": "算法", "en": "Algorithm"},
    "col_expected": {"zh": "期望哈希", "en": "Expected"},
    "col_actual": {"zh": "实际哈希", "en": "Actual"},
    # ---------------- 核心模块 ----------------
    "err_is_dir": {"zh": "目标是一个文件夹，请添加其中的文件：{path}", "en": "Target is a folder; add the files inside it: {path}"},
    "err_not_found": {"zh": "文件不存在或已被移动：{path}", "en": "File missing or moved: {path}"},
    "err_locked": {"zh": "文件被其他程序占用，无法读取：{path}", "en": "File is in use by another program: {path}"},
    "err_denied": {"zh": "拒绝访问（没有读取权限）：{path}", "en": "Access denied (no read permission): {path}"},
    "err_cant_read": {"zh": "无法读取文件：{path}", "en": "Cannot read file: {path}"},
    "err_read_fail": {"zh": "读取文件出错：{path}（{reason}）", "en": "Read error: {path} ({reason})"},
    "err_generic": {"zh": "{path}：{exc}", "en": "{path}: {exc}"},
    "err_path_missing": {"zh": "路径不存在或无法访问：{p}", "en": "Path missing or inaccessible: {p}"},
    "err_unknown_algo": {"zh": "不支持的哈希算法：{algos}", "en": "Unsupported hash algorithm(s): {algos}"},
    "err_no_algo": {"zh": "至少需要选择一个哈希算法", "en": "Select at least one hash algorithm"},
    "err_bad_encoding": {"zh": "无法识别文件编码，请使用 UTF-8 或 GBK 编码保存：{path}",
                         "en": "Unrecognized file encoding; save as UTF-8 or GBK: {path}"},
    "err_compute": {"zh": "计算出错：{exc}", "en": "Compute error: {exc}"},
    "csv_name": {"zh": "文件名", "en": "File Name"},
    "csv_path": {"zh": "完整路径", "en": "Full Path"},
    "csv_size": {"zh": "大小(字节)", "en": "Size (bytes)"},
    "csv_elapsed": {"zh": "耗时(秒)", "en": "Time (s)"},
    "csv_status": {"zh": "状态", "en": "Status"},
    "csv_done": {"zh": "完成", "en": "Done"},
    "csv_cancelled": {"zh": "已取消", "en": "Cancelled"},
    "csv_error": {"zh": "错误", "en": "Error"},
    "csv_line": {"zh": "清单行号", "en": "List Line"},
    "csv_expected": {"zh": "期望哈希", "en": "Expected"},
    "csv_actual": {"zh": "实际哈希", "en": "Actual"},
    "csv_error_info": {"zh": "错误信息", "en": "Error Info"},
}

_CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "HashTool")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")
# 1.5.0 之前使用的中文配置目录（仅用于启动时迁移）
_LEGACY_CONFIG_PATH = os.path.join(os.path.dirname(_CONFIG_DIR), "哈希工具", "config.json")


def tr(key: str, lang: str | None = None, **kwargs) -> str:
    """按当前（或指定）语言取字符串；支持 {name} 占位符格式化。缺失时回退到中文/键名。"""
    entry = _STRINGS.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(lang or _current, entry.get("zh", key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def set_lang(lang: str) -> None:
    global _current
    if lang in LANGUAGES:
        _current = lang


def get_lang() -> str:
    return _current


def detect_system_language() -> str:
    """按系统用户界面语言检测：中文环境返回 zh，否则 en。"""
    try:
        if os.name == "nt":
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if langid & 0x3FF == 0x04:  # LANG_CHINESE
                return "zh"
    except Exception:
        pass
    loc = (locale.getdefaultlocale()[0] or "").lower()
    return "zh" if loc.startswith("zh") else "en"


def load_config(path: str = _CONFIG_PATH) -> str | None:
    """读取配置中的语言设置；无配置或读取失败返回 None。"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        lang = data.get("language")
        return lang if lang in LANGUAGES else None
    except Exception:
        return None


def save_config(lang: str, path: str = _CONFIG_PATH) -> bool:
    """把语言设置写入配置；失败返回 False（调用方可忽略）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"language": lang}, fh, ensure_ascii=False)
        return True
    except Exception:
        return False


def _migrate_legacy_config() -> None:
    """把旧版中文目录（%APPDATA%\\哈希工具）里的配置迁移到新目录，并清理旧文件与空目录。"""
    try:
        if os.path.exists(_CONFIG_PATH) or not os.path.isfile(_LEGACY_CONFIG_PATH):
            return
        lang = load_config(_LEGACY_CONFIG_PATH)
        if lang is not None and save_config(lang, _CONFIG_PATH):
            os.remove(_LEGACY_CONFIG_PATH)
            try:
                os.rmdir(os.path.dirname(_LEGACY_CONFIG_PATH))  # 仅在目录已清空时移除
            except OSError:
                pass
    except OSError:
        pass


def init_language() -> str:
    """启动时确定语言：优先配置中的选择，其次系统检测，并把检测结果落盘。"""
    _migrate_legacy_config()
    lang = load_config() or detect_system_language()
    if load_config() is None:
        save_config(lang)
    set_lang(lang)
    return lang
