"""Bounded prepared state, escaped cards and lazy job rows shared across browsers."""
import copy
import threading
import time
import uuid


class PanelDashboardCache:
    def __init__(self, render, page_size=5):
        self._render = render
        self.page_size = page_size
        self._lock = threading.Lock()
        self._prepare_lock = threading.Lock()
        self._prepared = None
        self._statuses = None
        self._instance = uuid.uuid4().hex
        self._revision = 0
        self._cards = {}

    def prepare(self, key, build):
        """Build once per source generation or server deadline, never per browser."""
        with self._prepare_lock:
            # Sample under lock: overlapping requests are not backwards clock steps.
            now = time.time()
            cached = self._prepared
            if (cached is None or cached[0] != key or now < cached[1]
                    or now >= cached[2]):
                statuses, deadline = build(now)
                self._prepared = (copy.deepcopy(key), now, deadline, statuses)
            # Private to the app/renderers; consumers must not mutate this shared view.
            return self._prepared[3]

    def _sync(self, devices, statuses):
        """Invalidate only changed card sources; keep at most one row cache per device."""
        if self._statuses is statuses:
            return
        self._cards = {key: value for key, value in self._cards.items() if key in devices}
        for device_id, device in devices.items():
            status = statuses[device_id]
            status_view = {key: value for key, value in status.items()
                           if key not in {"jobs", "active_jobs", "latest_job"}}
            status_view["active_job_count"] = len(status["active_jobs"])
            cards = self._cards.setdefault(device_id, {})
            for kind, view in (("status", status_view), ("jobs", status["jobs"])):
                source = (device, view)
                cached = cards.get(kind)
                if cached is None or cached["source"] != source:
                    self._revision += 1
                    cached = {"source": (copy.deepcopy(device), view), "revision": self._revision}
                    if kind == "status":
                        cached["html"] = self._render("_device_status.html", device_id=device_id,
                                                      device=device, st=status_view)
                    else:
                        cached["rows"] = [None] * len(view)
                        cached["empty"] = None
                    cards[kind] = cached
        self._statuses = statuses

    def _job_window(self, device_id, limit):
        """Render only requested rows, reusing them across all requested window sizes."""
        cached = self._cards[device_id]["jobs"]
        jobs = cached["source"][1]
        if not jobs:
            if cached["empty"] is None:
                cached["empty"] = self._render("_device_jobs.html", jobs=[])
            html = cached["empty"]
        else:
            for index in range(min(limit, len(jobs))):
                if cached["rows"][index] is None:
                    cached["rows"][index] = self._render("_device_jobs.html", jobs=[jobs[index]])
            html = "".join(cached["rows"][:limit])
        if len(jobs) > limit:
            # Keep a scroll target below the first batch, even when five rows fit exactly.
            html += '<li class="muted" data-jobs-sentinel>Scroll ned for flere jobs.</li>'
        return {"jobs": html, "jobs_total": len(jobs), "jobs_limit": limit}

    def snapshot(self, devices, statuses, *, since=None, instance=None, job_limits=None):
        """Return shared initial/reset cards or per-browser revision deltas."""
        with self._lock:
            self._sync(devices, statuses)
            updates = {}
            reset = instance != self._instance or since is None or since > self._revision
            for device_id, cards in self._cards.items():
                for kind in ("status", "jobs"):
                    if reset or cards[kind]["revision"] > since:
                        fields = updates.setdefault(device_id, {})
                        if kind == "status":
                            fields["status"] = cards[kind]["html"]
                        else:
                            limit = (job_limits or {}).get(device_id, self.page_size)
                            fields.update(self._job_window(device_id, limit))
            return {"instance": self._instance, "revision": self._revision, "devices": updates}

    def job_window(self, devices, statuses, device_id, limit):
        """Expand one browser's prefix without retaining browser-specific cache entries."""
        with self._lock:
            self._sync(devices, statuses)
            return {"instance": self._instance, "revision": self._revision,
                    "devices": {device_id: self._job_window(device_id, limit)}}
