"""GUI 冒烟测试：验证主窗口计算流程与三种对比模式的核心路径。

需要图形环境（Windows 桌面会话）；无显示时自动跳过。测试期间窗口保持隐藏。
"""
import time
import tkinter as tk

import pytest

from app import HashToolApp

EXPECTED_ABC = {
    "md5": "900150983cd24fb0d6963f7d28e17f72",
    "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d",
    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
}


def _pump_until(root, predicate, timeout=15.0):
    """循环驱动 Tk 事件直到 predicate() 为真或超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.02)
    root.update()
    return predicate()


@pytest.fixture
def gui_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("当前环境无法创建图形窗口，跳过 GUI 测试")
    root.withdraw()  # 隐藏窗口，避免测试时闪烁
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def _teardown_app(app, root):
    if app.drop_target is not None:
        app.drop_target.detach()
    if app.worker is not None and app.worker.is_alive():
        app.cancel_event.set()
    root.update()
    root.destroy()


def test_main_window_compute_flow(gui_root, tmp_path):
    """主窗口：添加文件 → 计算 SHA-256 → 结果正确。"""
    f = tmp_path / "abc.txt"
    f.write_bytes(b"abc")
    app = HashToolApp(gui_root)
    try:
        app.add_paths([str(f)])
        assert len(app.files) == 1
        app.start_compute()
        assert _pump_until(gui_root, lambda: app.worker is None and app.results)
        r = app.results[str(f)]
        assert r.ok
        assert r.get("sha256") == EXPECTED_ABC["sha256"]
        assert "计算完成" in app.status_var.get()
    finally:
        _teardown_app(app, gui_root)


def test_verify_tab_single_file(gui_root, tmp_path):
    """模式一：单文件校验，自动识别算法并显示一致。"""
    f = tmp_path / "abc.txt"
    f.write_bytes(b"abc")
    app = HashToolApp(gui_root)
    try:
        app.open_compare()
        tab = app.compare_win.tab_verify
        tab.var_file.set(str(f))
        tab.var_hash.set(EXPECTED_ABC["sha256"])
        tab.start()
        assert _pump_until(gui_root, lambda: tab.worker is None)
        assert "一致" in tab.var_result.get()
        assert EXPECTED_ABC["sha256"] in tab.var_detail.get()
    finally:
        _teardown_app(app, gui_root)


def test_verify_tab_mismatch_shows_red_text(gui_root, tmp_path):
    """模式一：期望值错误时显示不一致。"""
    f = tmp_path / "abc.txt"
    f.write_bytes(b"abc")
    app = HashToolApp(gui_root)
    try:
        app.open_compare()
        tab = app.compare_win.tab_verify
        tab.var_file.set(str(f))
        tab.var_hash.set("9" * 32)  # 32 位长度（识别为 MD5）但内容错误
        tab.start()
        assert _pump_until(gui_root, lambda: tab.worker is None)
        assert "不一致" in tab.var_result.get()
    finally:
        _teardown_app(app, gui_root)


def test_two_file_tab(gui_root, tmp_path):
    """模式二：两个内容相同的文件互比应全部一致。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"abc")
    b.write_bytes(b"abc")
    app = HashToolApp(gui_root)
    try:
        app.open_compare()
        tab = app.compare_win.tab_two
        tab.var_file_a.set(str(a))
        tab.var_file_b.set(str(b))
        tab.start()
        assert _pump_until(gui_root, lambda: tab.worker is None)
        text = tab.text.get("1.0", "end")
        assert "完全相同" in text
    finally:
        _teardown_app(app, gui_root)


def test_batch_tab(gui_root, tmp_path):
    """模式三：批量比对，覆盖通过与文件缺失两种状态。"""
    (tmp_path / "ok.txt").write_bytes(b"abc")
    list_file = tmp_path / "清单.txt"
    list_file.write_text(
        f"{EXPECTED_ABC['md5']}  ok.txt\n{EXPECTED_ABC['md5']}  notexist.txt\n", encoding="utf-8"
    )
    app = HashToolApp(gui_root)
    try:
        app.open_compare()
        tab = app.compare_win.tab_batch
        tab.var_list.set(str(list_file))
        tab.var_dir.set(str(tmp_path))
        tab.start()
        assert _pump_until(gui_root, lambda: tab.worker is None and tab.results)
        summary = tab.var_summary.get()
        assert "通过 1" in summary
        assert "文件缺失 1" in summary
    finally:
        _teardown_app(app, gui_root)


