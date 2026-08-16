"""配置管理 —— 状态保存/恢复的核心。

吸取前两代教训:
1. 官方版(易语言+Edge):"存了但启动时不读"  -> 我们启动时必读、关闭时必写。
2. 自建版第一代(Python):"保存的是初始值,不是真实窗口状态;句柄获取失败"
   -> 我们保存时实时读取窗口真实 geometry,不在关闭时才读一次,而是
      移动/缩放过程中持续更新(带防抖落盘),关闭时再兜底写一次。
3. 登录态:由 WebView 的持久化 profile 负责(见 webview_container.py)。

配置用 JSON,存放在用户数据目录(~/.mabao)下 config.json,便于用户查看和备份。
"""
import json
import os
import threading
import time

from . import DATA_DIR

_DEFAULT_HOTKEYS = {
    "toggle_play": "`",            # ~ 播放/暂停(官方妈宝 V6 默认)
    "seek_forward": "6",           # 快进 5 秒(长按连发)
    "seek_backward": "5",          # 快退 5 秒(长按连发)
    "toggle_maximize": "ctrl+space",  # 最大化/还原
    "toggle_hide": "9",            # 隐藏/显示(打游戏时临时藏起小窗)
    "toggle_clickthrough": "0",    # 鼠标穿透开关(官方默认 0)
}

_DEFAULTS = {
    "window": {
        "x": 100,
        "y": 100,
        "width": 480,
        "height": 640,
        "maximized": False,
        "opacity": 1.0,
        "topmost": True,
        "click_through": False,
    },
    "browser": {
        "home_url": "https://www.bilibili.com",
        "last_url": "https://www.bilibili.com",
    },
    "hotkeys": dict(_DEFAULT_HOTKEYS),
    "misc": {
        "volume": 1.0,
        "playback_rate": 1.0,
        "seek_step_sec": 5,
    },
}


class Config:
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(DATA_DIR, "config.json")
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()
        self._dirty = False
        self._last_save = 0.0

    def _load(self):
        data = json.loads(json.dumps(_DEFAULTS))  # 深拷贝默认值
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    user = json.load(f)
                self._merge(data, user)
            except Exception:
                # 配置损坏时备份并回退默认,不让用户数据直接丢失
                try:
                    os.replace(self.path, self.path + ".bak")
                except Exception:
                    pass
        return data

    @staticmethod
    def _merge(base, override):
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def get(self, section, key=None, default=None):
        with self._lock:
            if key is None:
                return self._data.get(section, default)
            return self._data.get(section, {}).get(key, default)

    def set(self, section, key, value, save=True):
        # 注意:先更新数据再释放锁,然后再 save()。
        # save() 内部要获取 self._lock,而 threading.Lock 不可重入,
        # 在持锁状态下调用 save() 会死锁(实测主线程卡死)。
        with self._lock:
            self._data.setdefault(section, {})[key] = value
        if save:
            self.save()

    def update(self, section, mapping, save=True):
        with self._lock:
            self._data.setdefault(section, {}).update(mapping)
        if save:
            self.save()

    def save(self):
        """防抖落盘:0.5 秒内多次调用只写一次。"""
        now = time.time()
        with self._lock:
            self._data["_saved_at"] = now
            if now - self._last_save < 0.5:
                self._dirty = True
                return
            self._write_locked()
            self._last_save = now

    def flush(self):
        """关闭前兜底,立即写盘。"""
        with self._lock:
            self._write_locked()

    def _write_locked(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            self._dirty = False
        except Exception:
            pass
