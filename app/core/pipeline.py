"""任务流水线：识别附件 → 生成 LaTeX → 编译 → 失败则带错误日志回喂模型修复 → 循环。

支持两种任务：kind="generate"（按需求生成）、kind="convert"（PDF 转 LaTeX，近似重建）。

在工作线程中运行，通过 queue.Queue 向 SSE 端点推送事件：
  {"type": "stage",  "stage": "preparing"|"generating"|"compiling"|"fixing", "round": n}
  {"type": "token",  "text": "..."}
  {"type": "notice", "text": "..."}
  {"type": "done",   "pdf_url": "...", "tex": "...", "kind": "generate|convert"}
  {"type": "error",  "message": "...", "log": "...", "tex": "..."}
任务结束时把元数据写入 workspace/{id}/meta.json，供历史记录功能使用。
"""
import base64
import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from . import compiler, config, error_fixer, llm_client, prompts


class JobCancelled(Exception):
    pass


_FENCE = re.compile(r"```(?:latex|tex)?\s*\n(.*?)```", re.S)
_DOC = re.compile(r"(\\documentclass.*?\\end\{document\})", re.S)

_TEXT_PART_LIMIT = 15000  # 每个附件注入提示词的最大字符数
_IMAGE_DESC_LIMIT = 6000  # 单张图片识别结果的最大字符数
_PDF_TEXT_LIMIT = 30000   # PDF 转换时注入的最大字符数
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def extract_tex(raw: str) -> str | None:
    """从模型输出中提取完整 LaTeX 文档：优先带 \\\\documentclass 的代码块。"""
    for block in _FENCE.findall(raw):
        if "\\documentclass" in block:
            return block.strip()
    m = _DOC.search(raw)
    if m:
        return m.group(1).strip()
    if "\\documentclass" in raw:
        return raw.strip()
    blocks = _FENCE.findall(raw)
    if blocks:
        return blocks[0].strip()
    return None


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…（内容过长，已截断）"


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:20])
    if not text.strip():
        raise ValueError("没有可提取的文本（可能是扫描件），请改传图片或选择其他 PDF")
    return text


def _image_data_url(path: Path) -> str:
    mime = _MIME.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _prepare_attachments(job: "Job") -> str:
    """处理各附件：tex/文本直接读取，PDF 提取文本，图片走视觉模型。

    只做内容提取与中性类型标注，不做用途推断——附件怎么用由用户写在需求描述里。
    """
    parts: list[dict] = []
    for att in job.attachments:
        name = att["name"]
        path = Path(att["path"])
        try:
            if att["kind"] == "tex":
                label = "LaTeX 源码"
                text = path.read_text(encoding="utf-8", errors="replace")
            elif att["kind"] == "pdf":
                label = "PDF 提取文本"
                text = _pdf_text(path)
            else:
                label = "文本内容"
                text = path.read_text(encoding="utf-8", errors="replace")
            parts.append({"label": label, "name": name, "text": _clip(text, _TEXT_PART_LIMIT)})
        except Exception as e:
            job.emit({"type": "notice", "text": f"⚠ 附件 {name} 处理失败，已跳过：{e}"})

    for att in [a for a in job.attachments if a["kind"] == "image"]:
        name = att["name"]
        job.emit({"type": "notice", "text": f"正在用视觉模型识别图片 {name}…"})
        try:
            desc = llm_client.describe_images(_image_data_url(Path(att["path"])))
            parts.append({
                "label": "图片识别结果", "name": name, "text": _clip(desc, _IMAGE_DESC_LIMIT),
            })
        except Exception as e:
            job.emit({"type": "notice", "text": f"⚠ 图片 {name} 识别失败，已跳过：{e}"})

    return prompts.build_attachment_section(parts)


