"""全局热键管理 —— 低级键盘钩子(WH_KEYBOARD_LL)方案。

为什么不用 QAbstractNativeEventFilter:
  实测 PyQt5 5.15 + QtWebEngine 环境下 installNativeEventFilter 会导致
  窗口 show 时进程直接退出(退出码 127)。官方妈宝 V6 也是用低级键盘钩子 +
  独立线程 + 消息循环,这是绕开该冲突的成熟方案。

方案结构(与官方 V6 一致):
  - 独立线程安装 WH_KEYBOARD_LL 钩子,自带消息循环
  - 钩子回调里维护 modifier 状态 + 已注册热键表,命中时通过 Qt 信号
    通知主线程执行动作(线程安全)
  - 支持组合键"滚键容忍":Ctrl 松开 300ms 内按 Space 也算 Ctrl+Space,
    匹配真人手指习惯(官方 V6 2026-08-11 修复点)

热键字符串格式:"ctrl+space"、"right"、"9"、"ctrl+q" 等。
"""
import ctypes
import threading
import time
from ctypes import wintypes

from PyQt6.QtCore import QThread, pyqtSignal

from .logger import get_logger

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---- ctypes 签名声明:64 位系统下指针/句柄参数必须显式声明,否则
#     回调里传 64 位指针值会 OverflowError("int too long to convert"),
#     导致钩子放行失败、后续按键事件丢失(实测 5/6 命中但 ~/0 丢失)。 ----
_LRESULT = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = _LRESULT
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

# 通用 modifier VK(左/右归一)
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_WIN = 0x5B

# 滚键容忍窗口(毫秒):modifier 刚抬起 <= 300ms 内按下 trigger 键也算组合
ROLLOVER_WINDOW_MS = 300

_MODIFIERS = {
    "ctrl": VK_CONTROL, "control": VK_CONTROL,
    "alt": VK_MENU, "shift": VK_SHIFT, "win": VK_WIN, "meta": VK_WIN,
}

_VK_MAP = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "\\": 0xDC,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
}

_IS_MODIFIER = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_WIN, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


def _normalize_mod(vk):
    """左/右 modifier(0xA0-0xA5)归一到通用码(0x10/0x11/0x12/0x5B)。"""
    if vk in (0xA0, 0xA1):
        return VK_SHIFT
    if vk in (0xA2, 0xA3):
        return VK_CONTROL
    if vk in (0xA4, 0xA5):
        return VK_MENU
    return vk


def parse_hotkey(s):
    """把 "ctrl+space" 解析为 (modifiers:set[vk], trigger_vk)。失败抛 ValueError。"""
    s = s.strip().lower()
    parts = [p.strip() for p in s.split("+") if p.strip()]
    mods = set()
    keys = []
    for p in parts:
        if p in _MODIFIERS:
            mods.add(_MODIFIERS[p])
        else:
            keys.append(p)
    if not keys:
        raise ValueError("没有按键: %r" % s)
    if len(keys) > 1:
        raise ValueError("多余的按键: %r" % s)
    key = keys[0]
    if key.isdigit() and len(key) == 1:
        vk = ord(key)
    elif len(key) == 1 and key.isalpha():
        vk = ord(key.upper())
    elif key in _VK_MAP:
        vk = _VK_MAP[key]
    else:
        raise ValueError("未知按键: %r" % key)
    return mods, vk


class _KeyboardHookThread(QThread):
    """独立线程 + 低级键盘钩子 + 消息循环。命中热键时发信号。"""

    hotkey_triggered = pyqtSignal(str)   # 普通热键(按下触发一次)
    hotkey_hold_down = pyqtSignal(str)   # 长按热键:按下(用于连发启动)
    hotkey_hold_up = pyqtSignal(str)     # 长按热键:松开(用于连发停止)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = get_logger()
        self._bindings = {}        # trigger_vk -> [(mods_set, action, is_hold), ...]
        self._actions = set()      # 所有 action 名
        self._pressed_mods = set()  # 当前按住的 modifier(通用码)
        self._mod_times = {}       # 通用码 -> {"down": ns, "up": ns}
        self._stop_flag = threading.Event()
        self._hook = None

    def bind(self, action, hotkey_str, is_hold=False):
        try:
            mods, vk = parse_hotkey(hotkey_str)
        except ValueError as e:
            self._log.error("热键 %s 解析失败: %s", action, e)
            return False
        self._bindings.setdefault(vk, []).append((mods, action, is_hold))
        self._actions.add(action)
        return True

    def unbind_all(self):
        self._bindings.clear()
        self._actions.clear()

    def stop(self):
        self._stop_flag.set()
        # 唤醒消息循环
        user32.PostThreadMessageW(int(self.threadId) if hasattr(self, "threadId") else 0, WM_QUIT, 0, 0)

    def run(self):
        self.threadId = int(ctypes.windll.kernel32.GetCurrentThreadId())

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def callback(nCode, wParam, lParam):
            if nCode >= 0:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                self._on_key_event(int(wParam), int(kb.vkCode))
            # 放行所有按键(我们只监听,不拦截)
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._callback_fn = HOOKPROC(callback)  # 防止被 GC
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback_fn, None, 0)
        if not self._hook:
            self._log.error("低级键盘钩子安装失败")
            return
        self._log.info("键盘钩子已安装")

        msg = wintypes.MSG()
        while not self._stop_flag.is_set():
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._log.info("键盘钩子已卸载")

    # ---------------- 按键处理 ----------------
    def _on_key_event(self, wParam, raw_vk):
        vk = _normalize_mod(raw_vk)
        now_ns = time.perf_counter_ns()
        is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)

        if vk in _IS_MODIFIER:
            if is_down:
                self._pressed_mods.add(vk)
                self._mod_times.setdefault(vk, {})["down"] = now_ns
            else:
                self._pressed_mods.discard(vk)
                self._mod_times.setdefault(vk, {})["up"] = now_ns
            return

        if is_down:
            # trigger 键按下:检查命中(含长按热键的按下)
            for mods, action, is_hold in self._bindings.get(vk, []):
                if self._match_mods(mods, now_ns):
                    try:
                        if is_hold:
                            self.hotkey_hold_down.emit(action)
                        else:
                            self.hotkey_triggered.emit(action)
                    except Exception:
                        self._log.exception("热键信号异常: %s", action)
                    break
        else:
            # 松开:只通知长按热键(短按热键按下时已触发)
            for mods, action, is_hold in self._bindings.get(vk, []):
                if is_hold:
                    try:
                        self.hotkey_hold_up.emit(action)
                    except Exception:
                        self._log.exception("热键松开信号异常: %s", action)
                    break

    def _match_mods(self, mods, now_ns):
        """严格同时 OR 300ms 滚键容忍。"""
        if not mods:
            return True
        for mod_vk in mods:
            pressed = mod_vk in self._pressed_mods
            times = self._mod_times.get(mod_vk, {})
            up_ns = times.get("up", 0)
            rolled = up_ns > 0 and (now_ns - up_ns) <= ROLLOVER_WINDOW_MS * 1_000_000
            if not (pressed or rolled):
                return False
        return True


