"""FastAPI 入口：页面、任务接口（含附件上传与 PDF 转换）、历史记录、SSE 进度流、健康自检、优雅退出。"""
import json
import queue
import shutil
import threading
import time
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


@app.middleware("http")
async def no_cache_app_shell(request, call_next):
    """页面与静态资源要求每次使用前重新校验，避免浏览器缓存旧版脚本导致按钮失效。"""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response

# python -m app.main / start_app.pyw 启动时持有 uvicorn.Server，供「退出服务」使用
server_handle: dict = {"server": None}


class RecompileRequest(BaseModel):
    tex: str


class ConfigRequest(BaseModel):
    llm_api_key: str = ""


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/jobs")
async def create_job(
    prompt: str = Form(""),
    doc_type: str = Form("auto"),
    kind: str = Form("generate"),
    files: list[UploadFile] = File(default=[]),
):
    prompt = (prompt or "").strip()
    if kind not in ("generate", "convert"):
        raise HTTPException(400, "未知的任务类型")
    if kind == "generate" and not prompt:
        raise HTTPException(400, "需求描述不能为空")
    if kind == "convert" and not prompt:
        prompt = "将 PDF 转换为 LaTeX 文档"
    if doc_type not in prompts.DOC_TYPES:
        raise HTTPException(400, "未知的文档类型")

    # 先校验所有附件，再统一落盘、入队，避免产生无效任务
    metas = []
    for f in files or []:
        name = Path(f.filename or "file").name
        ext = Path(name).suffix.lower()
        if ext not in config.ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的附件类型：{name}（支持 tex/txt/md/pdf/png/jpg/webp）")
        metas.append((f, name, ext))

    if kind == "convert" and not any(ext == ".pdf" for _, _, ext in metas):
        raise HTTPException(400, "PDF 转换任务需要上传一个 PDF 文件")

    attachments = []
    if metas:
        stage_dir = config.UPLOADS_DIR / uuid.uuid4().hex[:12]
        stage_dir.mkdir(parents=True, exist_ok=True)
        limit = config.MAX_UPLOAD_MB * 1024 * 1024
        for f, name, ext in metas:
            i = len(attachments)
            dest = stage_dir / f"{i:02d}_{name}"
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
                att_kind = "image"
            elif ext == ".tex":
                att_kind = "tex"
            elif ext == ".pdf":
                att_kind = "pdf"
            else:
                att_kind = "text"
            attachments.append({"name": name, "kind": att_kind, "path": str(dest)})

    job = jobs.manager.create(prompt, doc_type, attachments, kind)
    return {"job_id": job.id}


# ---------- 任务详情 / 历史 ----------

def _read_meta(job_id: str) -> dict | None:
    meta_path = config.WORKSPACE_DIR / job_id / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _job_payload(job_id: str) -> dict | None:
    """优先取内存任务，否则从磁盘 meta.json 回退（重启后历史任务仍可查看/重编译）。"""
    job = jobs.manager.get(job_id)
    if job:
        return {
            "job_id": job.id,
            "kind": job.kind,
            "status": job.status,
            "prompt": job.prompt,
            "tex": job.tex,
            "pdf_url": job.pdf_url,
            "error": job.error,
        }
    meta = _read_meta(job_id)
    if not meta:
        return None
    d = config.WORKSPACE_DIR / job_id
    tex = ""
    tex_file = d / "main.tex"
    if tex_file.is_file():
        tex = tex_file.read_text(encoding="utf-8", errors="replace")
    return {
        "job_id": job_id,
        "kind": meta.get("kind", "generate"),
        "status": meta.get("status", "unknown"),
        "prompt": meta.get("prompt", ""),
        "tex": tex,
        "pdf_url": f"/workspace/{job_id}/main.pdf" if (d / "main.pdf").is_file() else "",
        "error": meta.get("error", ""),
    }


