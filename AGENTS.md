# AGENTS.md

本文件面向 AI 编码代理，描述本项目的结构、约定与常用命令。项目文档与代码注释以中文为主。

## 项目概述

**文件哈希值获取与对比工具（HashTool）**：Windows 10/11 64 位桌面小工具，当前版本 1.5.0。

- 计算文件哈希：MD5 / SHA-1 / SHA-256 / SHA-512 / CRC32（可多选同时计算）。
- 三种哈希对比模式：单文件校验（按哈希长度自动识别算法）、两文件互比、批量比对（兼容 MD5Sum / SHA256SUM / certutil 清单格式）。
- 结果导出：CSV（带 BOM）与标准 SUM 格式 TXT。
- 中英双语界面（`i18n.py`），语言选择持久化到 `%APPDATA%\HashTool\config.json`（旧中文目录配置启动时自动迁移）。
- 界面为包豪斯风格（暖纸底色、墨黑标题带、三原色几何标识、扁平控件），全局微软雅黑。
- **纯 Python 标准库实现，零第三方运行时依赖**；最终交付为 PyInstaller 打包的 64 位单文件 `dist\HashTool.exe`。

## 技术栈与运行时架构

- **语言/运行时**：Python，目标 3.11+ 64 位（`ruff.toml` 中 `target-version = "py311"`）。本机开发虚拟环境为 `.venv`（Python 3.14，内含 pytest、ruff、pyinstaller）。
- **GUI**：tkinter / ttk。可选依赖 ttkbootstrap——若已安装则 ttk 控件自动改用 cosmo 主题（`app.py:_root_with_style` 中 try/except 回退到 clam 主题 + 手绘包豪斯样式）。
- **拖拽**：`dnd.py` 通过 ctypes 调用 Windows 原生 API（`DragAcceptFiles` + 接管窗口过程处理 `WM_DROPFILES`），仅支持 Windows，其他平台 `attach()` 返回 False 自动禁用。
- **并发模型（关键）**：哈希计算在后台 `ThreadPoolExecutor` 线程池中进行（最多 4 线程，hashlib 处理大块数据会释放 GIL，多线程有真实加速）。worker 与 GUI 通过 `queue.Queue` 消息通信，消息协议为 `("total", count, bytes)` / `("start", path)` / `("progress", path, done, size)` / `("result", HashResult)` / `("done",)`；GUI 主线程用 `root.after(50, ...)` 轮询队列。添加文件夹的目录递归遍历同样走后台线程 + 队列回插（队列用局部引用随轮询传递），扫描状态由 `app._scanning` 标志覆盖到结果消费完毕，窗口期内拦截清空/移除/重复添加/开始计算。**worker 必须以 try/finally 保证任何情况下都发送 `done`**，否则界面永久卡在「计算中」（有对应单元测试 `test_worker_unexpected_error_still_sends_done`）。
- **大文件读取**：8MB 分块 + 预分配缓冲区 `readinto`（`hash_core.HashCalculator`），不一次性读入内存。
- **进度核算**：`hash_core.ProgressTracker` 为纯逻辑类，结果消息允许乱序到达，进度收敛与顺序无关。
- **错误处理约定**：`compute_file` 等核心函数**不抛异常**，错误以 `HashResult.error` 字符串返回（经 `describe_error` 翻译为用户友好文案，语言随当前 i18n 设置）。
- **崩溃兜底**：`main.py` 捕获未处理异常，无控制台环境下把 traceback 写入临时目录的 `哈希工具_error.log`。

## 目录结构与模块划分

```
HashTool/
├── main.py                # 程序入口：--selftest 无界面自检（官方已知值验证算法）/ --smoke GUI 冒烟（1.5 秒后自退）
├── app.py                 # tkinter 图形界面：HashToolApp（主窗口）、ExportDialog、
│                          #   CompareWindow（含 VerifyTab / TwoFileTab / BatchTab 三个对比标签页）、launch()
├── hash_core.py           # 哈希核心逻辑，与 GUI 完全分离、可独立测试：
│                          #   HashCalculator（分块计算/取消）、ProgressTracker（进度核算）、
│                          #   collect_files（文件夹递归）、normalize_hash_text / detect_algorithm、
│                          #   parse_hash_list / verify_batch（清单解析与批量校验）、
│                          #   format_export_txt / format_export_csv / format_batch_csv（导出）、human_size
├── i18n.py                # 中英双语字符串表 _STRINGS、tr()、系统语言检测、配置读写与旧目录迁移
├── dnd.py                 # Windows 原生拖拽（ctypes + WM_DROPFILES），DropTarget 类
├── make_icon.py           # 图标生成脚本（纯 Python 绘制 ICO，多尺寸 BMP 条目）
├── benchmark.py           # 并行计算基准（复用 HashToolApp._compute_worker，对比 1/2/4 线程）
├── conftest.py            # pytest 夹具（见「测试说明」）
├── tests/
│   ├── test_hash_core.py  # 核心逻辑单元测试（官方已知值、分块、取消、清单解析、批量校验、导出等）
│   ├── test_app_worker.py # 并行 worker / 线程数解析测试（无需图形环境）
│   ├── test_i18n.py       # 双语完整性、占位符一致性、配置读写与迁移测试
│   └── test_gui_smoke.py  # GUI 冒烟测试（主流程 + 三种对比模式 + 语言切换；无显示环境自动跳过）
├── pytest.ini             # pytest 配置
├── ruff.toml              # ruff 静态检查配置
├── build.bat              # 一键打包脚本（生成图标 + PyInstaller）
├── README.md / README_EN.md / CHANGELOG.md
├── tmp_work/              # 测试临时目录（见 conftest.py）
└── dist/HashTool.exe      # 打包产物（被 .gitignore 忽略）
```

