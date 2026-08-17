"""WebView 容器 —— 内置浏览器核心(WebView2/Edge 内核)。

关键决策:官方妈宝 V6 使用 WebView2(Edge Chromium 现代内核)而不是
QtWebEngine(Chromium 83 太旧),这是它能正常访问 B 站等现代网站的根本原因。
本容器基于 qtwebview2 库(官方 V6 同款)实现,完全兼容 B 站。

设计:
1. 登录态持久化:user_data_folder 固定存程序目录 profile/ 下
   -> B 站等账号登录后,重启应用自动保持登录。
2. 网址记忆:每次页面跳转实时写回配置 last_url,启动时恢复。
3. 视频控制:通过注入 JS 操作页面里的 <video> 元素。
"""
import os

from PyQt6.QtCore import pyqtSignal

from qtwebview2 import QtWebView2Widget

from . import DATA_DIR
from .logger import get_logger

# 通用视频控制 JS(在 evaluate_js 的 async 包装里直接 return)
_JS_TOGGLE_PLAY = """
var v = document.querySelector('video');
if(!v) { return 'no-video'; }
if(v.paused){ v.play(); return 'play'; } else { v.pause(); return 'pause'; }
"""

_JS_PAUSE = """
var v = document.querySelector('video');
if(!v) { return 'no-video'; }
if(!v.paused){ v.pause(); return 'paused'; }
return 'already-paused';
"""

_JS_SEEK = """
var v = document.querySelector('video');
if(!v) { return 'no-video'; }
v.currentTime = Math.max(0, v.currentTime + %d);
return 'seeked';
"""

_JS_CHANGE_RATE = """
var v = document.querySelector('video');
if(!v) { return 'no-video'; }
var r = Math.min(16, Math.max(0.25, (v.playbackRate || 1) + %s));
v.playbackRate = r;
return 'rate=' + r;
"""

_JS_CHANGE_VOLUME = """
var v = document.querySelector('video');
if(!v) { return 'no-video'; }
var vol = Math.min(1, Math.max(0, (v.volume || 0.5) + %s));
v.volume = vol;
v.muted = false;
return 'vol=' + vol;
"""


