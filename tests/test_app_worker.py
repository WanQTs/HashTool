"""主窗口并行计算工作线程（HashToolApp._compute_worker）的单元测试。

工作线程只依赖文件、算法列表、取消事件与消息队列，无需图形环境即可测试。
"""
import hashlib
import os
import queue
import threading

from app import HashToolApp


def _run_worker(files, algos=("md5", "sha256"), cancel_event=None, max_threads=None):
    """同步运行工作线程，返回队列中的全部消息（以 done 结尾）。"""
    q = queue.Queue()
    HashToolApp._compute_worker(files, list(algos), cancel_event or threading.Event(), q,
                                max_threads=max_threads)
    msgs = []
    while True:
        m = q.get_nowait()
        msgs.append(m)
        if m[0] == "done":
            break
    return msgs


def test_worker_processes_all_files(tmp_path):
    """多个文件全部计算成功，结果按路径与文件一一对应（并行下顺序不定）。"""
    files = []
    for i in range(6):
        p = tmp_path / f"f{i}.bin"
        p.write_bytes(b"abc" * (i + 1))
        files.append(str(p))
    msgs = _run_worker(files)
    kinds = [m[0] for m in msgs]
    assert kinds[0] == "total" and kinds[-1] == "done"
    assert msgs[0][1] == len(files)  # total 消息携带文件总数
    results = {m[1].path: m[1] for m in msgs if m[0] == "result"}
    assert set(results) == set(files)
    assert all(r.ok for r in results.values())
    assert results[files[0]].get("md5") == hashlib.md5(b"abc").hexdigest()
    assert results[files[0]].get("sha256") == hashlib.sha256(b"abc").hexdigest()


def test_worker_marks_start_for_each_file(tmp_path):
    """每个文件都有对应的 start 消息（界面据此标记“计算中”）。"""
    files = []
    for i in range(3):
        p = tmp_path / f"f{i}.bin"
        p.write_bytes(b"x" * 100)
        files.append(str(p))
    msgs = _run_worker(files)
    started = {m[1] for m in msgs if m[0] == "start"}
    assert started == set(files)


def test_worker_cancel_before_start(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    ev = threading.Event()
    ev.set()
    msgs = _run_worker([str(p)], cancel_event=ev)
    results = [m[1] for m in msgs if m[0] == "result"]
    assert len(results) == 1 and results[0].cancelled


def test_worker_missing_file_reports_error(tmp_path):
    """文件不存在时以 HashResult.error 返回，工作线程不抛异常且仍发送 done。"""
    msgs = _run_worker([str(tmp_path / "nope.bin")])
    results = [m[1] for m in msgs if m[0] == "result"]
    assert len(results) == 1 and results[0].error
    assert msgs[-1][0] == "done"


def test_worker_with_explicit_threads(tmp_path):
    """显式指定线程数（1 与 2）时结果与自动模式一致。"""
    files = []
    for i in range(4):
        p = tmp_path / f"f{i}.bin"
        p.write_bytes(b"abc" * (i + 1))
        files.append(str(p))
    for threads in (1, 2):
        msgs = _run_worker(files, max_threads=threads)
        results = {m[1].path: m[1] for m in msgs if m[0] == "result"}
        assert set(results) == set(files)
        assert all(r.ok for r in results.values())
        assert msgs[-1][0] == "done"


def test_resolve_worker_count():
    """线程数解析：自动模式受 4、CPU 核数与文件数约束；显式指定按指定值。"""
    cpu = os.cpu_count() or 1
    assert HashToolApp._resolve_worker_count(3) == min(4, cpu, 3)  # 低核机器上结果随之降低
    assert HashToolApp._resolve_worker_count(100) == min(4, cpu)
    assert HashToolApp._resolve_worker_count(0) == 1
    assert HashToolApp._resolve_worker_count(100, 2) == 2
    assert HashToolApp._resolve_worker_count(1, 4) == 1
    assert HashToolApp._resolve_worker_count(10, 99) == 10


def test_worker_unexpected_error_still_sends_done(tmp_path, monkeypatch):
    """worker 内发生意外异常时也必须发送 done（否则界面轮询空转、按钮永久禁用）。"""
    def _boom(_path):
        raise RuntimeError("boom")

    monkeypatch.setattr("os.path.isfile", _boom)
    q = queue.Queue()
    try:
        HashToolApp._compute_worker([str(tmp_path / "a.bin")], ["md5"], threading.Event(), q)
    except RuntimeError:
        pass  # 异常向外传播由线程 excepthook 记录，关键是 done 必须已发出
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    assert msgs and msgs[-1][0] == "done"
    assert all(m[0] != "result" for m in msgs)


def test_empty_row_matches_column_count():
    """_empty_row 生成的行值个数必须与表格列定义一致（算法列随 ALGOS 适配）。"""
    from app import ALGOS

    row = HashToolApp._empty_row("x.bin", "等待计算")
    assert len(row) == 3 + len(ALGOS) + 2
    assert row[0] == "x.bin" and row[1] == "x.bin" and row[-1] == "等待计算"
