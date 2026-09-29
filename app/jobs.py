"""任务管理与串行执行队列（免费档模型有速率限制，按串行处理）。"""
import queue
import threading

from .core import pipeline


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, pipeline.Job] = {}
        self._order: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.Lock()
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()

    def create(
        self,
        prompt: str,
        doc_type: str = "auto",
        att_purpose: str = "auto",
        attachments: list[dict] | None = None,
        kind: str = "generate",
    ) -> pipeline.Job:
        job = pipeline.Job(prompt, doc_type, att_purpose, attachments, kind)
        with self._lock:
            self._jobs[job.id] = job
        self._order.put(job.id)
        return job

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def get(self, job_id: str) -> pipeline.Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job.cancel_event.set()
        if job.status == "queued":
            job.status = "cancelled"
            job.emit({"type": "error", "message": "任务已取消。", "log": "", "tex": ""})
        return True

    def _worker(self) -> None:
        while True:
            job_id = self._order.get()
            job = self._jobs.get(job_id)
            if job is None or job.status == "cancelled":
                continue
            pipeline.run_job(job)


manager = JobManager()