**模块边界约定**：所有可脱离 GUI 的逻辑都放 `hash_core.py`（纯函数/类，可独立单元测试）；`app.py` 只做界面与线程调度。新增功能时优先遵循此边界。

## 常用命令

以下命令均假设在项目根目录（`HashTool/`）执行，本机可用 `.venv/Scripts/python.exe` 代替 `python`：

```bat
:: 开发模式运行 / 自检 / 冒烟
python main.py
python main.py --selftest
python main.py --smoke

:: 运行全部测试（64 个，当前全部通过）
python -m pytest

:: 静态检查（当前零告警）
python -m ruff check

:: 性能基准（默认 6×128MB，对比 1/2/4 线程）
python benchmark.py

:: 打包（需 64 位 Python 3.11+ 且已安装 pyinstaller）
build.bat
```

## 代码风格

- 注释、docstring、提交信息、文档均用**中文**；新代码请保持同样风格。
- ruff 配置（`ruff.toml`）：`line-length = 120`，启用规则集 `E4/E7/E9/F/W6/I/UP/B/PIE`。
- **有意不启用 BLE/S**：GUI 与 ctypes 层存在大量有意为之的静默兜底（主题回退、拖拽注册失败、配置读写失败、剪贴板占用等），安全审计类规则对桌面工具是噪音。这些兜底处通常有注释说明，修改时不要随手「修复」成抛异常。
- 导入顺序遵循 isort 风格（ruff `I` 规则），现代类型标注（`X | None`，`from __future__ import annotations`）。
- 修改代码后必须跑 `python -m pytest` 和 `python -m ruff check`，两者全绿才算完成。

## 测试说明

- 框架为 pytest，配置在 `pytest.ini`（`pythonpath = .`，`testpaths = tests`）。
- **不要用 pytest 内置 `tmp_path` 夹具**：其 0o700 权限目录在本机文件沙箱环境中会被拒绝访问。`conftest.py` 用同名自定义夹具覆盖它——在项目内 `tmp_work/` 下创建普通权限目录，测试结束自动删除。基准脚本同理（用 `bench_tmp_<pid>/` 而非 `tempfile.TemporaryDirectory`）。
- `conftest.py` 还有 autouse 夹具 `_default_zh`：每个测试前后强制语言为中文，避免本机保存的语言配置影响断言。测试英文行为时先 `i18n.set_lang("en")`，并在结尾切回。
- **i18n 约定（测试强制）**：`_STRINGS` 中每个键必须同时有 `zh` 和 `en`，且两种语言的 `{占位符}` 集合一致；`tr()` 对未知键回退为键名本身，格式化失败回退为原文。新增界面文案时务必双语同步添加。
- GUI 测试（`test_gui_smoke.py`）通过直接调用 `HashToolApp` 方法驱动，用 `_pump_until` 循环 `root.update()` 等待后台完成；窗口 `withdraw()` 隐藏；无图形环境时 `pytest.skip` 自动跳过。
- 算法正确性用官方已知值验证（如 `"abc"` 的 SHA-256 = `ba7816bf…15ad`），`main.py --selftest` 也内置同一组向量。

## 打包与部署

- 运行 `build.bat`：先用 `make_icon.py` 生成 `app.ico`，再执行 `PyInstaller --noconfirm --clean --onefile --noconsole --name "HashTool" --icon app.ico --distpath dist --workpath build --specpath build main.py`。
- 要求 64 位 Python 3.11+，目标系统 Windows 10/11 64 位，产物 `dist\HashTool.exe` 单文件。
- `app.ico`、`build/`、`dist/`、`tmp_work/`、`bench_tmp_*/` 均被 `.gitignore` 忽略（图标是生成物，不入库）。
- PyInstaller `--onefile` 产物偶尔被杀毒软件误报，属已知现象（README 常见问题有说明）。

## 安全与平台注意事项

- 拖拽（`dnd.py`）直接操作窗口过程，所有 ctypes 调用都要保持现有的类型声明与异常兜底；非 Windows 必须静默禁用。
- 配置目录为 `%APPDATA%\HashTool\`；旧目录 `%APPDATA%\哈希工具\` 仅用于启动时迁移，不要在新代码中引用旧路径。
- 程序不访问网络、不写工作目录之外的位置（除上述配置目录与临时目录的错误日志）；保持零第三方运行时依赖，新功能优先用标准库实现。
- 批量比对清单中的文件名可含相对子目录，路径拼接基于用户选择的目录（`verify_batch` 的 `base_dir`），属预期行为。
