"""Windows 原生文件拖拽支持（WM_DROPFILES），不依赖任何第三方库。

原理：通过 ctypes 调用 shell32.DragAcceptFiles 将 Tk 顶层窗口注册为拖放目标，
再临时接管其窗口过程处理 WM_DROPFILES 消息，用 DragQueryFileW 取出拖入的路径，
随后恢复原窗口过程。非 Windows 平台自动禁用。
"""
from __future__ import annotations

import ctypes
import os
import tkinter as tk
from ctypes import wintypes

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

# 窗口过程：返回 LRESULT（64 位下为 64 位整数）
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
shell32.DragFinish.argtypes = [wintypes.HANDLE]
shell32.DragQueryFileW.restype = wintypes.UINT
shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]

try:
    _set_window_long = user32.SetWindowLongPtrW
except AttributeError:  # 32 位 Python 的兜底（本工具目标为 64 位）
    _set_window_long = user32.SetWindowLongW
_set_window_long.restype = ctypes.c_ssize_t
_set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]


def _query_dropped_files(hdrop: int) -> list[str]:
    count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    paths: list[str] = []
    for i in range(count):
        length = shell32.DragQueryFileW(hdrop, i, None, 0)
        buf = ctypes.create_unicode_buffer(length + 1)
        shell32.DragQueryFileW(hdrop, i, buf, length + 1)
        paths.append(buf.value)
    return paths


class DropTarget:
    """把某个 Tk 组件所在的顶层窗口注册为文件拖放目标。"""

    def __init__(self, widget: tk.Misc, on_drop):
        self.widget = widget
        self.on_drop = on_drop
        self.hwnd: int | None = None
        self._proc = None  # 持有回调引用，防止被垃圾回收
        self._old_proc = None

    def attach(self) -> bool:
        """注册拖放，成功返回 True；非 Windows 或注册失败返回 False。"""
        if os.name != "nt":
            return False
        try:
            self.widget.update_idletasks()
            hwnd = self.widget.winfo_id()
            # Tk 顶层窗口的真实句柄是其客户区窗口的父窗口
            toplevel = user32.GetParent(hwnd) or hwnd
            self._proc = WNDPROC(self._wnd_proc)
            old = _set_window_long(toplevel, GWL_WNDPROC, self._proc)
            if not old:
                return False
            self._old_proc = WNDPROC(old)
            self.hwnd = toplevel
            shell32.DragAcceptFiles(toplevel, True)
            return True
        except Exception:
            self.hwnd = None
            return False

    def detach(self) -> None:
        """恢复原窗口过程并注销拖放。"""
        if self.hwnd is None or self._old_proc is None:
            return
        try:
            _set_window_long(self.hwnd, GWL_WNDPROC, self._old_proc)
            shell32.DragAcceptFiles(self.hwnd, False)
        except Exception:
            pass
        self.hwnd = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                paths = _query_dropped_files(wparam)
                if paths and self.on_drop is not None:
                    # 延后到 Tk 事件循环中处理，避免在窗口过程里直接操作控件
                    self.widget.after_idle(lambda p=paths: self.on_drop(p))
            finally:
                shell32.DragFinish(wparam)
            return 0
        return user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)