def test_language_switch_to_english_and_back(gui_root, tmp_path):
    """语言切换：界面即时更新为英文（含对比窗口），再切回中文。"""
    import i18n

    app = HashToolApp(gui_root)
    try:
        f = tmp_path / "abc.txt"
        f.write_bytes(b"abc")
        app.add_paths([str(f)])
        app.switch_language("en")
        assert app.root.title().startswith("File Hash")
        assert app.btn_start.cget("text") == "Start (F5)"
        assert app.tree.heading("name")["text"] == "File Name"
        assert app.tree.set(str(f), "status") == "Waiting"
        app.open_compare()
        assert app.compare_win.title() == "Hash Compare"
        assert app.compare_win.tab_verify.btn_start.cget("text") == "Verify"
        app.switch_language("zh")
        assert app.btn_start.cget("text") == "开始计算 (F5)"
        assert app.tree.heading("name")["text"] == "文件名"
        assert app.tree.set(str(f), "status") == "等待计算"
        assert app.compare_win.tab_verify.btn_start.cget("text") == "开始校验"
    finally:
        i18n.set_lang("zh")
        _teardown_app(app, gui_root)


def test_language_switch_thread_combobox_uses_new_language(gui_root):
    """语言切换后线程下拉框：「自动」用新语言文案（不残留旧语言文本），数字选项原样保留。"""
    import i18n

    app = HashToolApp(gui_root)
    try:
        app.var_threads.set("自动（最多 4）")
        app.switch_language("en")
        assert app.var_threads.get() == "Auto (max 4)"
        assert app.var_threads.get() in app.cb_threads.cget("values")
        app.var_threads.set("2")  # 数字选项在切换后原样保留
        app.switch_language("zh")
        assert app.var_threads.get() == "2"
        app.switch_language("en")
        assert app.var_threads.get() == "2"
        app.var_threads.set("Auto (max 4)")
        app.switch_language("zh")
        assert app.var_threads.get() == "自动（最多 4）"
    finally:
        i18n.set_lang("zh")
        _teardown_app(app, gui_root)


def test_add_folder_scans_in_background(gui_root, tmp_path):
    """添加文件夹走后台扫描线程：遍历结果经队列回主线程插入表格，界面不冻结。"""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.txt").write_bytes(b"a")
    (sub / "b.txt").write_bytes(b"b")
    app = HashToolApp(gui_root)
    try:
        app.add_paths([str(tmp_path)])
        assert _pump_until(gui_root, lambda: not app._scanning and len(app.files) == 2)
        assert set(app.tree.get_children()) == set(app.files)
        assert "已添加 2" in app.status_var.get()
    finally:
        _teardown_app(app, gui_root)


def test_scan_window_guards(gui_root, tmp_path):
    """扫描窗口期防御：扫描进行中（含结果待回插）拦截清空、移除、重复添加与开始计算。"""
    f = tmp_path / "a.txt"
    f.write_bytes(b"a")
    app = HashToolApp(gui_root)
    try:
        app.add_paths([str(f)])
        app._scanning = True  # 模拟扫描进行中（含结果待回插的窗口期）
        app.clear_list()
        assert app.files == [str(f)]  # 清空被拦截，避免结果被随后到达的扫描“复活”
        app.tree.selection_set(str(f))
        app.remove_selected()
        assert app.files == [str(f)]  # 移除选中同样被拦截（文件在扫描范围内会被回插“复活”）
        app.remove_row(str(f))
        assert app.files == [str(f)]  # 右键移除单行同样被拦截
        app.add_paths([str(tmp_path / "b.txt")])
        assert app.files == [str(f)]  # 重复添加被拦截
        app.start_compute()
        assert app.worker is None  # 开始计算被拦截
        assert "扫描" in app.status_var.get()
    finally:
        app._scanning = False
        _teardown_app(app, gui_root)
