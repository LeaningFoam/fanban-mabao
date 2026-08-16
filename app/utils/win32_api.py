"""Win32 工具封装:窗口置顶/鼠标穿透 等系统级能力。

- 鼠标穿透:WS_EX_TRANSPARENT | WS_EX_LAYERED(让鼠标事件穿过窗口打到游戏)
- 置顶:优先走 Qt WindowStaysOnTopHint,这里提供 Win32 兜底方案
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20


def _get_ex_style(hwnd):
    return user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)


def set_click_through(hwnd, enabled):
    """开启后鼠标事件直接穿透本窗口(用于"边打游戏边看攻略、不想挡住操作")。"""
    if not hwnd:
        return False
    style = _get_ex_style(hwnd)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
    return True


def is_click_through(hwnd):
    if not hwnd:
        return False
    return bool(_get_ex_style(hwnd) & WS_EX_TRANSPARENT)
