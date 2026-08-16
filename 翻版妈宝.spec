# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Users/w/WorkBuddy/2026-08-15-13-20-20/.venv/Lib/site-packages/qtwebview2/lib', 'lib')]
binaries = []
hiddenimports = ['qtwebview2', 'clr']
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='翻版妈宝',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 关键:请求管理员权限(官方妈宝 V6 同款 requireAdministrator)。
    # 游戏(原神等)常以管理员运行,普通权限程序的键盘钩子受 UIPI 隔离
    # 收不到管理员窗口的按键 → 游戏里热键全部失效。uac_admin=True 后
    # 启动会弹一次 UAC 确认,但钩子能覆盖管理员权限的游戏窗口。
    uac_admin=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='翻版妈宝',
)
