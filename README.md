# 翻版妈宝 · 游戏攻略伴侣小浏览器

> 纯本地、免费、无任何联网验证的游戏攻略小窗浏览器。参考官方"妈宝"的操作习惯重制,浏览器核心采用**官方 V6 同款方案**(WebView2 / Edge 现代 Chromium 内核)。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## ✨ 特性

- **置顶小窗浏览器**:打游戏时看攻略视频,小窗永远浮在最上层
- **全局热键**:游戏/任何软件前台时,直接按键控制视频,不用切回窗口
- **完全兼容 B 站**:WebView2(Edge 151 内核)实测首页/视频页/播放器/自动播放全部正常
- **登录态持久化**:数据存在用户目录 `~/.mabao`,更新程序不丢登录态(官方 V6 同款方案)
- **沉浸穿透模式**:按 0 进入穿透,导航栏隐藏 + 鼠标穿透,再按恢复
- **无卡密、无服务器、无心跳、无到期**:永久免费,纯本地运行

## 🎮 快捷键(全局热键,官方妈宝 V6 方案)

| 按键 | 功能 |
|---|---|
| `~`(Tab 上方反引号) | 播放 / 暂停 |
| `6` / `5` | 快进 / 快退 5 秒(按住连续) |
| `9` | 隐藏 / 显示窗口(隐藏时视频暂停、热键暂停) |
| `0` | 穿透模式(隐藏导航栏 + 鼠标穿透) |
| `Ctrl+Space` | 最大化 / 还原 |

> 热键使用**低级键盘钩子**(WH_KEYBOARD_LL + 独立线程),与游戏场景兼容;
> exe 请求管理员权限(和官方一样),确保在管理员权限的游戏窗口里热键也生效。

## 🖱️ 其他特性

- **鼠标悬停自动激活**:鼠标移到窗口上,播放器进度条正常弹出,点回游戏焦点即回归
- **无边框赛博风 UI**:边缘拖拽缩放
- **窗口状态完整恢复**:位置/大小/透明度/上次网址,关掉再开全保留

## 🚀 快速开始

```bash
# 需要 Python 3.10+
python -m pip install -r requirements.txt
python main.py
```

打包 exe:双击 `build.bat`,产物在 `dist\翻版妈宝\`(整个文件夹一起拷贝,双击 exe 即用)。

## 📁 项目结构

```
├── main.py                   # 入口
├── app/
│   ├── config.py             # 配置管理(状态保存/恢复,线程安全)
│   ├── hotkey_manager.py     # 全局热键(低级键盘钩子 + 长按连发)
│   ├── webview_container.py  # 浏览器核心(WebView2,登录态持久化 + 视频控制)
│   ├── main_window.py        # 主窗口(无边框赛博风 + 边缘缩放 + 悬停激活)
│   ├── theme.py              # 赛博主题
│   ├── logger.py             # 日志
│   └── utils/win32_api.py    # Win32 工具(鼠标穿透等)
├── build.bat                 # 打包脚本(PyInstaller + uac-admin)
└── requirements.txt
```

## 🛠️ 技术栈

Python 3.10+ / PyQt6 / **WebView2**(qtwebview2 库 + Edge Chromium 内核)/ pythonnet / pywin32

> **为什么用 WebView2 而不是 QtWebEngine**:反编译官方妈宝 V6.04 源码发现,
> 官方浏览器核心用的是 **WebView2(Edge 现代 Chromium 内核)**。QtWebEngine
> 内置内核老旧(Chromium 83 兼容性差),实测 B 站封面点击不跳转、播放器渲染不出来。
> 本应用采用官方同款方案,实测 B 站完全正常。

## 📝 开发排坑记录

1. **WebView2 需系统 Runtime**(Win10/11 自带);PyInstaller 打包需手动 `--add-data "qtwebview2/lib;lib"` 且路径必须是 `_internal/lib`
2. **WebView2 是原生子窗口**:会盖住 Qt 控件,边缘缩放手柄需容器内边距(8px)留出区域
3. **游戏前台时后台窗口 hover 失效**:WebView2(Chromium)在未激活窗口不处理 hover → 鼠标移入时自动激活窗口
4. **`threading.Lock` 不可重入**:Config 持锁时再调 save() 会死锁,先释放锁再落盘
5. **PyInstaller + uac-admin**:游戏以管理员运行时,普通权限程序的键盘钩子收不到按键(UIPI 隔离),exe 必须请求管理员权限
6. **数据与程序分离**:配置/登录态存用户目录 `~/.mabao`,更新程序不丢数据(官方同款方案)

## ⚖️ 免责声明

本工具是参考官方"妈宝"操作习惯重制的学习项目,纯本地运行,不包含官方任何代码。请勿用于商业用途。
