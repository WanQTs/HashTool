"""hash_core 模块单元测试。

用官方已知向量（如 "abc" 的 SHA-256 = ba7816bf…）验证各算法输出，
并覆盖分块读取、取消、算法识别、清单解析、批量校验、导出等功能。
"""
import hashlib
import os
import random
import threading

import pytest

import hash_core
from hash_core import (
    BatchCheckItem,
    HashCalculator,
    HashResult,
    ProgressTracker,
    batch_status_text,
    collect_files,
    describe_error,
    detect_algorithm,
    format_batch_csv,
    format_export_csv,
    format_export_txt,
    human_size,
    normalize_hash_text,
    parse_hash_list,
    read_text_file,
    verify_batch,
)

# "abc" 的官方已知值
EXPECTED_ABC = {
    "md5": "900150983cd24fb0d6963f7d28e17f72",
    "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d",
    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    "sha512": "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
    "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
    "crc32": "352441c2",
}

EXPECTED_EMPTY = {
    "md5": "d41d8cd98f00b204e9800998ecf8427e",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "crc32": "00000000",
}


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ---------------------------------------------------------------------- 计算


@pytest.mark.parametrize("algo,expected", sorted(EXPECTED_ABC.items()))
def test_abc_known_vectors_with_1_byte_chunks(algo, expected, tmp_path):
    """用 1 字节分块验证：各算法对 "abc" 的输出与官方值一致（同时覆盖分块读取）。"""
    p = _write(tmp_path, "abc.bin", b"abc")
    calc = HashCalculator([algo], chunk_size=1)
    r = calc.compute_file(p)
    assert r.error == "" and not r.cancelled
    assert r.hashes[algo] == expected
    assert r.size == 3
    assert r.elapsed >= 0


def test_all_algorithms_in_one_pass(tmp_path):
    p = _write(tmp_path, "abc.bin", b"abc")
    r = HashCalculator(list(EXPECTED_ABC)).compute_file(p)
    assert r.ok
    assert r.hashes == EXPECTED_ABC


@pytest.mark.parametrize("algo,expected", sorted(EXPECTED_EMPTY.items()))
def test_empty_file_vectors(algo, expected, tmp_path):
    p = _write(tmp_path, "empty.bin", b"")
    r = HashCalculator([algo]).compute_file(p)
    assert r.hashes[algo] == expected


def test_large_file_chunked_matches_oneshot(tmp_path):
    """大文件分块计算结果与 hashlib 一次性计算结果一致。"""
    data = bytes(range(256)) * 4096  # 1MB 确定性数据
    p = _write(tmp_path, "big.bin", data)
    r = HashCalculator(["md5", "sha256"], chunk_size=100_000).compute_file(p)
    assert r.hashes["md5"] == hashlib.md5(data).hexdigest()
    assert r.hashes["sha256"] == hashlib.sha256(data).hexdigest()


def test_unknown_algorithm_raises():
    with pytest.raises(ValueError):
        HashCalculator(["md4"])
    with pytest.raises(ValueError):
        HashCalculator([])


def test_missing_file_reports_error_not_exception(tmp_path):
    r = HashCalculator(["md5"]).compute_file(str(tmp_path / "nope.bin"))
    assert r.error and "不存在" in r.error
    assert not r.ok


def test_directory_reports_error(tmp_path):
    r = HashCalculator(["md5"]).compute_file(str(tmp_path))
    assert r.error and "文件夹" in r.error


def test_cancel_before_start(tmp_path):
    ev = threading.Event()
    ev.set()
    p = _write(tmp_path, "a.bin", b"abc")
    r = HashCalculator(["md5"], cancel_event=ev).compute_file(p)
    assert r.cancelled and not r.ok and not r.hashes


def test_cancel_during_compute_stops_after_current_chunk(tmp_path):
    ev = threading.Event()
    p = _write(tmp_path, "a.bin", b"x" * 20_000_000)  # 20MB，跨多个 8MB 分块

    def cb(_path, done, _size):
        if done >= 8 * 1024 * 1024:  # 第一块完成后取消
            ev.set()

    r = HashCalculator(["md5"], cancel_event=ev, progress_callback=cb).compute_file(p)
    assert r.cancelled
    assert not r.hashes


def test_progress_callback_reports_every_chunk(tmp_path):
    p = _write(tmp_path, "a.bin", b"x" * 1000)
    calls = []
    HashCalculator(["md5"], chunk_size=100,
                   progress_callback=lambda _p, d, s: calls.append((d, s))).compute_file(p)
    assert calls[0] == (100, 1000)
    assert calls[-1] == (1000, 1000)


# ---------------------------------------------------------------------- 算法识别


