@echo off
chcp 65001 >nul
title LaTeX 文档生成器
cd /d "%~dp0"

rem 读取 .env 中的端口（默认 8000）
set PORT=8000
for /f "tokens=1,* delims==" %%a in (.env) do (
  if /i "%%a"=="PORT" set PORT=%%b
)

rem 服务已在运行则直接打开页面，不重复启动
curl -s -o nul --max-time 2 http://127.0.0.1:%PORT%/api/health >nul 2>&1
if not errorlevel 1 (
  echo 服务已在运行，正在打开页面…
  if not "%LATEX_NO_BROWSER%"=="1" start "" http://127.0.0.1:%PORT%
  %SystemRoot%\System32\ping.exe -n 3 127.0.0.1 >nul
  exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"。
  pause
  exit /b 1
)

rem 延迟 2 秒待服务就绪后自动打开浏览器
if not "%LATEX_NO_BROWSER%"=="1" start "" /min cmd /c "%SystemRoot%\System32\ping.exe -n 3 127.0.0.1 >nul && start "" http://127.0.0.1:%PORT%"

echo ==============================================
echo   LaTeX 文档生成器 已启动
echo   页面地址: http://127.0.0.1:%PORT%
echo   关闭此窗口即停止服务
echo ==============================================
python -m app.main
pause
