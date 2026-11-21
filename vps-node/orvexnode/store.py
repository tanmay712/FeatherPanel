"""Small persistent key/value state of the agent (JSON file, thread safe)."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

from .util import read_json, write_json_atomic


class Store:
    """Holds data that must survive restarts but does not belong in Incus:

    * pending credentials registered by the panel before an instance exists
    * snapshot descriptions
    * temporary console users created through /access/users
    """

    def __init__(self, state_dir: str):
        self.path = os.path.join(state_dir, "state.json")
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = read_json(self.path, {}) or {}
        for key in ("pending_credentials", "snapshot_notes", "users"):
            self._data.setdefault(key, {})

    def _save(self) -> None:
        write_json_atomic(self.path, self._data)

    # ------------------------------------------------ pending credentials
    def put_pending_credentials(self, vmid: int, username: str, password_hash: str) -> None:
        with self._lock:
            self._data["pending_credentials"][str(vmid)] = {
                "username": username,
                "password_hash": password_hash,
                "expires": int(time.time()) + 24 * 3600,
            }
            self._save()

    def pop_pending_credentials(self, vmid: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            pending = self._data["pending_credentials"]
            now = int(time.time())
            for key in [k for k, v in pending.items() if int(v.get("expires", 0)) < now]:
                del pending[key]
            entry = pending.pop(str(vmid), None)
            self._save()
            return entry

    # --------------------------------------------------- snapshot notes
    def set_snapshot_note(self, vmid: int, snap: str, description: str, vmstate: bool = False) -> None:
        with self._lock:
            notes = self._data["snapshot_notes"].setdefault(str(vmid), {})
            notes[snap] = {"description": description, "vmstate": 1 if vmstate else 0}
            self._save()

    def snapshot_note(self, vmid: int, snap: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data["snapshot_notes"].get(str(vmid), {}).get(snap, {}))

    def drop_snapshot_note(self, vmid: int, snap: Optional[str] = None) -> None:
        with self._lock:
            if snap is None:
                self._data["snapshot_notes"].pop(str(vmid), None)
            else:
                self._data["snapshot_notes"].get(str(vmid), {}).pop(snap, None)
            self._save()

    # ------------------------------------------------------------- users
    def users(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data["users"])

    def put_user(self, userid: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._data["users"][userid] = data
            self._save()

    def delete_user(self, userid: str) -> bool:
        with self._lock:
            existed = self._data["users"].pop(userid, None) is not None
            self._save()
            return existed
