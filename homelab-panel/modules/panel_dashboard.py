"""Cache only shared card fragments and send per-browser revision deltas."""
import copy
import threading
import uuid


class PanelDashboardCache:
    def __init__(self, render):
        self._render = render
        self._lock = threading.Lock()
        self._instance = uuid.uuid4().hex
        self._revision = 0
        self._cards = {}

    def snapshot(self, devices, statuses, *, since=None, instance=None):
        """Rebuild changed fragments; username, flashes and cookies never enter here."""
        with self._lock:
            updates = {}
            reset = instance != self._instance or since is None or since > self._revision
            for device_id, device in devices.items():
                status = statuses[device_id]
                status_view = {key: value for key, value in status.items()
                               if key not in {"jobs", "active_jobs", "latest_job"}}
                status_view["active_job_count"] = len(status["active_jobs"])
                views = {"status": status_view, "jobs": status["jobs"]}
                cards = self._cards.setdefault(device_id, {})
                for kind, view in views.items():
                    # Device configuration is shared and may change after a restart.
                    source = (device, view)
                    cached = cards.get(kind)
                    if cached is None or cached["source"] != source:
                        html = self._render(f"_device_{kind}.html", device_id=device_id,
                                            device=device, st=status_view, jobs=status["jobs"])
                        self._revision += 1
                        cached = {"source": copy.deepcopy(source), "html": html,
                                  "revision": self._revision}
                        cards[kind] = cached
                    if reset or cached["revision"] > since:
                        updates.setdefault(device_id, {})[kind] = cached["html"]
            return {"instance": self._instance, "revision": self._revision, "devices": updates}
