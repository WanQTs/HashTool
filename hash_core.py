"""哈希计算核心模块（与 GUI 无关，可独立单元测试）。

包含：
- 分块哈希计算（默认每块 8MB，大文件不会一次性读入内存）
- 文件/文件夹递归遍历
- 并行计算的进度核算（ProgressTracker，纯逻辑，可独立测试）
- 哈希值格式归一化与算法自动识别（按长度：32=MD5、40=SHA-1、64=SHA-256、128=SHA-512、8=CRC32）
- 哈希清单解析与批量校验（兼容 MD5Sum / SHA256SUM / certutil 格式）
- 结果导出（TXT 标准 SUM 格式 / CSV）
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import threading
import time
import zlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from i18n import tr

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB，大文件分块读取

SUPPORTED_ALGORITHMS: tuple[str, ...] = ("md5", "sha1", "sha256", "sha512", "crc32")

ALGORITHM_LABELS = {
    "md5": "MD5",
    "sha1": "SHA-1",
    "sha256": "SHA-256",
    "sha512": "SHA-512",
    "crc32": "CRC32",
}

# 按十六进制字符串长度自动识别算法
_LENGTH_TO_ALGORITHM = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512", 8: "crc32"}

_HEX_RUN_RE = re.compile(r"[0-9a-fA-F]+")

ProgressCallback = Callable[[str, int, int], None] | None


@dataclass
class HashResult:
    """单个文件的哈希计算结果。"""

    path: str
    size: int = 0
    hashes: dict = field(default_factory=dict)  # 算法名 -> 十六进制哈希字符串
    elapsed: float = 0.0
    error: str = ""  # 非空表示计算失败（已翻译成用户友好的中文）
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.error and not self.cancelled

    def get(self, algorithm: str) -> str:
        return self.hashes.get(algorithm, "")


@dataclass
class BatchCheckItem:
    """哈希清单中的一条记录。"""

    expected_hash: str
    filename: str
    algorithm: str | None = None  # None 表示格式无法识别
    line_no: int = 0


@dataclass
class BatchResultItem:
    """批量校验的一条结果。status: pass/fail/missing/error/bad_format/cancelled"""

    item: BatchCheckItem
    status: str
    actual_hash: str = ""
    error: str = ""


class _CRC32Hasher:
    """zlib.crc32 的增量封装，接口与 hashlib 保持一致。"""

    def __init__(self) -> None:
        self._value = 0

    def update(self, chunk: bytes) -> None:
        self._value = zlib.crc32(chunk, self._value)

    def hexdigest(self) -> str:
        return f"{self._value & 0xFFFFFFFF:08x}"


class HashCalculator:
    """分块计算文件哈希；可通过 cancel_event 取消。"""

    def __init__(
        self,
        algorithms: Iterable[str],
        chunk_size: int = CHUNK_SIZE,
        progress_callback: ProgressCallback = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.algorithms = tuple(algorithms)
        unknown = [a for a in self.algorithms if a not in SUPPORTED_ALGORITHMS]
        if unknown:
            raise ValueError(tr("err_unknown_algo", algos=", ".join(unknown)))
        if not self.algorithms:
            raise ValueError(tr("err_no_algo"))
        self.chunk_size = max(1, int(chunk_size))
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event

    def _new_hashers(self) -> dict:
        out = {}
        for algo in self.algorithms:
            out[algo] = _CRC32Hasher() if algo == "crc32" else hashlib.new(algo)
        return out

    def compute_file(self, path: str) -> HashResult:
        """计算单个文件的哈希。任何错误都以 HashResult.error 返回，不抛出异常。"""
        path = os.fspath(path)
        if self.cancel_event is not None and self.cancel_event.is_set():
            return HashResult(path=path, cancelled=True)
        if os.path.isdir(path):
            return HashResult(path=path, error=tr("err_is_dir", path=path))
        start = time.perf_counter()
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return HashResult(path=path, error=describe_error(exc, path))
        hashers = self._new_hashers()
        processed = 0
        # 预分配缓冲区 + readinto：避免每个 8MB 分块都新分配内存，减少大文件计算时的内存抖动
        buf = bytearray(self.chunk_size)
        view = memoryview(buf)
        try:
            with open(path, "rb") as fh:
                while True:
                    if self.cancel_event is not None and self.cancel_event.is_set():
                        return HashResult(path=path, size=size, cancelled=True)
                    n = fh.readinto(buf)
                    if not n:
                        break
                    chunk = view[:n]
                    for h in hashers.values():
                        h.update(chunk)
                    processed += n
                    if self.progress_callback is not None:
                        self.progress_callback(path, processed, size)
        except (OSError, ValueError) as exc:
            return HashResult(path=path, size=size, error=describe_error(exc, path))
        elapsed = time.perf_counter() - start
        return HashResult(
            path=path,
            size=size,
            elapsed=elapsed,
            hashes={a: h.hexdigest() for a, h in hashers.items()},
        )


class ProgressTracker:
    """多文件并行计算的整体进度核算（纯逻辑，与 GUI 无关，可独立测试）。

    消息语义与后台工作线程发送的队列消息一一对应；结果消息允许乱序到达
    （并行下各文件完成顺序不定），最终收敛到 100% 与到达顺序无关。
    """

    def __init__(self) -> None:
        self.total_bytes = 0
        self.finished_bytes = 0
        self.finished_count = 0
        self.in_progress: dict[str, int] = {}  # 路径 -> 该文件已处理字节

    def set_total(self, total_bytes: int) -> None:
        self.total_bytes = max(0, int(total_bytes))

    def on_progress(self, path: str, done_bytes: int) -> None:
        self.in_progress[path] = done_bytes

    def on_result(self, result: HashResult) -> None:
        """文件结束（成功/失败/取消）：累计字节并清除其进行中记录。

        失败的文件不计入完成字节（与界面既有行为一致：进度条不因其虚增）。
        """
        self.finished_count += 1
        if not result.error:
            self.finished_bytes += result.size
        self.in_progress.pop(result.path, None)

    @property
    def percent(self) -> float:
        """整体进度百分比（0~100）；总字节为 0（如全是空文件）时返回 0，不除零。"""
        if self.total_bytes <= 0:
            return 0.0
        done = self.finished_bytes + sum(self.in_progress.values())
        return min(100.0, done / self.total_bytes * 100.0)


def describe_error(exc: BaseException, path: str = "") -> str:
    """把文件异常翻译成用户友好的提示（文件被占用 / 无权限 / 不存在等），语言随当前设置。"""
    if isinstance(exc, FileNotFoundError):
        return tr("err_not_found", path=path)
    if isinstance(exc, IsADirectoryError):
        return tr("err_is_dir", path=path)
    if isinstance(exc, PermissionError):
        winerror = getattr(exc, "winerror", None)
        if winerror == 32:
            return tr("err_locked", path=path)
        if winerror == 5 or getattr(exc, "errno", None) == 13:
            return tr("err_denied", path=path)
        return tr("err_cant_read", path=path)
    if isinstance(exc, OSError):
        reason = getattr(exc, "strerror", None) or str(exc)
        return tr("err_read_fail", path=path, reason=reason)
    return tr("err_generic", path=path, exc=exc)


def collect_files(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """展开输入路径：文件直接收录，文件夹递归遍历所有子目录。

    返回 (files, errors)；errors 为中文错误描述列表。
    """
    files: list[str] = []
    errors: list[str] = []

    def walk_error(exc: OSError) -> None:
        errors.append(describe_error(exc, getattr(exc, "filename", "") or ""))

    for p in paths:
        try:
            if os.path.isfile(p):
                files.append(p)
            elif os.path.isdir(p):
                for root, dirs, names in os.walk(p, onerror=walk_error):
                    dirs.sort()
                    for name in sorted(names):
                        files.append(os.path.join(root, name))
            else:
                errors.append(tr("err_path_missing", p=p))
        except OSError as exc:
            errors.append(describe_error(exc, p))
    return files, errors


def normalize_hash_text(text: str) -> str:
    """提取文本中的哈希值：去除空白、统一小写。

    兼容形如 "MD5 (file.txt) = 90015098…" 的格式——取最长的十六进制片段。
    """
    if not text:
        return ""
    candidates = _HEX_RUN_RE.findall(text.lower())
    if not candidates:
        return ""
    return max(candidates, key=len)


def detect_algorithm(text: str) -> str | None:
    """按长度自动识别算法：32=MD5、40=SHA-1、64=SHA-256、128=SHA-512、8=CRC32。"""
    return _LENGTH_TO_ALGORITHM.get(len(normalize_hash_text(text)))


def compare_hashes(computed: str, expected: str) -> bool:
    """忽略大小写与空白比较两个哈希值。"""
    expected_norm = normalize_hash_text(expected)
    return bool(expected_norm) and normalize_hash_text(computed) == expected_norm


def parse_hash_list(text: str) -> list[BatchCheckItem]:
    """解析哈希清单，兼容 MD5Sum / SHA256SUM / certutil 格式。

    每行支持：
        <哈希值>   <文件名>            （空格/制表符分隔）
        <哈希值>  *<文件名>            （BSD 风格）
        MD5 (<文件名>) = <哈希值>      （certutil 风格）
    以 # 或 ; 开头的行视为注释，空行跳过。
    """
    items: list[BatchCheckItem] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        item = _parse_one_line(line, line_no)
        if item is not None:
            items.append(item)
    return items


def _parse_one_line(line: str, line_no: int) -> BatchCheckItem | None:
    # certutil 风格：MD5 (file) = hash（算法名不区分大小写）
    m = re.match(r"^(md5|sha1|sha256|sha512|crc32)\s*\((.+?)\)\s*=\s*([0-9a-fA-F]{8,128})$", line, re.IGNORECASE)
    if m:
        algo, filename, digest = m.groups()
        return BatchCheckItem(digest.lower(), filename.strip(), algo.lower(), line_no)
    # 常规风格：hash 文件名 / hash *文件名
    m = re.match(r"^([0-9a-fA-F]{8,128})\s+\*?(.*?)\s*$", line)
    if m:
        digest, filename = m.groups()
        if not filename:
            return None
        return BatchCheckItem(digest.lower(), filename, _LENGTH_TO_ALGORITHM.get(len(digest)), line_no)
    return None


def verify_batch(
    items: Iterable[BatchCheckItem],
    base_dir: str,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[BatchResultItem]:
    """批量校验哈希清单。base_dir 为文件所在目录。

    progress_callback(index, total, done_bytes, size_bytes)
    """
    items = list(items)
    total = len(items)
    results: list[BatchResultItem] = []
    for idx, item in enumerate(items):
        if cancel_event is not None and cancel_event.is_set():
            results.append(BatchResultItem(item=item, status="cancelled"))
            continue
        if item.algorithm is None:
            results.append(BatchResultItem(item=item, status="bad_format"))
            continue
        path = item.filename if os.path.isabs(item.filename) else os.path.join(base_dir, item.filename)
        if not os.path.isfile(path):
            results.append(BatchResultItem(item=item, status="missing"))
            if progress_callback is not None:
                progress_callback(idx, total, 0, 0)
            continue

        def cb(_p, done, size, idx=idx):  # 显式绑定循环变量，避免闭包按引用捕获
            if progress_callback is not None:
                progress_callback(idx, total, done, size)

        result = HashCalculator([item.algorithm], cancel_event=cancel_event, progress_callback=cb).compute_file(path)
        if result.cancelled:
            results.append(BatchResultItem(item=item, status="cancelled"))
        elif result.error:
            results.append(BatchResultItem(item=item, status="error", error=result.error))
        else:
            actual = result.get(item.algorithm)
            status = "pass" if actual == item.expected_hash else "fail"
            results.append(BatchResultItem(item=item, status=status, actual_hash=actual))
    return results


def read_text_file(path: str) -> str:
    """读取文本文件，自动尝试 UTF-8(BOM)/GBK 编码。"""
    path = os.fspath(path)
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            raise
    raise ValueError(tr("err_bad_encoding", path=path))


def format_export_txt(results: Iterable[HashResult], algorithm: str) -> str:
    """生成标准 SUM 格式文本（每行 "哈希值  文件名"，可被其他校验工具识别）。"""
    ok = [r for r in results if r.ok and r.get(algorithm)]
    if not ok:
        return ""
    counts = Counter(os.path.basename(r.path) for r in ok)
    lines = []
    for r in ok:
        name = os.path.basename(r.path) if counts[os.path.basename(r.path)] == 1 else r.path
        lines.append(f"{r.get(algorithm)}  {name}")
    return "\n".join(lines) + "\n"


def format_export_csv(results: Iterable[HashResult], algorithms: Iterable[str]) -> str:
    """生成 CSV 文本（调用方应以 utf-8-sig 写盘，便于 Excel 直接打开）。"""
    algorithms = [a for a in algorithms if a in SUPPORTED_ALGORITHMS]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([tr("csv_name"), tr("csv_path"), tr("csv_size"),
                     *[ALGORITHM_LABELS[a] for a in algorithms], tr("csv_elapsed"), tr("csv_status")])
    for r in results:
        if r.error:
            status = tr("st_error_fmt", msg=r.error)
        else:
            status = tr("csv_done") if r.ok else tr("csv_cancelled")
        writer.writerow(
            [
                os.path.basename(r.path),
                r.path,
                r.size,
                *[r.get(a) for a in algorithms],
                f"{r.elapsed:.3f}",
                status,
            ]
        )
    return buf.getvalue()


_BATCH_STATUS_KEYS = {
    "pass": "bt_st_pass",
    "fail": "bt_st_fail",
    "missing": "bt_st_missing",
    "error": "bt_st_error",
    "bad_format": "bt_st_bad",
    "cancelled": "bt_st_cancelled",
}


def batch_status_text(status: str) -> str:
    return tr(_BATCH_STATUS_KEYS.get(status, "")) if status in _BATCH_STATUS_KEYS else status


def format_batch_csv(results: Iterable[BatchResultItem]) -> str:
    """把批量比对结果导出为 CSV 文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([tr("csv_line"), tr("csv_name"), tr("col_algo"), tr("csv_expected"),
                     tr("csv_actual"), tr("csv_status"), tr("csv_error_info")])
    for r in results:
        it = r.item
        writer.writerow(
            [
                it.line_no,
                it.filename,
                ALGORITHM_LABELS.get(it.algorithm or "", ""),
                it.expected_hash,
                r.actual_hash,
                batch_status_text(r.status),
                r.error,
            ]
        )
    return buf.getvalue()


def human_size(num: int) -> str:
    """把字节数格式化为易读文本。"""
    try:
        num = int(num)
    except (TypeError, ValueError):
        return ""
    if num < 1024:
        return f"{num} B"
    value = float(num)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        value /= 1024.0
        if value < 1024 or unit == "PB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"
