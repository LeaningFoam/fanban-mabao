"""赛博朋克主题 —— 参考官方 V6 的视觉风格(毛玻璃 + 霓虹光效)。

配色体系:
  背景层   #0A0E17 (近黑深蓝)   #101624 (面板)
  霓虹青   #00E5FF (主强调/激活)
  霓虹品红 #FF2E88 (次强调/危险)
  电子紫   #7C4DFF (点缀)
  文字     #E6EDF3 (主)  #8B98A9 (次)
"""
from PyQt6.QtGui import QColor

# ---- 颜色常量 ----
BG_TOP = QColor("#0A0E17")
BG_BOTTOM = QColor("#101624")
PANEL = QColor("#131A2A")
PANEL_DARK = QColor("#0D1220")
NEON_CYAN = QColor("#00E5FF")
NEON_PINK = QColor("#FF2E88")
NEON_PURPLE = QColor("#7C4DFF")
TEXT_MAIN = QColor("#E6EDF3")
TEXT_DIM = QColor("#8B98A9")
TEXT_FAINT = QColor("#5A6678")
BORDER_GLOW = QColor("#1E2A44")
DANGER = QColor("#FF4D6D")

_MAIN_QSS = """
* {
    font-family: "Microsoft YaHei";
    outline: none;
}

QMainWindow, QWidget#Root {
    background-color: #0A0E17;
    color: #E6EDF3;
}

/* ---------- 标题栏 ---------- */
QWidget#TitleBar {
    background-color: rgba(16, 22, 36, 0.92);
    border-bottom: 1px solid #1E2A44;
}
QLabel#TitleText {
    color: #00E5FF;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 2px;
}
QLabel#TitleHint {
    color: #5A6678;
    font-size: 10px;
}
QPushButton#TitleBtn {
    background: transparent;
    border: none;
    color: #8B98A9;
    font-size: 14px;
    font-weight: bold;
    min-width: 34px;
    min-height: 26px;
    border-radius: 4px;
}
QPushButton#TitleBtn:hover {
    background: rgba(0, 229, 255, 0.12);
    color: #00E5FF;
}
QPushButton#TitleBtn:pressed {
    background: rgba(0, 229, 255, 0.22);
}
QPushButton#TitleBtnClose:hover {
    background: #FF2E88;
    color: #FFFFFF;
}
QPushButton#TitleBtnPin {
    border: 1px solid #1E2A44;
}
QPushButton#TitleBtnPin[active="true"] {
    border: 1px solid #00E5FF;
    color: #00E5FF;
    background: rgba(0, 229, 255, 0.10);
}

/* ---------- 工具栏 ---------- */
QWidget#ToolBar {
    background-color: rgba(13, 18, 32, 0.9);
    border-bottom: 1px solid #1E2A44;
}
QPushButton#ToolBtn {
    background: transparent;
    border: 1px solid #1E2A44;
    color: #8B98A9;
    font-size: 12px;
    min-width: 30px;
    min-height: 24px;
    border-radius: 5px;
}
QPushButton#ToolBtn:hover {
    border-color: #00E5FF;
    color: #00E5FF;
}
QPushButton#ToolBtn:pressed {
    background: rgba(0, 229, 255, 0.15);
}
QLineEdit#UrlEdit {
    background: #0D1220;
    border: 1px solid #1E2A44;
    border-radius: 5px;
    padding: 4px 10px;
    color: #E6EDF3;
    font-size: 12px;
    selection-background-color: #7C4DFF;
}
QLineEdit#UrlEdit:focus {
    border-color: #00E5FF;
}

/* ---------- 状态栏 ---------- */
QWidget#StatusBar {
    background-color: rgba(13, 18, 32, 0.95);
    border-top: 1px solid #1E2A44;
}
QLabel#StatusText {
    color: #8B98A9;
    font-size: 11px;
}
QLabel#StatusText[accent="true"] {
    color: #00E5FF;
}
QLabel#StatusText[warn="true"] {
    color: #FF2E88;
}

/* ---------- 滑块(透明度/音量) ---------- */
QSlider#MiniSlider::groove:horizontal {
    height: 3px;
    background: #1E2A44;
    border-radius: 1px;
}
QSlider#MiniSlider::handle:horizontal {
    width: 10px;
    margin: -4px 0;
    border-radius: 5px;
    background: #00E5FF;
    border: 1px solid #00E5FF;
}
QSlider#MiniSlider::sub-page:horizontal {
    background: #00E5FF;
    border-radius: 1px;
}

/* ---------- 菜单 ---------- */
QMenu {
    background-color: #101624;
    color: #E6EDF3;
    border: 1px solid #1E2A44;
    padding: 4px;
}
QMenu::item {
    padding: 5px 18px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: rgba(0, 229, 255, 0.15);
    color: #00E5FF;
}
QMenu::separator {
    height: 1px;
    background: #1E2A44;
    margin: 4px 8px;
}

QToolTip {
    background-color: #101624;
    color: #E6EDF3;
    border: 1px solid #00E5FF;
    padding: 4px 8px;
}
"""


def apply_theme(app):
    app.setStyleSheet(_MAIN_QSS)