def test_detect_algorithm_by_length():
    assert detect_algorithm("900150983cd24fb0d6963f7d28e17f72") == "md5"
    assert detect_algorithm("a9993e364706816aba3e25717850c26c9cd0d89d") == "sha1"
    assert detect_algorithm("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") == "sha256"
    assert detect_algorithm(EXPECTED_ABC["sha512"]) == "sha512"
    assert detect_algorithm("352441C2") == "crc32"
    assert detect_algorithm("abc") is None
    assert detect_algorithm("") is None


def test_normalize_hash_text_handles_certutil_and_case():
    text = "MD5 (a.txt) = 900150983CD24FB0D6963F7D28E17F72\n"
    assert normalize_hash_text(text) == "900150983cd24fb0d6963f7d28e17f72"
    assert normalize_hash_text("  BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD  ") == \
        EXPECTED_ABC["sha256"]


# ---------------------------------------------------------------------- 清单解析


def test_parse_hash_list_common_formats():
    text = "\n".join([
        "# 注释行",
        "900150983cd24fb0d6963f7d28e17f72  a.txt",
        "a9993e364706816aba3e25717850c26c9cd0d89d *b.bin",
        "MD5 (c 文件.txt) = 900150983cd24fb0d6963f7d28e17f72",
        "352441c2\tsub\\d.txt",
        "",
        "; 另一个注释",
    ])
    items = parse_hash_list(text)
    assert len(items) == 4
    assert items[0].line_no == 2
    assert items[0].algorithm == "md5" and items[0].filename == "a.txt"
    assert items[1].algorithm == "sha1" and items[1].filename == "b.bin"
    assert items[2].algorithm == "md5" and items[2].filename == "c 文件.txt"
    assert items[3].algorithm == "crc32" and items[3].filename == "sub\\d.txt"


def test_parse_hash_list_skips_invalid_lines():
    assert parse_hash_list("hello world") == []
    assert parse_hash_list("a" * 32) == []  # 只有哈希没有文件名


# ---------------------------------------------------------------------- 批量校验


def test_verify_batch_statuses(tmp_path):
    base = tmp_path / "base"
    (base / "sub").mkdir(parents=True)
    (base / "ok.txt").write_bytes(b"abc")
    (base / "bad.txt").write_bytes(b"ABD")
    (base / "sub" / "d.txt").write_bytes(b"abc")
    items = parse_hash_list(
        "900150983cd24fb0d6963f7d28e17f72  ok.txt\n"
        "900150983cd24fb0d6963f7d28e17f72  bad.txt\n"
        "900150983cd24fb0d6963f7d28e17f72  missing.txt\n"
        "352441c2  sub/d.txt\n"
        "abcdef012345  badfmt.txt\n"
    )
    results = verify_batch(items, str(base))
    assert [r.status for r in results] == ["pass", "fail", "missing", "pass", "bad_format"]
    assert results[1].actual_hash == hashlib.md5(b"ABD").hexdigest()


def test_verify_batch_cancel(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"abc")
    items = parse_hash_list("900150983cd24fb0d6963f7d28e17f72  a.txt")
    ev = threading.Event()
    ev.set()
    results = verify_batch(items, str(tmp_path), cancel_event=ev)
    assert all(r.status == "cancelled" for r in results)


def test_verify_batch_progress_callback(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"abc")
    items = parse_hash_list("900150983cd24fb0d6963f7d28e17f72  a.txt")
    calls = []
    verify_batch(items, str(tmp_path), progress_callback=lambda i, t, d, s: calls.append((i, t, d, s)))
    assert calls[-1] == (0, 1, 3, 3)


# ---------------------------------------------------------------------- 文件遍历


def test_collect_files_recursive(tmp_path):
    d = tmp_path / "dir"
    (d / "sub").mkdir(parents=True)
    (d / "a.txt").write_bytes(b"a")
    (d / "sub" / "b.txt").write_bytes(b"b")
    single = tmp_path / "x.bin"
    single.write_bytes(b"x")
    files, errors = collect_files([str(single), str(d), str(tmp_path / "missing")])
    assert sorted(os.path.basename(f) for f in files) == ["a.txt", "b.txt", "x.bin"]
    assert errors and "不存在" in errors[0]


# ---------------------------------------------------------------------- 错误提示


def test_describe_error_locked_file():
    exc = PermissionError(13, "拒绝访问。")
    exc.winerror = 32  # Windows 共享冲突（文件被占用）
    assert "占用" in describe_error(exc, "f.bin")


def test_describe_error_permission():
    exc = PermissionError(13, "denied")
    assert "权限" in describe_error(exc, "f.bin")


# ---------------------------------------------------------------------- 导出


