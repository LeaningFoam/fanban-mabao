@echo off
chcp 65001 >nul
cd /d %~dp0

echo ============================================
echo   翻版妈宝 打包脚本 (PyInstaller + WebView2)
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python,请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
python -m pip install -r requirements.txt pyinstaller

echo [2/4] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] 定位 WebView2 SDK DLL 路径...
for /f "delims=" %%i in ('python -c "import site,os; print(os.path.join(site.getsitepackages()[0],'qtwebview2','lib'))"') do set WV2LIB=%%i
if not exist "%WV2LIB%\Microsoft.Web.WebView2.Core.dll" (
    echo [错误] 未找到 qtwebview2 的 WebView2 DLL,请确认依赖安装成功
    pause
    exit /b 1
)

echo [4/4] 打包中(onedir 模式)...
rem 关键参数说明:
rem   --add-data "%WV2LIB%;lib"  WebView2 DLL 必须放在 _internal\lib\ 下
rem   (qtwebview2 库在打包后从 sys._MEIPASS\lib 加载 DLL,路径不能错)
rem   --uac-admin             请求管理员权限(官方妈宝 V6 同款):游戏以管理员运行时,
rem                           普通权限的键盘钩子收不到按键(UIPI 隔离),热键会全部失效。
python -m PyInstaller --noconfirm --windowed --uac-admin --name "翻版妈宝" --add-data "%WV2LIB%;lib" --hidden-import qtwebview2 --hidden-import clr --collect-all pythonnet main.py

echo.
echo 打包完成!程序在 dist\翻版妈宝\翻版妈宝.exe
echo 说明:整个 dist\翻版妈宝 文件夹都可以移动/拷贝,双击 exe 即用。
echo       登录数据保存在程序同目录 profile\ 下,换机时一起拷贝即可保留登录态。
echo       要求系统已安装 WebView2 Runtime(Win10/11 自带)。
pause