class Job:
    def __init__(
        self,
        prompt: str,
        doc_type: str = "auto",
        attachments: list[dict] | None = None,
        kind: str = "generate",
    ):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind  # generate / convert
        self.prompt = prompt
        self.doc_type = doc_type
        self.attachments = attachments or []
        self.status = "queued"  # queued / running / done / failed / cancelled
        self.created_at = time.time()
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.tex = ""
        self.pdf_url = ""
        self.log = ""
        self.error = ""

    def emit(self, event: dict) -> None:
        self.events.put(event)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled()

    def meta(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "prompt": self.prompt,
            "doc_type": self.doc_type,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": time.time(),
            "error": self.error,
            "attachments": [
                {"name": a["name"], "role": a.get("role", "auto")} for a in self.attachments
            ],
        }

    def save_meta(self) -> None:
        """把任务元数据写入磁盘，供历史记录在重启后仍可查看。"""
        try:
            d = config.WORKSPACE_DIR / self.id
            d.mkdir(parents=True, exist_ok=True)
            (d / "meta.json").write_text(
                json.dumps(self.meta(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass


def _collect(job: Job, messages: list[dict], temperature: float = 0.35) -> str:
    """流式收集模型输出，逐 token 推送给前端。"""
    buf: list[str] = []
    for piece in llm_client.stream_chat(
        messages, cancel_event=job.cancel_event, temperature=temperature
    ):
        job._check_cancel()
        buf.append(piece)
        job.emit({"type": "token", "text": piece})
    return "".join(buf)


def run_job(job: Job) -> None:
    job.status = "running"
    try:
        if job.kind == "convert":
            pdf_att = next((a for a in job.attachments if a["kind"] == "pdf"), None)
            if not pdf_att:
                raise RuntimeError("PDF 转换任务需要一个 PDF 附件")
            text = _clip(_pdf_text(Path(pdf_att["path"])), _PDF_TEXT_LIMIT)
            job.emit({
                "type": "notice",
                "text": f"已提取 PDF 文本（约 {len(text)} 字），正在由模型重建 LaTeX（结果为近似转换，仅供格式参考）…",
            })
            messages = [
                {"role": "system", "content": prompts.CONVERT_SYSTEM_PROMPT},
                {"role": "user", "content": prompts.build_convert_prompt(text)},
            ]
        else:
            attachment_context = ""
            if job.attachments:
                job.emit({"type": "stage", "stage": "preparing"})
                attachment_context = _prepare_attachments(job)
            job.emit({"type": "stage", "stage": "generating"})
            user_content = prompts.build_user_prompt(job.prompt, job.doc_type)
            if attachment_context:
                user_content += "\n\n" + attachment_context
            messages = [
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

        if job.kind == "convert":
            job.emit({"type": "stage", "stage": "generating"})
        raw = _collect(job, messages)
        tex = extract_tex(raw)
        if not tex:
            raise RuntimeError(
                "模型没有返回有效的 LaTeX 文档，请重试；或在需求中更明确地描述文档类型与结构。"
            )

        job_dir = config.WORKSPACE_DIR / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        tex_path = job_dir / "main.tex"

        total_rounds = 1 + config.MAX_FIX_ROUNDS
        for attempt in range(total_rounds):
            tex_path.write_text(tex, encoding="utf-8")
            job.tex = tex
            job.emit({"type": "stage", "stage": "compiling", "round": attempt + 1})
            if attempt == 0:
                job.emit({
                    "type": "notice",
                    "text": "首次编译某类文档时，Tectonic 需联网下载宏包，请耐心等待。",
                })
            result = compiler.compile_tex(job_dir)
            job.log = result.log
            if result.ok:
                job.pdf_url = f"/workspace/{job.id}/main.pdf"
                job.status = "done"
                job.save_meta()
                job.emit({"type": "done", "pdf_url": job.pdf_url, "tex": job.tex, "kind": job.kind})
                return

            errors = error_fixer.extract_errors(result.log)
            if attempt == total_rounds - 1:
                break

            job.emit({"type": "stage", "stage": "fixing", "round": attempt + 1})
            fix_messages = [
                {"role": "system", "content": prompts.FIX_SYSTEM_PROMPT},
                {"role": "user", "content": prompts.build_fix_prompt(tex, errors)},
            ]
            raw = _collect(job, fix_messages, temperature=0.2)
            fixed = extract_tex(raw)
            if fixed:
                tex = fixed

        job.status = "failed"
        job.error = (
            f"自动修复 {config.MAX_FIX_ROUNDS} 轮后仍编译失败。"
            "可在「LaTeX 源码」页手动修改后点击「重新编译」。"
        )
        job.save_meta()
        job.emit({"type": "error", "message": job.error, "log": job.log, "tex": job.tex})
    except JobCancelled:
        job.status = "cancelled"
        job.save_meta()
        job.emit({"type": "error", "message": "任务已取消。", "log": job.log, "tex": job.tex})
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.save_meta()
        job.emit({"type": "error", "message": str(e), "log": job.log, "tex": job.tex})
