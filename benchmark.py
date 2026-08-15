"""并行计算基准测试：对比 1 / 2 / 4 线程计算多个大文件的耗时与加速比。

复用 app.HashToolApp._compute_worker（与 GUI 实际计算路径一致），
每个配置重复多轮取最优值，避免系统瞬时负载干扰。

用法：
    python benchmark.py                          # 默认 6 个文件 x 128MB，每配置 2 轮
    python benchmark.py --count 8 --size-mb 256 --rounds 3
"""
import argparse
import os
import queue
import shutil
import sys
import threading
import time

import hash_core
from app import HashToolApp

ALGOS = ("md5", "sha256", "sha512")


def make_files(root: str, count: int, size: int) -> list[str]:
    """生成 count 个大小为 size 字节的测试文件。"""
    files = []
    block = bytes(1024 * 1024)
    for i in range(count):
        path = os.path.join(root, f"big{i}.bin")
        with open(path, "wb") as fh:
            written = 0
            while written < size:
                n = min(len(block), size - written)
                fh.write(block[:n])
                written += n
        files.append(path)
    return files


def run_once(files: list[str], max_threads: int) -> float:
    """同步跑完一轮计算，返回耗时（秒）；同时校验结果完整性。"""
    q = queue.Queue()
    event = threading.Event()
    start = time.perf_counter()
    HashToolApp._compute_worker(files, list(ALGOS), event, q, max_threads=max_threads)
    elapsed = time.perf_counter() - start
    results = {}
    while True:
        msg = q.get()
        if msg[0] == "result":
            results[msg[1].path] = msg[1]
        elif msg[0] == "done":
            break
    assert len(results) == len(files) and all(r.ok for r in results.values()), "基准结果校验失败"
    return elapsed


def main() -> None:
    # Windows 下输出经管道/重定向时默认使用 ANSI 代码页，强制 UTF-8 避免中文乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="哈希计算并行基准")
    parser.add_argument("--count", type=int, default=6, help="测试文件数量（默认 6）")
    parser.add_argument("--size-mb", type=int, default=128, help="单个文件大小 MB（默认 128）")
    parser.add_argument("--rounds", type=int, default=2, help="每个配置重复轮数，取最优（默认 2）")
    args = parser.parse_args()

    total_mb = args.count * args.size_mb
    print(f"CPU 逻辑核心数：{os.cpu_count()}；算法：{'、'.join(hash_core.ALGORITHM_LABELS[a] for a in ALGOS)}")
    print(f"正在生成 {args.count} 个 {args.size_mb}MB 测试文件（共 {total_mb}MB）…")
    # 用普通权限目录代替 tempfile.TemporaryDirectory（其 0o700 权限在部分受限环境下不可访问）
    tmp = os.path.join(os.getcwd(), f"bench_tmp_{os.getpid()}")
    os.mkdir(tmp)
    try:
        files = make_files(tmp, args.count, args.size_mb * 1024 * 1024)
        print(f"生成完成，开始基准（每配置 {args.rounds} 轮取最优）…")
        best = {}
        for threads in (1, 2, 4):
            t = min(run_once(files, threads) for _ in range(args.rounds))
            best[threads] = t
            print(f"  {threads} 线程：{t:.2f}s（吞吐 {total_mb / t:.0f} MB/s）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    base = best[1]
    print("\n加速比（相对 1 线程）：")
    for threads in (1, 2, 4):
        print(f"  {threads} 线程：x{base / best[threads]:.2f}")


if __name__ == "__main__":
    main()
