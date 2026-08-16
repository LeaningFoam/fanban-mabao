"""主窗口 —— 无边框赛博风小窗浏览器。

实现要点(全部针对前两代踩过的坑):
1. 窗口状态实时保存:moveEvent/resizeEvent 持续更新 config,关闭时兜底 flush。
2. 启动恢复:读取上次的 位置/大小/最大化/透明度/置顶/上次网址。
3. 无边框自绘标题栏 + 边缘拖拽缩放(游戏小窗也需要能随手调大小)。
4. 全局热键动作绑定(播放/快进快退/倍速/音量/最大化/隐藏/置顶/穿透/退出)。
"""
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .logger import get_logger
from .webview_container import WebViewContainer
from . import theme
from .utils import win32_api

# 边缘缩放热区(像素)
_EDGE = 6
_MIN_W, _MIN_H = 320, 400

# 穿透时鼠标悬停窗口的透明度
_THROUGH_HOVER_OPACITY = 0.4

_EDGE_CURSORS = {
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
}


class _ResizeHandle(QWidget):
    """窗口边缘的透明缩放手柄。

    独立小控件盖在窗口四边/四角上(不进入布局,raise 到最前),
    专门接收边缘的鼠标事件做窗口缩放。
    好处:网页(QWebEngineView)区域完全不安装任何过滤器,
    网页内的点击/滚动 100% 交给浏览器,不会再出现"点不动网页"的问题。
    """

    def __init__(self, parent, edge):
        super().__init__(parent)
        self._edge = edge
        self._win = parent
        self.setCursor(_EDGE_CURSORS[edge])

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._win._begin_resize(self._edge, e.globalPos())

    def mouseMoveEvent(self, e):
        self._win._do_resize(e.globalPos())

    def mouseReleaseEvent(self, e):
        self._win._end_resize()


