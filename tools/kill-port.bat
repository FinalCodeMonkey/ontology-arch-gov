@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo 用法: kill-port.bat ^<端口号^>
    echo 示例: kill-port.bat 8080
    exit /b 1
)

set PORT=%~1

echo 正在查找占用端口 %PORT% 的进程...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set PID=%%a
    goto :found
)

echo 未找到占用端口 %PORT% 的进程。
exit /b 0

:found
echo 找到进程 PID: !PID!

for /f "tokens=1,2" %%a in ('tasklist /fi "PID eq !PID!" /fo csv ^| findstr /v "PID"') do (
    set PROC_NAME=%%a
)

echo 进程名称: !PROC_NAME!
echo.

set /p CONFIRM=确认终止该进程？(y/n): 
if /i "!CONFIRM!"=="y" (
    taskkill /pid !PID! /f >nul 2>&1
    if !errorlevel! equ 0 (
        echo 已成功终止进程 PID: !PID!，端口 %PORT% 已释放。
    ) else (
        echo 终止失败，可能需要管理员权限。
    )
) else (
    echo 已取消。
)

endlocal
