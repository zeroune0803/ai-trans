@echo off
REM ============================================================
REM  translate_agent 统一启动入口
REM  确保始终使用 conda 环境解释器，避免 PATH 漂移到系统 Python
REM ============================================================
cd /d "%~dp0"
set PYTHON_EXE=E:\Dev\.conda\python.exe

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=E:\Dev\.conda\.conda\python.exe
)

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=E:\Dev\.venv\Scripts\python.exe
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 找不到 Python 解释器: %PYTHON_EXE%
    echo 请确认 Python 环境存在于以下任一路径：
    echo   E:\Dev\.conda\python.exe
    echo   E:\Dev\.conda\.conda\python.exe
    echo   E:\Dev\.venv\Scripts\python.exe
    pause
    exit /b 1
)

echo [*] 使用解释器: %PYTHON_EXE%
echo [*] 工作目录:   %CD%
echo.

REM 如果当前会话未带入密钥，则从用户环境变量回填（避免新终端未重载）
if "%OPENAI_API_KEY%"=="" (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`) do set "OPENAI_API_KEY=%%A"
)
if "%OPENAI_BASE_URL%"=="" (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_BASE_URL','User')"`) do set "OPENAI_BASE_URL=%%A"
)

if "%OPENAI_API_KEY%"=="" (
    echo [ERROR] OPENAI_API_KEY 未设置，无法启动服务。
    echo 请先执行: setx OPENAI_API_KEY "你的密钥"
    pause
    exit /b 1
)

echo [*] 启动前自动清理 7 天前临时文件...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\cleanup_old_files.ps1" -RetentionDays 7
if errorlevel 1 (
    echo [WARN] 自动清理执行异常，继续启动服务。
)

"%PYTHON_EXE%" app.py %*
