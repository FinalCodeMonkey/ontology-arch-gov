@echo off
chcp 65001 >nul
cd /d "%~dp0"

set VENV_PYTHON=..\.venv\Scripts\python.exe
set PORT=8765

if "%1"=="stop" goto :stop
if "%1"=="restart" goto :restart

:start
if not exist "%VENV_PYTHON%" (
    echo ❌ 未找到虚拟环境 Python: %VENV_PYTHON%
    echo    请先在项目根目录执行: python -m venv .venv
    goto :end
)
echo 🚀 启动 BO 治理 API 服务 (端口 %PORT%)...
start "BO-API-Server" /MIN "%VENV_PYTHON%" bo-api-server.py --port %PORT%
REM 等待服务就绪
timeout /t 2 /nobreak >nul
echo ✅ 服务已启动，正在打开界面...
start http://127.0.0.1:%PORT%
echo    界面地址: http://127.0.0.1:%PORT%
echo.
echo    停止服务: %~nx0 stop
echo    重启服务: %~nx0 restart
goto :end

:stop
echo 🛑 停止 BO 治理 API 服务...
taskkill /FI "WINDOWTITLE eq BO-API-Server" /F 2>nul
REM 备选：按端口杀
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F 2>nul
)
echo ✅ 服务已停止
goto :end

:restart
call "%~f0" stop
timeout /t 1 /nobreak >nul
call "%~f0" start
goto :end

:end
