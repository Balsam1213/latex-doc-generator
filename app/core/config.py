"""全局配置：从项目根目录的 .env 读取，所有项都有默认值。"""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default: str) -> str:
    value = os.environ.get(key, "").strip()
    return value if value else default


LLM_BASE_URL = _get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
LLM_API_KEY = _get("LLM_API_KEY", "")
LLM_MODEL = _get("LLM_MODEL", "glm-4.5-flash")
LLM_VISION_MODEL = _get("LLM_VISION_MODEL", "glm-4.6v-flash")
LLM_MAX_TOKENS = int(_get("LLM_MAX_TOKENS", "8192"))
MAX_FIX_ROUNDS = int(_get("MAX_FIX_ROUNDS", "3"))
COMPILE_TIMEOUT = int(_get("COMPILE_TIMEOUT", "180"))
MAX_UPLOAD_MB = int(_get("MAX_UPLOAD_MB", "10"))
HOST = _get("HOST", "127.0.0.1")
PORT = int(_get("PORT", "8000"))

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTS = {".tex", ".txt", ".md", ".markdown"}
PDF_EXTS = {".pdf"}
ALLOWED_EXTS = IMAGE_EXTS | TEXT_EXTS | PDF_EXTS

VENDOR_DIR = BASE_DIR / "vendor"
WORKSPACE_DIR = BASE_DIR / "workspace"
UPLOADS_DIR = WORKSPACE_DIR / "_uploads"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def find_tectonic() -> str | None:
    """依次查找 vendor/tectonic.exe、vendor/tectonic、PATH 中的 tectonic。"""
    exe = "tectonic.exe" if os.name == "nt" else "tectonic"
    for candidate in (VENDOR_DIR / exe, VENDOR_DIR / "tectonic"):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("tectonic")


def llm_configured() -> bool:
    return bool(LLM_API_KEY) and "在此填入" not in LLM_API_KEY


def save_env_value(key: str, value: str) -> None:
    """把一个配置项写回 .env（存在则替换，否则追加），并立即更新本进程的运行时值。"""
    env_path = BASE_DIR / ".env"
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.strip().upper().startswith(f"{key.upper()}="):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    globals()[key] = value
