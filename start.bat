@echo off
setlocal
chcp 65001 >nul
title Chip Test HUB - Launcher

rem Always run from this script directory
cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║        芯片测试可视化 HUB - 一键启动脚本                ║
echo ║        Chip Test HUB - One-click Launcher              ║
echo ╚════════════════════════════════════════════════════════╝
echo.

echo [1/6] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [错误] 未检测到 Python。请安装 Python 3.8 或更高版本，并勾选 Add to PATH。
  pause
  exit /b 1
)
echo [√] Python 可用
echo.

set "VENV_DIR=.venv"

echo [2/6] 检查虚拟环境 "%VENV_DIR%"...
if not exist "%VENV_DIR%" (
  echo [!] 未找到虚拟环境，正在创建...
  python -m venv "%VENV_DIR%"
  if %errorlevel% neq 0 (
    echo [错误] 虚拟环境创建失败
    pause
    exit /b 1
  )
  echo [√] 虚拟环境创建成功
) else (
  echo [√] 虚拟环境已存在
)
echo.

echo [3/6] 激活虚拟环境...
call "%VENV_DIR%\Scripts\activate.bat"
if %errorlevel% neq 0 (
  echo [错误] 虚拟环境激活失败
  pause
  exit /b 1
)
echo [√] 已激活
echo.

echo [4/6] 安装依赖...
if not exist "requirements.txt" (
  echo [错误] 未找到 requirements.txt
  pause
  exit /b 1
)

python -m pip install --upgrade pip --quiet --disable-pip-version-check
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
  echo [错误] 依赖安装失败。你可以把命令行输出截图给我排查。
  pause
  exit /b 1
)
echo [√] 依赖安装完成
echo.

echo [5/6] 创建必要目录...
if not exist "logs" mkdir "logs"
if not exist "uploads" mkdir "uploads"
if not exist "exports" mkdir "exports"
if not exist "test_results" mkdir "test_results"
echo [√] 目录就绪
echo.

echo [6/6] 启动 HUB...
echo.
echo 访问地址: http://127.0.0.1:5000
echo 停止服务: Ctrl + C
echo.

python app.py

echo.
echo [!] HUB 已退出
pause