@app.get("/api/jobs/{job_id}")
def job_info(job_id: str):
    data = _job_payload(job_id)
    if not data:
        raise HTTPException(404, "任务不存在")
    return data


@app.get("/api/history")
def history():
    items = []
    if config.WORKSPACE_DIR.is_dir():
        for d in config.WORKSPACE_DIR.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            meta = _read_meta(d.name)
            if not meta:
                continue
            items.append({
                "id": meta.get("id", d.name),
                "kind": meta.get("kind", "generate"),
                "status": meta.get("status", "unknown"),
                "prompt": meta.get("prompt", ""),
                "doc_type": meta.get("doc_type", ""),
                "created_at": meta.get("created_at", 0),
                "has_pdf": (d / "main.pdf").is_file(),
                "has_tex": (d / "main.tex").is_file(),
            })
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"items": items[:100]}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    d = config.WORKSPACE_DIR / job_id
    if not d.is_dir():
        raise HTTPException(404, "任务不存在")
    shutil.rmtree(d, ignore_errors=True)
    jobs.manager.forget(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    job = jobs.manager.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在（历史任务不支持实时进度）")

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
    """手动修改源码后重新编译（历史任务重启服务后同样可用，直接基于磁盘操作）。"""
    tex = req.tex.strip()
    if "\\documentclass" not in tex:
        raise HTTPException(400, "这不是完整的 LaTeX 文档（缺少 \\documentclass）")
    job_dir = config.WORKSPACE_DIR / job_id
    if not job_dir.is_dir():
        raise HTTPException(404, "任务工作目录不存在")

    (job_dir / "main.tex").write_text(tex, encoding="utf-8")
    result = compiler.compile_tex(job_dir)

    job = jobs.manager.get(job_id)
    if job:
        job.tex = tex
        job.log = result.log
        if result.ok:
            job.pdf_url = f"/workspace/{job.id}/main.pdf"
            job.status = "done"
            job.error = ""
        else:
            job.status = "failed"
        job.save_meta()
    else:
        meta = _read_meta(job_id)
        if meta:
            meta["status"] = "done" if result.ok else "failed"
            meta["finished_at"] = time.time()
            try:
                (job_dir / "meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError:
                pass

    if result.ok:
        return {"ok": True, "pdf_url": f"/workspace/{job_id}/main.pdf", "log": result.log}
    return {"ok": False, "errors": error_fixer.extract_errors(result.log), "log": result.log}


@app.post("/api/shutdown")
def shutdown():
    """无窗口启动时，由页面按钮干净退出服务。"""
    server = server_handle.get("server")
    if not server:
        raise HTTPException(400, "当前以控制台方式启动：直接关闭命令行窗口即可停止服务")
    threading.Timer(0.6, setattr, args=(server, "should_exit", True)).start()
    return {"ok": True}


# ---------- API Key 配置 ----------

def _mask_key(key: str) -> str:
    return f"{key[:6]}····{key[-4:]}" if len(key) > 14 else "已配置"


@app.get("/api/config")
def get_config():
    configured = config.llm_configured()
    return {
        "llm_configured": configured,
        "llm_api_key_masked": _mask_key(config.LLM_API_KEY) if configured else "",
        "llm_model": config.LLM_MODEL,
        "vision_model": config.LLM_VISION_MODEL,
        "llm_base_url": config.LLM_BASE_URL,
    }


@app.post("/api/config")
def set_config(req: ConfigRequest):
    key = req.llm_api_key.strip()
    if not key or "在此填入" in key:
        raise HTTPException(400, "请粘贴有效的 API Key")
    config.save_env_value("LLM_API_KEY", key)
    if not config.llm_configured():
        raise HTTPException(500, "保存失败：请检查项目目录是否可写")
    return {"ok": True, "llm_api_key_masked": _mask_key(key)}


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

    from .core import first_run

    if not first_run.ensure_api_key():
        raise SystemExit(0)  # 用户取消了首次设置
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT))
    server_handle["server"] = server
    server.run()
