@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   bmp2dxf 位图转 DXF 工具 - 安装依赖
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python。请先安装 Python 3.10 或更高版本：
    echo        https://www.python.org/downloads/
    echo        安装时请勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
) else (
    echo [1/3] 虚拟环境已存在，跳过创建。
)

echo [2/3] 安装 Python 依赖 ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接后重试。
    pause
    exit /b 1
)

echo [3/3] 以可编辑模式安装 bmp2dxf ...
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
    echo [警告] 可编辑安装失败，但直接运行仍可使用。
)

echo.
echo 安装完成！双击 "启动工具.bat" 即可使用。
echo.
pause
