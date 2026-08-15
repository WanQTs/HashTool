"""i18n 模块与英文模式核心行为测试。"""
import re

import pytest

import hash_core
import i18n
from i18n import _STRINGS, detect_system_language, get_lang, load_config, save_config, set_lang, tr

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_]\w*)")


def test_every_key_has_both_languages():
    missing = [k for k, v in _STRINGS.items() if "zh" not in v or "en" not in v]
    assert not missing, f"缺少翻译的键: {missing}"


def test_placeholder_sets_match_between_languages():
    bad = []
    for key, entry in _STRINGS.items():
        zh = set(_PLACEHOLDER_RE.findall(entry["zh"]))
        en = set(_PLACEHOLDER_RE.findall(entry["en"]))
        if zh != en:
            bad.append((key, zh, en))
    assert not bad, f"占位符不一致的键: {bad}"


def test_tr_switches_and_falls_back():
    set_lang("zh")
    assert tr("menu_file") == "文件"
    set_lang("en")
    assert tr("menu_file") == "File"
    assert tr("unknown_key_xyz") == "unknown_key_xyz"
    set_lang("xx")  # 非法语言被忽略，保持当前语言不变
    assert tr("menu_file") == "File"
    assert get_lang() == "en"


def test_tr_formatting():
    assert tr("st_added", lang="en", added=3, total=5) == "Added 3 file(s); 5 in total."
    assert tr("st_computing_pct", lang="zh", pct=42.5, done=3, total=7) == "正在计算… 42.5%（已完成 3/7 个文件）"


def test_core_english_error_messages():
    set_lang("en")
    exc = PermissionError(13, "denied")
    exc.winerror = 32
    assert "in use" in hash_core.describe_error(exc, "f.bin")
    assert hash_core.batch_status_text("pass") == "Passed"
    assert hash_core.batch_status_text("missing") == "Missing"
    with pytest.raises(ValueError) as ei:
        hash_core.HashCalculator(["md4"])
    assert "Unsupported" in str(ei.value)
    set_lang("zh")
    assert hash_core.batch_status_text("pass") == "通过"


def test_core_english_export_headers(tmp_path):
    set_lang("en")
    r = hash_core.HashResult(path=str(tmp_path / "a.txt"), size=3,
                             hashes={"md5": "900150983cd24fb0d6963f7d28e17f72"}, elapsed=0.1)
    out = hash_core.format_export_csv([r], ["md5"])
    assert "File Name" in out and "Status" in out and "Done" in out
    item = hash_core.BatchCheckItem("900150983cd24fb0d6963f7d28e17f72", "a.txt", "md5", 1)
    bout = hash_core.format_batch_csv([hash_core.BatchResultItem(item=item, status="fail")])
    assert "List Line" in bout and "Failed" in bout
    set_lang("zh")


def test_config_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    assert save_config("en", str(p)) is True
    assert load_config(str(p)) == "en"
    p.write_text('{"language": "xx"}', encoding="utf-8")
    assert load_config(str(p)) is None
    assert load_config(str(tmp_path / "nope.json")) is None


def test_migrate_legacy_config(tmp_path, monkeypatch):
    """旧中文配置目录自动迁移到新目录，旧文件与空目录被清理。"""
    new_path = tmp_path / "HashTool" / "config.json"
    legacy_path = tmp_path / "哈希工具" / "config.json"
    monkeypatch.setattr(i18n, "_CONFIG_PATH", str(new_path))
    monkeypatch.setattr(i18n, "_LEGACY_CONFIG_PATH", str(legacy_path))
    legacy_path.parent.mkdir(parents=True)
    assert save_config("en", str(legacy_path)) is True
    i18n._migrate_legacy_config()
    assert load_config(str(new_path)) == "en"
    assert not legacy_path.exists()
    assert not legacy_path.parent.exists()


def test_migrate_legacy_config_keeps_existing_new_config(tmp_path, monkeypatch):
    """新配置已存在时不迁移，旧文件原样保留。"""
    new_path = tmp_path / "HashTool" / "config.json"
    legacy_path = tmp_path / "哈希工具" / "config.json"
    monkeypatch.setattr(i18n, "_CONFIG_PATH", str(new_path))
    monkeypatch.setattr(i18n, "_LEGACY_CONFIG_PATH", str(legacy_path))
    assert save_config("zh", str(new_path)) is True
    legacy_path.parent.mkdir(parents=True)
    assert save_config("en", str(legacy_path)) is True
    i18n._migrate_legacy_config()
    assert load_config(str(new_path)) == "zh"
    assert legacy_path.exists()


def test_detect_system_language_returns_supported():
    assert detect_system_language() in {"zh", "en"}
