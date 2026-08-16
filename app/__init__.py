"""翻版妈宝 —— 游戏攻略伴侣小浏览器(自建版,参照官方妈宝 V6 重制)

纯本地、免费、无任何联网验证的应用。
技术栈:PyQt6 + WebView2(Edge 内核,官方 V6 同款方案)
"""

import os
import shutil
import sys

if getattr(sys, "frozen", False):
    # PyInstaller 打包后:程序本体在 exe 目录
    APP_DIR = os.path.dirname(sys.executable)
else:
    # 源码运行:项目根目录
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_NAME = "翻版妈宝"
__version__ = "2.1.1"

# ---------------- 数据目录(官方妈宝 V6 同款方案) ----------------
# 关键决策:数据(配置/登录态/日志)存在【用户主目录 ~/.mabao】,而不是 exe 目录。
# 这样更新/替换程序文件时,登录态和窗口状态完全不受影响(官方也是这么做的)。
# 用户可设置环境变量 MABAO_CONFIG_DIR 自定义位置。
def _get_data_dir():
    env = os.environ.get("MABAO_CONFIG_DIR", "").strip()
    if env:
        return os.path.abspath(env)
    home = os.path.expanduser("~")
    return os.path.join(home, ".mabao")


DATA_DIR = _get_data_dir()


def _migrate_legacy_data():
    """把旧版本(exe 目录下的 config.json/profile/logs)迁移到用户目录。

    只迁移一次:用户目录里还没有对应文件时才复制,避免覆盖新数据。
    迁移后旧文件保留(不删),防止误删。
    """
    try:
        legacy_items = [
            ("config.json", "config.json"),
            ("profile", "profile"),
            ("logs", "logs"),
        ]
        for src_name, dst_name in legacy_items:
            src = os.path.join(APP_DIR, src_name)
            dst = os.path.join(DATA_DIR, dst_name)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    print(f"[迁移] {src_name} → {dst}")
                except Exception:
                    pass
    except Exception:
        pass


# 模块加载时执行一次迁移(幂等,第二次运行用户目录已有数据则跳过)
_migrate_legacy_data()