class HotkeyManager:
    """对外封装:注册热键 -> 动作名 -> 回调。主线程使用。"""

    def __init__(self, parent=None):
        self._thread = _KeyboardHookThread(parent)
        self._callbacks = {}   # action -> callable
        self._hold_down = {}   # action -> callable(按下)
        self._hold_up = {}     # action -> callable(松开)
        self._suspended = set()  # 被暂停的动作集合(隐藏窗口时用,官方 V6 行为)
        self._thread.hotkey_triggered.connect(self._dispatch)
        self._thread.hotkey_hold_down.connect(self._dispatch_hold_down)
        self._thread.hotkey_hold_up.connect(self._dispatch_hold_up)
        self._log = get_logger()
        self._started = False

    def _ensure_started(self):
        if not self._started:
            self._thread.start()
            self._started = True

    # ---------------- 暂停/恢复(官方按 9 隐藏行为) ----------------
    def suspend_all_except(self, keep_actions):
        """暂停除 keep_actions 外的所有热键(隐藏窗口时调用)。

        官方妈宝 V6:按 9 隐藏后,除 toggle_visible(9)/自动对话外,
        所有热键都暂停响应 —— 避免隐藏状态下误触控制视频。
        """
        self._suspended = {
            a for a in list(self._callbacks) + list(self._hold_down)
            if a not in keep_actions
        }
        self._log.info("热键暂停: 仅保留 %s 响应", sorted(keep_actions))

    def resume_all(self):
        """恢复所有热键(窗口重新显示时调用)。"""
        if self._suspended:
            self._log.info("热键恢复: 全部响应")
        self._suspended.clear()

    def _is_suspended(self, action):
        return action in self._suspended

    def _dispatch(self, action):
        if self._is_suspended(action):
            return
        cb = self._callbacks.get(action)
        if cb:
            try:
                cb()
            except Exception:
                self._log.exception("热键回调异常: %s", action)

    def _dispatch_hold_down(self, action):
        if self._is_suspended(action):
            return
        cb = self._hold_down.get(action)
        if cb:
            try:
                cb()
            except Exception:
                self._log.exception("长按热键按下回调异常: %s", action)

    def _dispatch_hold_up(self, action):
        if self._is_suspended(action):
            return
        cb = self._hold_up.get(action)
        if cb:
            try:
                cb()
            except Exception:
                self._log.exception("长按热键松开回调异常: %s", action)

    def register(self, action, hotkey_str, callback):
        self._ensure_started()
        ok = self._thread.bind(action, hotkey_str)
        if ok:
            self._callbacks[action] = callback
            self._log.info("热键已注册: %s = %s", action, hotkey_str)
        return ok

    def register_hold(self, action, hotkey_str, on_down, on_up):
        """长按热键:按下触发 on_down,松开触发 on_up。

        官方妈宝 V6 行为(5/6 快进快退):按下瞬间跳一次,按住不放
        由调用方用定时器连发,松开停止。
        """
        self._ensure_started()
        ok = self._thread.bind(action, hotkey_str, is_hold=True)
        if ok:
            self._hold_down[action] = on_down
            self._hold_up[action] = on_up
            self._log.info("长按热键已注册: %s = %s", action, hotkey_str)
        return ok

    def unregister_all(self):
        self._callbacks.clear()
        self._hold_down.clear()
        self._hold_up.clear()
        if self._thread is not None:
            self._thread.unbind_all()
            self._thread.stop()
            self._thread.wait(2000)
        self._started = False
