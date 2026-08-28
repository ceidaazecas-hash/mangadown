import asyncio
import time
from typing import Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field, asdict

@dataclass
class TaskProgress:
    task_id: str
    manga_title: str
    format: str # pdf, epub, cbz
    bundle_mode: str # single, zip
    status: str = "pending" # pending, scraping, downloading, packaging, completed, error, cancelled
    progress_percent: float = 0.0
    message: str = "Initializing download task..."
    current_chapter: str = ""
    current_chapter_idx: int = 0
    total_chapters: int = 0
    current_page: int = 0
    total_pages_in_chapter: int = 0
    total_pages_downloaded: int = 0
    total_pages_overall: int = 0
    file_id: Optional[str] = None
    filename: Optional[str] = None
    file_size_bytes: int = 0
    file_size_formatted: str = ""
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_cancelled: bool = False

class ProgressTracker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgressTracker, cls).__new__(cls)
            cls._instance.tasks = {}
            cls._instance.subscribers = {}
        return cls._instance

    def create_task(self, task_id: str, manga_title: str, format: str, bundle_mode: str, total_chapters: int = 0) -> TaskProgress:
        task = TaskProgress(
            task_id=task_id,
            manga_title=manga_title,
            format=format,
            bundle_mode=bundle_mode,
            total_chapters=total_chapters
        )
        self.tasks[task_id] = task
        self.subscribers[task_id] = []
        return task

    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs):
        task = self.tasks.get(task_id)
        if not task:
            return
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = time.time()

        # Notify any active SSE subscribers
        data = asdict(task)
        for queue in self.subscribers.get(task_id, []):
            try:
                queue.put_nowait(data)
            except Exception:
                pass

    def cancel_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task:
            task.is_cancelled = True
            task.status = "cancelled"
            task.message = "Task cancelled by user."
            self.update_task(task_id)

    async def subscribe(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        task = self.tasks.get(task_id)
        if not task:
            yield {"error": "Task not found"}
            return

        queue = asyncio.Queue()
        if task_id not in self.subscribers:
            self.subscribers[task_id] = []
        self.subscribers[task_id].append(queue)

        # Send initial snapshot
        yield asdict(task)

        try:
            while True:
                data = await queue.get()
                yield data
                if data.get("status") in ("completed", "error", "cancelled"):
                    break
        finally:
            if task_id in self.subscribers and queue in self.subscribers[task_id]:
                self.subscribers[task_id].remove(queue)
