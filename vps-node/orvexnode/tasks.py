"""Proxmox-style asynchronous tasks identified by UPIDs."""

from __future__ import annotations

import os
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from .util import LOG, PveError, read_json, write_json_atomic

KEEP_SECONDS = 2 * 24 * 3600
MAX_LOG_LINES = 5000


class Task:
    def __init__(self, upid: str, node: str, dtype: str, item: str, user: str, pid: int, pstart: int, starttime: int):
        self.upid = upid
        self.node = node
        self.type = dtype
        self.id = item
        self.user = user
        self.pid = pid
        self.pstart = pstart
        self.starttime = starttime
        self.status = "running"
        self.exitstatus: Optional[str] = None
        self.endtime: Optional[int] = None
        self.lines: List[str] = []
        self._lock = threading.Lock()

    def log(self, message: str) -> None:
        with self._lock:
            for line in str(message).splitlines() or [""]:
                if len(self.lines) < MAX_LOG_LINES:
                    self.lines.append(line)

    def finish(self, exitstatus: str) -> None:
        with self._lock:
            self.status = "stopped"
            self.exitstatus = exitstatus
            self.endtime = int(time.time())

    def as_status(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "upid": self.upid,
            "node": self.node,
            "pid": self.pid,
            "pstart": self.pstart,
            "starttime": self.starttime,
            "type": self.type,
            "id": self.id,
            "user": self.user,
            "status": self.status,
        }
        if self.status == "stopped":
            data["exitstatus"] = self.exitstatus or "OK"
        return data

    def to_dict(self) -> Dict[str, Any]:
        data = self.as_status()
        data["exitstatus"] = self.exitstatus
        data["endtime"] = self.endtime
        data["lines"] = self.lines[-200:]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        task = cls(
            data["upid"], data.get("node", ""), data.get("type", ""), data.get("id", ""),
            data.get("user", ""), int(data.get("pid", 0)), int(data.get("pstart", 0)), int(data.get("starttime", 0)),
        )
        task.status = data.get("status", "stopped")
        task.exitstatus = data.get("exitstatus")
        task.endtime = data.get("endtime")
        task.lines = list(data.get("lines") or [])
        if task.status == "running":  # the agent restarted while this task ran
            task.status = "stopped"
            task.exitstatus = "interrupted: the OrveX node agent restarted"
            task.lines.append("TASK ERROR: interrupted by node agent restart")
        return task


class TaskManager:
    def __init__(self, node: str, state_dir: str):
        self.node = node
        self.path = os.path.join(state_dir, "tasks.json")
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self._counter = 0
        self._load()

    def _load(self) -> None:
        for data in read_json(self.path, []) or []:
            try:
                task = Task.from_dict(data)
                self._tasks[task.upid] = task
            except (KeyError, TypeError, ValueError):
                continue

    def _persist(self) -> None:
        with self._lock:
            cutoff = time.time() - KEEP_SECONDS
            for upid in [u for u, t in self._tasks.items() if t.endtime and t.endtime < cutoff]:
                del self._tasks[upid]
            snapshot = [t.to_dict() for t in self._tasks.values()]
        try:
            write_json_atomic(self.path, snapshot)
        except OSError as exc:
            LOG.warning("could not persist tasks: %s", exc)

    def start(self, dtype: str, item: Any, user: str, fn: Callable[[Task], Optional[str]]) -> str:
        """Run fn(task) in a background thread and return the UPID immediately."""
        with self._lock:
            self._counter += 1
            pid = (os.getpid() * 1000 + self._counter) & 0xFFFFFFFF
            pstart = int(time.monotonic() * 100) & 0xFFFFFFFF
            starttime = int(time.time())
            upid = "UPID:%s:%08X:%08X:%08X:%s:%s:%s:" % (self.node, pid, pstart, starttime, dtype, item, user)
            task = Task(upid, self.node, dtype, str(item), user, pid, pstart, starttime)
            self._tasks[upid] = task

        def runner() -> None:
            try:
                result = fn(task)
                task.log("TASK OK" if not result else result)
                task.finish("OK")
            except PveError as exc:
                task.log("TASK ERROR: %s" % exc.message)
                task.finish(exc.message)
            except Exception as exc:  # noqa: BLE001 - surfaced to the client
                LOG.error("task %s failed: %s\n%s", upid, exc, traceback.format_exc())
                task.log("TASK ERROR: %s" % exc)
                task.finish(str(exc) or exc.__class__.__name__)
            self._persist()

        thread = threading.Thread(target=runner, name="task-%s-%s" % (dtype, item), daemon=True)
        thread.start()
        self._persist()
        return upid

    def run_sync(self, dtype: str, item: Any, user: str, fn: Callable[[Task], Optional[str]]) -> str:
        """Create an already-finished task (for operations that complete instantly)."""
        upid = self.start(dtype, item, user, fn)
        self.wait(upid, 120)
        return upid

    def get(self, upid: str) -> Task:
        with self._lock:
            task = self._tasks.get(upid)
        if task is None:
            raise PveError(500, "unable to open file - no such task '%s'" % upid)
        return task

    def wait(self, upid: str, timeout: float) -> Task:
        deadline = time.time() + timeout
        task = self.get(upid)
        while task.status == "running" and time.time() < deadline:
            time.sleep(0.05)
        return task

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.starttime, reverse=True)[:limit]
        return [t.as_status() for t in tasks]
