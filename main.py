"""妈宝 2.0 入口。

启动流程:
1. 初始化日志 / 配置(自动恢复上次状态)
2. 创建主窗口(自动加载上次网址,带登录态)
3. 注册全局热键
4. 进入事件循环
"""
import os
import sys


def _install_crash_hook():
    """早期崩溃捕获:打包版 exe 崩溃时把信息写到 exe 目录 crash.log。

    覆盖两类问题:
    - C 层崩溃/abort(faulthandler 抓栈)
    - Python 异常(sysexcepthook 写 traceback)
    """
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.getcwd()
        crash_log = os.path.join(base, "crash.log")

        import faulthandler
        faulthandler.enable(file=open(crash_log, "w"))

        def _hook(tp, val, tb):
            import traceback
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(tp, val, tb)))

        sys.excepthook = _hook
    except Exception:
        pass


_install_crash_hook()


def _setup_qt_env():
    """Qt 高 DPI 设置(WebView2 不需要 QtWebEngine 的兼容 flags)。"""
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


def main():
    _setup_qt_env()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    # Qt6 默认启用高 DPI(无需 AA_EnableHighDpiScaling)

    from app.config import Config
    from app.hotkey_manager import HotkeyManager
    from app.logger import setup_logger
    from app.main_window import MainWindow
    from app import APP_NAME, theme

    log = setup_logger()
    config = Config()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    theme.apply_theme(app)

    hotkeys = HotkeyManager()
    # 全局热键用低级键盘钩子(WH_KEYBOARD_LL)+独立线程,与浏览器内核无冲突。

    win = MainWindow(config, hotkeys)
    win.show()

    log.info("进入主循环")
    code = app.exec()
    hotkeys.unregister_all()
    config.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
