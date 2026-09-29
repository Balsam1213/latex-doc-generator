"""无窗口启动器：用 pythonw 运行，不出现命令提示符窗口。

行为：
- 若服务已在运行 → 直接打开浏览器页面后退出
- 否则后台启动服务，2 秒后自动打开浏览器
- 停止方式：页面右上角「⏻ 退出服务」按钮（服务干净退出，本进程随之结束）
"""
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _read_env(key: str, default: str) -> str:
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.upper().startswith(key.upper() + "="):
                return line.split("=", 1)[1].strip() or default
    return default


HOST = _read_env("HOST", "127.0.0.1")
PORT = _read_env("PORT", "8000")
URL = f"http://127.0.0.1:{PORT}"


def _service_running() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/health", timeout=2):
            return True
    except Exception:
        return False


if _service_running():
    webbrowser.open(URL)
else:
    if not os.environ.get("LATEX_NO_BROWSER"):
        threading.Timer(2.0, webbrowser.open, args=(URL,)).start()
    from app.main import app, server_handle

    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=int(PORT)))
    server_handle["server"] = server
    server.run()
