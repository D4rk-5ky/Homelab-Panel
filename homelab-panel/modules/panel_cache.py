"""Bounded, process-local caches for shared data; never store web sessions."""
import copy
import json
import os
import threading


class PanelJsonCache:
    """Parse each state-file version once and notice atomic/external replacements."""

    def __init__(self):
        self._lock = threading.Lock()
        self._files = {}

    @staticmethod
    def version(path):
        """Check one file identity without loading/copying its cached contents."""
        try:
            stat = os.stat(path)
            return (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        except OSError:
            return None

    def load(self, path, default):
        with self._lock:
            try:
                version = self.version(path)
                if version is None:
                    raise FileNotFoundError(path)
                cached = self._files.get(path)
                if cached is None or cached[0] != version:
                    with open(path, "r", encoding="utf-8") as stream:
                        data = json.load(stream)
                    self._files[path] = (version, data)
                return copy.deepcopy(self._files[path][1])
            except (OSError, ValueError, TypeError):
                self._files.pop(path, None)
                return copy.deepcopy(default)


class PanelJobsCache:
    """Merge, decode and sort shared job sources only when their content changes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._devices = {}

    def merge(self, device_id, panel_jobs, remote_payload, limit):
        with self._lock:
            sources = (panel_jobs, remote_payload, limit)
            cached = self._devices.get(device_id)
            if cached is None or cached[0] != sources:
                jobs = copy.deepcopy(panel_jobs)
                try:
                    remote_jobs = json.loads(remote_payload) if remote_payload else []
                except (ValueError, TypeError):
                    remote_jobs = []
                if isinstance(remote_jobs, list):
                    known = {(str(j.get("job_id")), str(j.get("updated_at"))) for j in jobs}
                    for job in remote_jobs:
                        if not isinstance(job, dict):
                            continue
                        key = (str(job.get("job_id")), str(job.get("updated_at")))
                        if key not in known:
                            jobs.append({**job, "origin": "Homelab Control"})
                jobs.sort(key=lambda j: str(j.get("updated_at") or j.get("queued_at") or ""), reverse=True)
                self._devices[device_id] = (copy.deepcopy(sources), jobs[:limit])
            return copy.deepcopy(self._devices[device_id][1])
