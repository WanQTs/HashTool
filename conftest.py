"""pytest 夹具配置。

说明：pytest 内置 tmp_path 夹具以 POSIX 0o700 权限模式创建临时目录，
在本机文件沙箱环境中此类目录会被拒绝访问（PermissionError），
因此用自定义夹具在项目内创建普通权限的临时目录作为替代。
"""
import pathlib
import shutil
import uuid

import pytest

_TMP_ROOT = pathlib.Path(__file__).resolve().parent / "tmp_work"


@pytest.fixture(autouse=True)
def _default_zh():
    """测试默认使用中文，避免本机保存的语言配置影响断言。"""
    import i18n

    i18n.set_lang("zh")
    yield
    i18n.set_lang("zh")


@pytest.fixture
def tmp_path():
    """返回项目内 tmp_work 下的独立临时目录，测试结束后自动删除。"""
    _TMP_ROOT.mkdir(exist_ok=True)
    d = _TMP_ROOT / f"test_{uuid.uuid4().hex[:12]}"
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)