def test_format_export_txt_standard_sum_format(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    results = [
        HashResult(path=str(a), size=3, hashes={"md5": "900150983cd24fb0d6963f7d28e17f72"}, elapsed=0.01),
        HashResult(path=str(b), size=3, hashes={"md5": "900150983cd24fb0d6963f7d28e17f72"}, elapsed=0.01),
    ]
    out = format_export_txt(results, "md5")
    assert out == ("900150983cd24fb0d6963f7d28e17f72  a.txt\n"
                   "900150983cd24fb0d6963f7d28e17f72  b.txt\n")


def test_format_export_txt_skips_failed_rows(tmp_path):
    results = [
        HashResult(path=str(tmp_path / "ok.txt"), size=3,
                   hashes={"md5": "900150983cd24fb0d6963f7d28e17f72"}, elapsed=0.01),
        HashResult(path=str(tmp_path / "bad.txt"), error="拒绝访问"),
    ]
    out = format_export_txt(results, "md5")
    assert "ok.txt" in out and "bad.txt" not in out


def test_format_export_csv(tmp_path):
    results = [HashResult(path=str(tmp_path / "a.txt"), size=3,
                          hashes={"md5": "900150983cd24fb0d6963f7d28e17f72"}, elapsed=0.05)]
    out = format_export_csv(results, ["md5"])
    assert "文件名" in out and "900150983cd24fb0d6963f7d28e17f72" in out and "a.txt" in out


def test_format_batch_csv():
    item = BatchCheckItem(expected_hash="900150983cd24fb0d6963f7d28e17f72",
                          filename="a.txt", algorithm="md5", line_no=1)
    out = format_batch_csv([hash_core.BatchResultItem(item=item, status="pass",
                                                      actual_hash=item.expected_hash)])
    assert "清单行号" in out and "通过" in out and "a.txt" in out


# ---------------------------------------------------------------------- 其他


def test_read_text_file_utf8_and_gbk(tmp_path):
    p_utf8 = tmp_path / "list_utf8.txt"
    p_utf8.write_text("900150983cd24fb0d6963f7d28e17f72  a.txt\n", encoding="utf-8")
    assert "a.txt" in read_text_file(str(p_utf8))
    p_gbk = tmp_path / "list_gbk.txt"
    p_gbk.write_bytes("900150983cd24fb0d6963f7d28e17f72  中文文件.txt\n".encode("gbk"))
    assert "中文文件.txt" in read_text_file(str(p_gbk))


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(1023) == "1023 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(3 * 1024 * 1024 * 1024) == "3.0 GB"


def test_batch_status_text():
    assert batch_status_text("pass") == "通过"
    assert batch_status_text("missing") == "文件缺失"
    assert batch_status_text("unknown") == "unknown"


# ---------------------------------------------------------------------- 进度核算


def _interleave(streams, seed):
    """随机归并多条消息流，保持每条流内部顺序（模拟并行 worker 下各文件消息的乱序到达）。"""
    rnd = random.Random(seed)
    streams = [list(s) for s in streams]
    out = []
    while any(streams):
        idx = rnd.choice([i for i, s in enumerate(streams) if s])
        out.append(streams[idx].pop(0))
    return out


def test_progress_tracker_sequential_reaches_100():
    t = ProgressTracker()
    t.set_total(100)
    t.on_progress("a", 40)
    assert t.percent == 40.0
    t.on_progress("a", 100)
    t.on_result(HashResult(path="a", size=100, hashes={"md5": "x"}))
    assert t.percent == 100.0
    assert t.finished_count == 1
    assert not t.in_progress


def test_progress_tracker_out_of_order_monotonic_and_converges():
    """乱序消息序列：4 个文件的消息随机归并（各自内部有序），进度单调不减且收敛到 100%。"""
    sizes = [100, 200, 300, 400]
    streams = [
        [("progress", path, size // 2), ("progress", path, size),
         ("result", HashResult(path=path, size=size, hashes={"md5": "x"}))]
        for path, size in ((f"f{i}", s) for i, s in enumerate(sizes))
    ]
    for seed in range(20):
        t = ProgressTracker()
        t.set_total(sum(sizes))
        last = 0.0
        for msg in _interleave(streams, seed):
            if msg[0] == "progress":
                t.on_progress(msg[1], msg[2])
            else:
                t.on_result(msg[1])
            assert t.percent >= last  # 成功文件的消息流内部有序：结果到达时 pop/add 守恒
            last = t.percent
        assert t.percent == 100.0
        assert t.finished_count == len(sizes)


def test_progress_tracker_error_file_not_counted():
    """失败文件不计入完成字节：进行中记录被清除，进度不虚增。"""
    t = ProgressTracker()
    t.set_total(100)
    t.on_progress("bad", 40)
    assert t.percent == 40.0
    t.on_result(HashResult(path="bad", error="拒绝访问"))
    assert t.percent == 0.0
    assert not t.in_progress
    assert t.finished_count == 1


def test_progress_tracker_zero_total_no_division_by_zero():
    t = ProgressTracker()
    t.set_total(0)
    assert t.percent == 0.0
