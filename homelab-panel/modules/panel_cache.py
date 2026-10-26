"""Bounded, process-local caches for shared data; never store web sessions."""
import copy
from collections import OrderedDict
import json
import os
import threading


class PanelJsonCache:
    """Parse each state-file version once and notice atomic/external replacements."""

    def __init__(self, *, enabled=True, max_files=3, max_bytes=2097152):
        """Bound retained JSON by file count and total on-disk source bytes."""
        if type(enabled) is not bool:
            raise ValueError("STATE_CACHE_CONFIG.enabled must be True or False")
        for key, value in (("max_files", max_files), ("max_bytes", max_bytes)):
            if type(value) is not int or value < 1:
                raise ValueError(f"STATE_CACHE_CONFIG.{key} must be a positive integer")
        self.enabled = enabled
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._files = OrderedDict()
        self._source_bytes = 0

    @staticmethod
    def _signature(stat):
        """Identify the actual opened file, including replacements and in-place edits."""
        return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    @staticmethod
    def version(path):
        """Check one file identity without loading/copying its cached contents."""
        try:
            stat = os.stat(path)
            return PanelJsonCache._signature(stat)
        except OSError:
            return None

    def _forget(self, path):
        """Release one cached source and keep eviction accounting exact under lock."""
        cached = self._files.pop(path, None)
        if cached is not None:
            self._source_bytes -= cached[2]

    def load(self, path, default):
        """Return isolated data; evict LRU entries, bypass oversized/unstable sources."""
        with self._lock:
            try:
                version = self.version(path)
                if version is None:
                    raise FileNotFoundError(path)
                cached = self._files.get(path)
                if self.enabled and cached is not None and cached[0] == version:
                    self._files.move_to_end(path)
                    return copy.deepcopy(cached[1])
                self._forget(path)
                with open(path, "r", encoding="utf-8") as stream:
                    before = self._signature(os.fstat(stream.fileno()))
                    data = json.load(stream)
                    after = self._signature(os.fstat(stream.fileno()))
                size = after[-1]
                if not self.enabled or size > self.max_bytes or before != after:
                    # This object isn't shared, so it needs no extra deep copy.
                    return data
                while self._files and (len(self._files) >= self.max_files
                                       or self._source_bytes + size > self.max_bytes):
                    self._forget(next(iter(self._files)))
                self._files[path] = (after, data, size)
                self._source_bytes += size
                return copy.deepcopy(data)
            except (OSError, ValueError, TypeError):
                self._forget(path)
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
