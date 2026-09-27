"""Tectonic 子进程封装：编译 tex 文件，返回结果与完整日志。"""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class CompileResult:
    ok: bool
    log: str
    pdf_path: Path | None


def compile_tex(job_dir: Path, tex_name: str = "main.tex") -> CompileResult:
    tectonic = config.find_tectonic()
    if not tectonic:
        return CompileResult(
            False,
            "未找到 Tectonic 编译器：请把 tectonic.exe 放入项目 vendor/ 目录"
            "（或运行 python download_tectonic.py 自动下载）。",
            None,
        )

    cmd = [tectonic, "--keep-logs", tex_name]
    try:
        proc = subprocess.run(
            cmd,
            cwd=job_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.COMPILE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            False,
            f"编译超时（超过 {config.COMPILE_TIMEOUT} 秒）。"
            "首次编译某类文档需联网下载宏包，可能较慢；"
            "可在 .env 中调大 COMPILE_TIMEOUT 后重试。",
            None,
        )

    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    pdf_path = job_dir / tex_name.replace(".tex", ".pdf")
    ok = proc.returncode == 0 and pdf_path.is_file()
    if ok:
        return CompileResult(True, log, pdf_path)
    if not log:
        log = f"编译失败：tectonic 退出码 {proc.returncode}，但没有输出任何日志。"
    return CompileResult(False, log, None)
