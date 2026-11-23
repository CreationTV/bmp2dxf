@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title bmp2dxf - 位图转矢量工作台

echo ============================================
echo   bmp2dxf 位图转 DXF - 本地 Web 工作台
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 没有找到 Python 虚拟环境 .venv
    echo.
    echo 请先双击运行 "安装依赖.bat" 完成安装；
    echo 或手动执行以下命令：
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo     .venv\Scripts\python.exe -m pip install -e .
    echo.
    pause
    exit /b 1
)

echo [启动] 正在启动本地 Web 服务，稍后会自动打开浏览器...
echo [提示] 关闭本窗口或按 Ctrl+C 即可停止服务。
echo.

".venv\Scripts\python.exe" -m bmp2dxf.web --open %*

if errorlevel 1 (
    echo.
    echo [提示] 服务已退出。若提示端口被占用，可换一个端口重试，例如：
    echo     "启动工具.bat" --port 8899
)

echo.
pause
endlocal
