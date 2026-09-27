"""FastAPI 入口：页面、任务接口（含附件上传）、SSE 进度流、健康自检。"""
import json
import queue
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs
from .core import compiler, config, error_fixer, prompts

app = FastAPI(title="LaTeX 文档生成器")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class RecompileRequest(BaseModel):
    tex: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/jobs")
async def create_job(
    prompt: str = Form(...),
    doc_type: str = Form("auto"),
    att_purpose: str = Form("auto"),
    files: list[UploadFile] = File(default=[]),
):
    prompt = (prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "需求描述不能为空")
    if doc_type not in prompts.DOC_TYPES:
        raise HTTPException(400, "未知的文档类型")
    if att_purpose not in ("auto", "format", "content"):
        raise HTTPException(400, "未知的附件用途")

    # 先校验所有附件，再统一落盘、入队，避免产生无效任务
    metas = []
    for f in files or []:
        name = Path(f.filename or "file").name
        ext = Path(name).suffix.lower()
        if ext not in config.ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的附件类型：{name}（支持 tex/txt/md/pdf/png/jpg/webp）")
        metas.append((f, name, ext))

    attachments = []
    if metas:
        stage_dir = config.UPLOADS_DIR / uuid.uuid4().hex[:12]
        stage_dir.mkdir(parents=True, exist_ok=True)
        limit = config.MAX_UPLOAD_MB * 1024 * 1024
        for f, name, ext in metas:
            dest = stage_dir / f"{len(attachments):02d}_{name}"
            size = 0
            try:
                with dest.open("wb") as out:
                    while chunk := await f.read(1024 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(400, f"附件 {name} 超过 {config.MAX_UPLOAD_MB}MB 限制")
                        out.write(chunk)
            finally:
                await f.close()
            if ext in config.IMAGE_EXTS:
                kind = "image"
            elif ext == ".tex":
                kind = "tex"
            elif ext == ".pdf":
                kind = "pdf"
            else:
                kind = "text"
            attachments.append({"name": name, "kind": kind, "path": str(dest)})

    job = jobs.manager.create(prompt, doc_type, att_purpose, attachments)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_info(job_id: str):
    job = jobs.manager.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return {
        "job_id": job.id,
        "status": job.status,
        "tex": job.tex,
        "pdf_url": job.pdf_url,
        "error": job.error,
    }


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    job = jobs.manager.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")

    def gen():
        # 任务已结束时（页面刷新后重连等），无需再推流
        terminal = job.status in ("done", "failed", "cancelled")
        while True:
            try:
                event = job.events.get(timeout=1.0)
            except queue.Empty:
                if terminal:
                    break
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if not jobs.manager.cancel(job_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/recompile")
def recompile(job_id: str, req: RecompileRequest):
    """用户手动修改源码后重新编译（同步执行，编译期间由线程池承载）。"""
    job = jobs.manager.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    tex = req.tex.strip()
    if "\\documentclass" not in tex:
        raise HTTPException(400, "这不是完整的 LaTeX 文档（缺少 \\documentclass）")
    job_dir = config.WORKSPACE_DIR / job.id
    if not job_dir.is_dir():
        raise HTTPException(404, "任务工作目录不存在，请重新生成")
    (job_dir / "main.tex").write_text(tex, encoding="utf-8")
    job.tex = tex
    result = compiler.compile_tex(job_dir)
    job.log = result.log
    if result.ok:
        job.pdf_url = f"/workspace/{job.id}/main.pdf"
        job.status = "done"
        job.error = ""
        return {"ok": True, "pdf_url": job.pdf_url, "log": result.log}
    job.status = "failed"
    return {"ok": False, "errors": error_fixer.extract_errors(result.log), "log": result.log}


@app.get("/api/health")
def health():
    tectonic = config.find_tectonic()
    return {
        "llm_configured": config.llm_configured(),
        "llm_base_url": config.LLM_BASE_URL,
        "llm_model": config.LLM_MODEL,
        "vision_model": config.LLM_VISION_MODEL,
        "tectonic_found": bool(tectonic),
        "tectonic_path": tectonic,
        "doc_types": [
            {"key": key, "label": info["label"]} for key, info in prompts.DOC_TYPES.items()
        ],
    }


# workspace 下按任务 ID 存放 tex/pdf/日志，供浏览器直接预览与下载
app.mount("/workspace", StaticFiles(directory=config.WORKSPACE_DIR), name="workspace")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