class WebViewContainer(QtWebView2Widget):
    url_changed = pyqtSignal(str)
    page_title_changed = pyqtSignal(str)
    js_result = pyqtSignal(str)

    def __init__(self, config, parent=None):
        self._log = get_logger()
        self._config = config

        profile_dir = os.path.join(DATA_DIR, "profile")
        url = config.get("browser", "last_url", "https://www.bilibili.com")

        super().__init__(
            url=url,
            user_data_folder=profile_dir,
            context_menus=True,
            # 关键:新窗口(target=_blank / window.open)在当前窗口打开,
            # 不要跳到系统浏览器(官方妈宝 V6 同款行为)
            handle_new_window=False,
            init_settings_hook=self._on_core_ready,
            parent=parent,
        )
        self._log.info("恢复上次网址: %s", url)

    # ---------------- 页面事件 ----------------
    def _on_core_ready(self, core):
        """WebView2 核心初始化完成后:挂 URL/标题/新窗口事件 + 注入取消静音脚本。

        注意:这些事件在 .NET 线程触发,这里通过 Qt 信号安全转发到主线程。
        """
        try:
            core.SourceChanged += self._on_source_changed
            core.DocumentTitleChanged += self._on_title_changed
            # 新窗口请求 -> 在当前窗口打开(不跳系统浏览器)
            core.NewWindowRequested += self._on_new_window_requested
        except Exception:
            self._log.exception("挂载页面事件失败")
        self._inject_unmute_script(core)

    def _inject_unmute_script(self, core):
        """注入"自动取消静音"脚本(官方妈宝 V6 同款方案)。

        背景:Chromium 自动播放策略 —— 没有用户手势的自动播放会被强制静音。
        软件启动时自动加载的 B 站页面,视频默认静音,用户每次都要手动开声音。
        官方解法:每个页面创建前注入脚本,监听 <video> 元素出现,
        一旦发现就取消 muted(不改变播放状态,只恢复声音)。
        """
        script = r"""
        (function() {
            // 只取消静音,不强行 play:保持页面原有的播放/暂停状态,
            // 只保证声音不被浏览器自动播放策略静音(用户手动播放时直接有声)。
            function unmuteVideo(video) {
                if (video && video.muted) {
                    video.muted = false;
                }
            }
            function setupObserver() {
                if (!document.body) return false;
                var videos = document.querySelectorAll('video');
                videos.forEach(unmuteVideo);
                var observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.nodeType === 1) {
                                if (node.tagName === 'VIDEO') {
                                    unmuteVideo(node);
                                }
                                var nested = node.querySelectorAll && node.querySelectorAll('video');
                                if (nested) {
                                    nested.forEach(unmuteVideo);
                                }
                            }
                        });
                    });
                });
                observer.observe(document.body, { childList: true, subtree: true });
                return true;
            }
            if (!setupObserver()) {
                var bodyCheck = setInterval(function() {
                    if (setupObserver()) clearInterval(bodyCheck);
                }, 50);
                setTimeout(function() { clearInterval(bodyCheck); }, 10000);
            }
        })();
        """
        try:
            # 官方 V6 同款:AddScriptToExecuteOnDocumentCreatedAsync 在
            # 每个页面(document)创建时自动注入,无需每次导航重新执行。
            core.AddScriptToExecuteOnDocumentCreatedAsync(script)
            self._log.info("已注入自动取消静音脚本(官方同款)")
        except Exception:
            self._log.exception("注入取消静音脚本失败")

    def _on_new_window_requested(self, sender, args):
        """拦截新窗口请求,在当前窗口导航(官方 V6 同款:lambda u: load_url(u))。"""
        try:
            url = args.Uri
            args.Handled = True
            if url:
                self._log.info("新窗口请求,在当前窗口打开: %s", url)
                self.load_url(url)
        except Exception:
            self._log.exception("新窗口处理失败")

    def _on_source_changed(self, sender, args):
        try:
            url = sender.Source
            if url and not url.startswith("about:"):
                self._config.set("browser", "last_url", url, save=True)
                self.url_changed.emit(url)
        except Exception:
            pass

    def _on_title_changed(self, sender, args):
        try:
            self.page_title_changed.emit(sender.DocumentTitle)
        except Exception:
            pass

    # ---------------- 导航 ----------------
    def navigate(self, url_text):
        s = url_text.strip()
        if not s:
            return
        if "://" not in s:
            s = "https://" + s
        self.load_url(s)

    def go_home(self):
        self.load_url(self._config.get("browser", "home_url", "https://www.bilibili.com"))

    def back(self):
        """返回上一页。WebView2 的 CoreWebView2 是异步初始化的,
        未就绪时 GoBack 会抛异常;历史为空(CanGoBack=False)时 GoBack 无效果。
        两种情况都静默失败会让"返回按钮"看起来失效 —— 这里做显式检查+日志。"""
        try:
            core = getattr(self, "_webview", None)
            core = getattr(core, "CoreWebView2", None) if core is not None else None
            if core is None:
                self._log.warning("返回被忽略:WebView2 内核尚未初始化完成")
                return
            if not core.CanGoBack:
                self._log.info("返回被忽略:没有上一页可返回")
                return
            core.GoBack()
        except Exception:
            self._log.exception("返回上一页失败")

    def forward(self):
        """前进到下一页(与 back 同样的防呆处理)。"""
        try:
            core = getattr(self, "_webview", None)
            core = getattr(core, "CoreWebView2", None) if core is not None else None
            if core is None:
                self._log.warning("前进被忽略:WebView2 内核尚未初始化完成")
                return
            if not core.CanGoForward:
                self._log.info("前进被忽略:没有下一页可前进")
                return
            core.GoForward()
        except Exception:
            self._log.exception("前进到下一页失败")

    # ---------------- 视频控制 ----------------
    def run_js(self, script):
        self.evaluate_js(script, self._on_js_result)

    def _on_js_result(self, result_dict):
        """evaluate_js 回调:dict {'success': bool, 'result': ..., 'error': ...}"""
        if result_dict and result_dict.get("success"):
            r = result_dict.get("result")
            if r is not None:
                self.js_result.emit(str(r))
        else:
            err = (result_dict or {}).get("error")
            if err:
                self._log.warning("JS 执行失败: %s", err)

    def toggle_play(self):
        self.run_js(_JS_TOGGLE_PLAY)

    def pause(self):
        """无条件暂停(官方 9 隐藏窗口时暂停视频)。"""
        self.run_js(_JS_PAUSE)

    def seek(self, delta_sec):
        self.run_js(_JS_SEEK % delta_sec)

    def change_rate(self, delta):
        self.run_js(_JS_CHANGE_RATE % delta)

    def change_volume(self, delta):
        self.run_js(_JS_CHANGE_VOLUME % delta)
