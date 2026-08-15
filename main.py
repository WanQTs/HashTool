"""文件哈希值获取与对比工具 —— 程序入口。

用法：
    python main.py            启动图形界面
    python main.py --selftest 无界面自检（用官方已知值验证内置算法与运行环境）
    python main.py --smoke    GUI 冒烟测试（启动界面约 1.5 秒后自动退出）
"""
import sys


def _selftest() -> bool:
    """计算 b"abc" 的各算法哈希并与官方已知值比对。"""
    import os
    import tempfile

    import hash_core

    expected = {
        "md5": "900150983cd24fb0d6963f7d28e17f72",
        "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "sha512": "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
        "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
        "crc32": "352441c2",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "abc.bin")
            with open(path, "wb") as fh:
                fh.write(b"abc")
            result = hash_core.HashCalculator(list(expected), chunk_size=1).compute_file(path)
            return result.ok and all(result.get(a) == v for a, v in expected.items())
    except Exception:
        return False


def main() -> int:
    try:
        if "--selftest" in sys.argv:
            return 0 if _selftest() else 1
        from app import launch

        launch(smoke="--smoke" in sys.argv)
        return 0
    except Exception:
        import traceback

        if sys.stderr is not None:
            traceback.print_exc()
        # 无控制台环境下把崩溃信息写入临时目录，便于诊断
        try:
            import os
            import tempfile

            log_path = os.path.join(tempfile.gettempdir(), "哈希工具_error.log")
            with open(log_path, "w", encoding="utf-8") as fh:
                traceback.print_exc(file=fh)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