class MainWindow(QMainWindow):
    def __init__(self, config, hotkeys):
        super().__init__()
        self._log = get_logger()
        self._config = config
        self._hotkeys = hotkeys

        self._click_through = False
        self._hover_timer = None
        self._topmost = bool(config.get("window", "topmost", True))
        self._dragging = False
        self._drag_offset = QPoint()
        self._resizing = False
        self._resize_edge = None
        self._press_geom = QRect()
        self._geom_dirty = False
        self._geom_timer = None
        self._hold_timer = None  # 长按连发定时器(5/6 键)
        self._hover_activate_timer = None  # 鼠标悬停自动激活(游戏场景 hover 修复)

        self._build_ui()
        self._restore_window_state()
        self._bind_hotkeys()
        self._start_hover_activate()
        self._log.info("%s v%s 启动完成", APP_NAME, __version__)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        if self._topmost:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(_MIN_W, _MIN_H)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        self._vbox = QVBoxLayout(root)
        self._vbox.setContentsMargins(1, 1, 1, 1)
        self._vbox.setSpacing(0)

        self._title_bar = self._build_title_bar()
        self._vbox.addWidget(self._title_bar)

        self._web = WebViewContainer(self._config)
        self._toolbar = self._build_toolbar()
        self._vbox.addWidget(self._toolbar)

        # WebView2 是原生子窗口,会盖住 Qt 控件;四周内缩 8px,
        # 给边缘缩放手柄留出 Qt 区域(否则手柄被 WebView2 窗口遮挡,无法缩放)。
        self._web_host = QWidget()
        self._web_host.setObjectName("WebHost")
        _wh = QVBoxLayout(self._web_host)
        _wh.setContentsMargins(_EDGE, _EDGE, _EDGE, _EDGE)
        _wh.setSpacing(0)
        _wh.addWidget(self._web)
        self._vbox.addWidget(self._web_host, 1)

        self._status_bar = self._build_status_bar()
        self._vbox.addWidget(self._status_bar)

        # 边缘缩放用独立透明手柄实现(见 _ResizeHandle),
        # 网页区域不安装任何事件过滤器,保证网页交互 100% 正常。
        self._install_resize_handles()

        self._web.url_changed.connect(self._on_url_changed)
        self._web.js_result.connect(self._on_js_result)

    def _build_title_bar(self):
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 4, 0)
        lay.setSpacing(6)

        title = QLabel(APP_NAME)
        title.setObjectName("TitleText")
        hint = QLabel("游戏攻略伴侣小浏览器")
        hint.setObjectName("TitleHint")

        self._btn_pin = self._make_title_btn("置顶", "切换置顶", self._toggle_topmost)
        self._btn_through = self._make_title_btn("穿透", "鼠标穿透,不挡操作(热键 0)", self._toggle_click_through)
        self._btn_min = self._make_title_btn("—", "最小化", self.showMinimized)
        self._btn_max = self._make_title_btn("□", "最大化/还原(热键 Ctrl+空格)", self._toggle_maximize)
        btn_close = self._make_title_btn("✕", "退出", self.close)
        btn_close.setObjectName("TitleBtnClose")

        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addStretch(1)
        lay.addWidget(self._btn_pin)
        lay.addWidget(self._btn_through)
        lay.addWidget(self._btn_min)
        lay.addWidget(self._btn_max)
        lay.addWidget(btn_close)
        return bar

    def _build_toolbar(self):
        bar = QWidget()
        bar.setObjectName("ToolBar")
        bar.setFixedHeight(38)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        self._btn_back = self._make_tool_btn("←", "后退", self._web.back)
        self._btn_fwd = self._make_tool_btn("→", "前进", self._web.forward)
        self._btn_reload = self._make_tool_btn("⟳", "刷新", self._web.reload)
        self._btn_home = self._make_tool_btn("⌂", "回到主页", self._web.go_home)

        self._url_edit = QLineEdit()
        self._url_edit.setObjectName("UrlEdit")
        self._url_edit.setPlaceholderText("输入网址,回车访问(如 bilibili.com)")
        self._url_edit.returnPressed.connect(self._on_url_entered)

        lay.addWidget(self._btn_back)
        lay.addWidget(self._btn_fwd)
        lay.addWidget(self._btn_reload)
        lay.addWidget(self._btn_home)
        lay.addWidget(self._url_edit, 1)
        return bar

    def _build_status_bar(self):
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(28)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        self._status = QLabel("就绪")
        self._status.setObjectName("StatusText")
        self._status.setProperty("accent", True)

        self._rate_label = QLabel("倍速 1.0x")
        self._rate_label.setObjectName("StatusText")
        self._vol_label = QLabel("音量 100%")
        self._vol_label.setObjectName("StatusText")

        lay.addWidget(self._status)
        lay.addStretch(1)
        lay.addWidget(self._rate_label)
        lay.addWidget(self._vol_label)
        return bar

    def _make_title_btn(self, text, tip, slot):
        b = QPushButton(text)
        b.setObjectName("TitleBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def _make_tool_btn(self, text, tip, slot):
        b = QPushButton(text)
        b.setObjectName("ToolBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ---------------- 状态恢复/保存 ----------------
    def _restore_window_state(self):
        cfg = self._config
        x = cfg.get("window", "x", 100)
        y = cfg.get("window", "y", 100)
        w = cfg.get("window", "width", 480)
        h = cfg.get("window", "height", 640)
        self.setGeometry(max(0, x), max(0, y), max(_MIN_W, w), max(_MIN_H, h))
        op = float(cfg.get("window", "opacity", 1.0))
        # 重要:opacity == 1.0 时不要调用 setWindowOpacity!
        # 一旦调用,Windows 窗口会变成"分层窗口"(WS_EX_LAYERED),
        # QtWebEngine(Chromium)在分层窗口上初始化会崩溃(实测退出码 127)。
        # 用户实际调低透明度(op < 1.0)时才需要分层。
        if op < 1.0:
            self.setWindowOpacity(op)
        self._update_pin_ui()
        self._update_through_ui()
        QTimer.singleShot(0, self._apply_maximized)

    def _apply_maximized(self):
        if self._config.get("window", "maximized", False):
            self.showMaximized()

    def _save_window_geometry(self):
        """保存"真实"几何:最大化时存还原后的矩形,避免恢复成大窗口。"""
        cfg = self._config
        if self.isMaximized():
            g = self.normalGeometry()
            cfg.update("window", {
                "x": g.x(), "y": g.y(),
                "width": g.width(), "height": g.height(),
                "maximized": True,
            }, save=True)
        else:
            cfg.update("window", {
                "x": self.x(), "y": self.y(),
                "width": self.width(), "height": self.height(),
                "maximized": False,
            }, save=True)

    def moveEvent(self, e):
        super().moveEvent(e)
        self._mark_geometry_changed()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._mark_geometry_changed()
        self._update_resize_handles()

    def _mark_geometry_changed(self):
        """移动/缩放时只打标记,由防抖定时器统一落盘。

        为什么防抖:move/resize 事件高频触发,每次都同步写 config.json
        在 QtWebEngine 场景下会拖慢甚至干扰窗口初始化的消息处理;
        800ms 内合并为一次写入,关闭时再兜底写一次。
        """
        if self.isMaximized():
            return
        self._geom_dirty = True
        if self._geom_timer is None:
            self._geom_timer = QTimer(self)
            self._geom_timer.setSingleShot(True)
            self._geom_timer.setInterval(800)
            self._geom_timer.timeout.connect(self._flush_geometry)

    def _flush_geometry(self):
        if self._geom_dirty:
            self._geom_dirty = False
            self._save_window_geometry()

    def closeEvent(self, e):
        self._stop_hover_fade()
        self._save_window_geometry()
        self._config.update("window", {"opacity": self.windowOpacity()}, save=False)
        self._config.flush()
        self._hotkeys.unregister_all()
        self._log.info("已退出,状态已保存")
        super().closeEvent(e)

    # ---------------- 无边框拖动/缩放 ----------------
    def _install_resize_handles(self):
        """在窗口四边/四角创建透明缩放手柄。"""
        self._resize_handles = {}
        for edge in ("l", "r", "t", "b", "tl", "tr", "bl", "br"):
            h = _ResizeHandle(self, edge)
            h.hide()
            self._resize_handles[edge] = h
        self._update_resize_handles()

    def _update_resize_handles(self):
        """窗口尺寸/最大化状态变化时,重新摆放手柄。"""
        if self.isMaximized():
            for h in self._resize_handles.values():
                h.hide()
            return
        w, h = self.width(), self.height()
        e = _EDGE
        geom = {
            "l": (0, e, e, h - 2 * e),
            "r": (w - e, e, e, h - 2 * e),
            "t": (e, 0, w - 2 * e, e),
            "b": (e, h - e, w - 2 * e, e),
            "tl": (0, 0, e, e),
            "tr": (w - e, 0, e, e),
            "bl": (0, h - e, e, e),
            "br": (w - e, h - e, e, e),
        }
        for edge, (x, y, ww, hh) in geom.items():
            h = self._resize_handles[edge]
            h.setGeometry(x, y, ww, hh)
            h.raise_()
            h.show()

    def _begin_resize(self, edge, global_pos):
        self._resizing = True
        self._resize_edge = edge
        self._press_geom = self.geometry()
        self._press_global = global_pos

    def _do_resize(self, global_pos):
        if self._resizing and self._resize_edge:
            self._apply_resize(global_pos - self._press_global)

    def _end_resize(self):
        self._resizing = False
        self._resize_edge = None

    def mousePressEvent(self, e):
        # 边缘缩放由 _ResizeHandle 手柄处理;这里只管标题栏拖动
        if e.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            if e.pos().y() < 34:
                self._dragging = True
                self._drag_offset = e.globalPos() - self.frameGeometry().topLeft()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self.move(e.globalPos() - self._drag_offset)
            return
        super().mouseMoveEvent(e)

    def _apply_resize(self, delta):
        g = QRect(self._press_geom)
        dx, dy = delta.x(), delta.y()
        e = self._resize_edge
        if "l" in e:
            g.setLeft(min(g.right() - _MIN_W, g.left() + dx))
        if "r" in e:
            g.setRight(max(g.left() + _MIN_W, g.right() + dx))
        if "t" in e:
            g.setTop(min(g.bottom() - _MIN_H, g.top() + dy))
        if "b" in e:
            g.setBottom(max(g.top() + _MIN_H, g.bottom() + dy))
        self.setGeometry(g)

    def mouseReleaseEvent(self, e):
        self._resizing = False
        self._dragging = False
        self._resize_edge = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.pos().y() < 34:
            self._toggle_maximize()
            return
        super().mouseDoubleClickEvent(e)

    # ---------------- 窗口操作 ----------------
    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._save_window_geometry()

    def _toggle_topmost(self):
        self._topmost = not self._topmost
        flags = self.windowFlags()
        if self._topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # setWindowFlags 会隐藏窗口,重新显示
        self._update_pin_ui()
        self._config.set("window", "topmost", self._topmost)

    def _toggle_click_through(self):
        self._click_through = not self._click_through
        ok = win32_api.set_click_through(int(self.winId()), self._click_through)
        if not ok:
            self._status.setText("穿透功能不可用")
            self._click_through = False
            return
        if self._click_through:
            # 官方妈宝 V6 沉浸模式行为:穿透时隐藏导航栏(标题栏+工具栏+状态栏),
            # 窗口内只留网页,获得最大沉浸视野;再按 0 恢复。
            self._set_ui_immersive(True)
            # 穿透模式:鼠标移到窗口上时才变淡(提示该区域点不到),移开恢复清晰。
            # 用定时器轮询鼠标位置实现(穿透后窗口收不到鼠标事件,无法用事件判断)。
            self._hover_timer = QTimer(self)
            self._hover_timer.setInterval(120)
            self._hover_timer.timeout.connect(self._check_hover_fade)
            self._hover_timer.start()
            self._flash("已穿透:导航栏已隐藏,鼠标移到窗口上会变淡,按 0 恢复")
        else:
            self._set_ui_immersive(False)
            self._stop_hover_fade()
            self._flash("穿透已关闭,导航栏已恢复")
        self._update_through_ui()
        self._config.set("window", "click_through", self._click_through)

    def _set_ui_immersive(self, immersive):
        """官方沉浸模式:穿透时隐藏所有导航 UI,只保留网页区域。"""
        for w in (self._title_bar, self._toolbar, self._status_bar):
            try:
                w.setVisible(not immersive)
            except Exception:
                pass

    def _stop_hover_fade(self):
        if self._hover_timer is not None:
            self._hover_timer.stop()
            self._hover_timer = None
        op = float(self._config.get("window", "opacity", 1.0))
        self.setWindowOpacity(op if op < 1.0 else 1.0)

    def _check_hover_fade(self):
        """穿透开启时:鼠标在窗口内 -> 变淡;移开 -> 恢复清晰。"""
        if not self._click_through or not self.isVisible():
            return
        inside = self.frameGeometry().contains(QCursor.pos())
        target = _THROUGH_HOVER_OPACITY if inside else 1.0
        cur = self.windowOpacity()
        if abs(cur - target) > 0.05:
            self.setWindowOpacity(target)

    # ---------------- 鼠标悬停自动激活(游戏场景 hover 修复) ----------------
    def _start_hover_activate(self):
        """启动光标位置轮询:鼠标移入窗口时自动激活窗口。

        为什么需要:游戏前台时妈宝是后台窗口,WebView2(Chromium)在
        未激活窗口里不处理鼠标 hover → 播放器进度条不弹出(实测 mm=0)。
        激活后 hover 恢复正常。鼠标移入说明用户想操作它,自动激活符合直觉;
        点回游戏窗口焦点即回归,不影响游戏。
        """
        if self._hover_activate_timer is None:
            self._hover_activate_timer = QTimer(self)
            self._hover_activate_timer.setInterval(150)
            self._hover_activate_timer.timeout.connect(self._check_hover_activate)
        self._hover_activate_timer.start()

    def _check_hover_activate(self):
        if not self.isVisible() or self.isMinimized():
            return
        if self._click_through:
            # 穿透模式:故意不抢焦点(鼠标要穿过窗口到下层)
            return
        if self.isActiveWindow():
            return
        # 鼠标是否在窗口范围内(含标题栏区域)
        if self.frameGeometry().contains(QCursor.pos()):
            self.activateWindow()
            self.raise_()

    def toggle_hide(self):
        if self.isVisible():
            # 官方行为:隐藏时视频也暂停,避免"盲看"错过内容
            self._web.pause()
            self.hide()
            # 官方行为:隐藏后除 9(显示)外所有热键暂停响应,
            # 防止隐藏状态下误触 ~ 等键控制视频
            self._hotkeys.suspend_all_except({"toggle_hide"})
            self._log.info("已隐藏(热键 9,视频已暂停,其他热键已暂停)")
        else:
            self.show()
            self._hotkeys.resume_all()
            self._log.info("已显示(热键恢复)")

    def _update_pin_ui(self):
        self._btn_pin.setProperty("active", self._topmost)
        self._btn_pin.style().unpolish(self._btn_pin)
        self._btn_pin.style().polish(self._btn_pin)

    def _update_through_ui(self):
        self._btn_through.setProperty("active", self._click_through)
        self._btn_through.style().unpolish(self._btn_through)
        self._btn_through.style().polish(self._btn_through)

    # ---------------- 浏览器联动 ----------------
    def _on_url_entered(self):
        self._web.navigate(self._url_edit.text())

    def _on_url_changed(self, url):
        self._url_edit.setText(url)
        self._url_edit.setCursorPosition(0)

    def _on_js_result(self, result):
        if result.startswith("rate="):
            self._rate_label.setText("倍速 %sx" % result[5:])
            try:
                self._config.set("misc", "playback_rate", float(result[5:]))
            except ValueError:
                pass
        elif result.startswith("vol="):
            self._vol_label.setText("音量 %d%%" % (float(result[4:]) * 100))
            try:
                self._config.set("misc", "volume", float(result[4:]))
            except ValueError:
                pass
        elif result == "no-video":
            self._flash("当前页面没有播放的视频")

    def _flash(self, text, warn=False):
        self._status.setText(text)
        self._status.setProperty("warn", warn)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        QTimer.singleShot(2500, self._reset_status)

    def _reset_status(self):
        self._status.setProperty("warn", False)
        self._status.setText("就绪")

    # ---------------- 热键 ----------------
    def _bind_hotkeys(self):
        cfg = self._config.get("hotkeys")
        # 官方妈宝 V6 默认按键方案:
        #   ~ 播放/暂停、6 快进、5 快退、9 隐藏、0 穿透、Ctrl+Space 最大化
        self._hotkeys.register("toggle_play", cfg.get("toggle_play", "`"),
                               self._web.toggle_play)
        # 5/6 快退/快进:长按连发(官方行为)——按下跳一次,按住定时连发,松开停止
        self._hotkeys.register_hold(
            "seek_forward", cfg.get("seek_forward", "6"),
            self._make_hold_seek(1), self._stop_hold_seek)
        self._hotkeys.register_hold(
            "seek_backward", cfg.get("seek_backward", "5"),
            self._make_hold_seek(-1), self._stop_hold_seek)
        self._hotkeys.register("toggle_maximize", cfg.get("toggle_maximize", "ctrl+space"),
                               self._toggle_maximize)
        self._hotkeys.register("toggle_hide", cfg.get("toggle_hide", "9"),
                               self.toggle_hide)
        self._hotkeys.register("toggle_clickthrough", cfg.get("toggle_clickthrough", "0"),
                               self._toggle_click_through)

    # ---------------- 长按连发(官方 5/6 行为) ----------------
    def _make_hold_seek(self, direction):
        """返回按下回调:立即跳一次 + 启动连发定时器(每 260ms 一跳)。"""
        step = self._config.get("misc", "seek_step_sec", 5) * direction

        def on_down():
            self._web.seek(step)
            if self._hold_timer is None:
                self._hold_timer = QTimer(self)
                self._hold_timer.setInterval(260)
                self._hold_timer.timeout.connect(
                    lambda: self._web.seek(step))
            if not self._hold_timer.isActive():
                self._hold_timer.start()

        return on_down

    def _stop_hold_seek(self):
        if self._hold_timer is not None:
            self._hold_timer.stop()
