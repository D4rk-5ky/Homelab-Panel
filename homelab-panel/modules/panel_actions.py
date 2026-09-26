#!/usr/bin/env python3
"""Device action execution for Homelab Panel.

This module owns the mechanics for local scripts, Wake-on-LAN retry jobs and
remote MQTT command dispatch.  The Flask application injects its persistence
and status callbacks, keeping action execution reusable without duplicating
panel state/history logic here.
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime


class PanelActionManager:
    """Execute configured local/remote actions while preserving safety guards."""

    def __init__(
        self,
        *,
        remote_devices,
        local_server,
        scripts_dir,
        wol_broadcast,
        run_command,
        mqtt_publish,
        local_script_runner,
        ping_host,
        get_device_button,
        update_panel_job,
        record_device_event,
        set_expected_state,
        device_mqtt_online,
        device_mqtt_offline,
    ):
        self._remote_devices = remote_devices
        self._local_server = local_server
        self._scripts_dir = scripts_dir
        self._wol_broadcast = wol_broadcast
        self._run_command = run_command
        self._mqtt_publish = mqtt_publish
        self._local_script_runner = local_script_runner
        self._ping_host = ping_host
        self._get_device_button = get_device_button
        self._update_panel_job = update_panel_job
        self._record_device_event = record_device_event
        self._set_expected_state = set_expected_state
        self._device_mqtt_online = device_mqtt_online
        self._device_mqtt_offline = device_mqtt_offline
        self._wol_jobs = {}
        self._wol_jobs_lock = threading.Lock()
        self._power_confirm_cancel = {}
        self._power_confirm_lock = threading.Lock()

    def send_wol(self, mac: str) -> tuple[bool, str]:
        """Send one Wake-on-LAN packet using the configured broadcast address."""
        cmd = ["wakeonlan", "-i", self._wol_broadcast(), mac]
        return self._run_command(cmd)

    def run_local_script(self, script_name: str) -> tuple[bool, str]:
        """Run one configured project script after strict path/executable checks."""
        if os.path.basename(script_name) != script_name or script_name in {".", ".."}:
            return False, f"Ugyldigt lokalt scriptnavn: {script_name}"

        scripts_dir = self._scripts_dir()
        script_path = os.path.realpath(os.path.join(scripts_dir, script_name))
        if os.path.dirname(script_path) != os.path.realpath(scripts_dir):
            return False, f"Lokalt script er uden for scripts-mappen: {script_name}"
        if not os.path.isfile(script_path):
            return False, f"Script findes ikke: {script_path}"
        if not os.access(script_path, os.X_OK):
            return False, f"Script er ikke eksekverbart: {script_path}"
        return self._run_command([script_path])

    def execute_local_action(self, command: str) -> tuple[bool, str]:
        """Resolve a local button ID from configuration and run only its script."""
        button = next((b for b in self._local_server().get("buttons", []) if b["id"] == command), None)
        if not button:
            return False, "Ukendt lokal handling."
        ok, message = self._local_script_runner(button["script"])
        if ok:
            return True, f"Kørte lokalt script: {button['script']} -> {message}"
        return False, f"Lokalt script fejlede: {button['script']} -> {message}"

    def wol_job_active(self, device_id: str) -> bool:
        """Return whether a cancellable Wake-on-LAN retry job is active."""
        with self._wol_jobs_lock:
            job = self._wol_jobs.get(device_id)
            return bool(job and not job["cancel"].is_set() and job.get("active"))

    def _finish_wol_job(self, device_id: str, job_id: str, status: str, message: str, severity: str = "info") -> None:
        """Persist the final WoL result and clear its active marker."""
        now = datetime.now().isoformat(timespec="seconds")
        if status == "success":
            self._set_expected_state(device_id, "online", "Wake-on-LAN confirmed")
        elif status in {"failure", "cancelled"}:
            self._set_expected_state(device_id, "unknown", "Wake-on-LAN did not complete")
        self._update_panel_job(device_id, job_id, status=status, updated_at=now, finished_at=now, message=message)
        self._record_device_event(
            device_id,
            category="power",
            event_type="wol_result",
            command="power_on",
            result=status,
            message=message,
            severity=severity,
            job_id=job_id,
            job_status=status,
        )
        with self._wol_jobs_lock:
            current = self._wol_jobs.get(device_id)
            if current and current.get("job_id") == job_id:
                current["active"] = False

    def _wol_worker(self, device_id: str, job_id: str, source: str) -> None:
        """Retry WoL, then confirm ping and optional MQTT availability."""
        device = self._remote_devices()[device_id]
        wol_cfg = device.get("wol", {})
        retry_cfg = wol_cfg.get("retry", {}) or {}
        retry_enabled = bool(retry_cfg.get("enabled", False))
        interval = max(1, int(retry_cfg.get("interval_seconds", 15)))
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 20))) if retry_enabled else 1
        wait_for_mqtt = max(0, int(retry_cfg.get("wait_for_mqtt_seconds", 120)))
        mac = str(wol_cfg.get("mac", "")).strip()
        ip = str(wol_cfg.get("ip", "")).strip()

        with self._wol_jobs_lock:
            cancel_event = self._wol_jobs[device_id]["cancel"]

        started_epoch = time.time()
        now = datetime.now().isoformat(timespec="seconds")
        self._update_panel_job(
            device_id, job_id, command="power_on", label=str(wol_cfg.get("label") or "Wake-on-LAN"),
            category="power", source=source, status="running", queued_at=now, started_at=now,
            updated_at=now, message="Wake-on-LAN started", runtime_seconds=0.0,
        )
        self._set_expected_state(device_id, "starting", "Wake-on-LAN requested")

        ping_seen = False
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            if cancel_event.is_set():
                self._finish_wol_job(device_id, job_id, "cancelled", "Wake-on-LAN retry cancelled by user")
                return

            ok, message = self.send_wol(mac)
            last_error = "" if ok else message
            self._record_device_event(
                device_id, category="power", event_type="wol_attempt", command="power_on",
                result="sent" if ok else "failure", message=f"WoL attempt {attempt}/{max_attempts}: {message}",
                source=source, severity="info" if ok else "error", job_id=job_id,
                job_status="running", attempt=attempt,
            )
            self._update_panel_job(
                device_id, job_id, status="waiting", updated_at=datetime.now().isoformat(timespec="seconds"),
                message=f"WoL attempt {attempt}/{max_attempts} sent; waiting for ping", attempts=attempt,
                runtime_seconds=round(time.time() - started_epoch, 1),
            )

            deadline = time.time() + interval
            while time.time() < deadline:
                if cancel_event.is_set():
                    self._finish_wol_job(device_id, job_id, "cancelled", "Wake-on-LAN retry cancelled by user")
                    return
                if ip and self._ping_host(ip):
                    ping_seen = True
                    break
                time.sleep(1)
            if ping_seen:
                break

        if not ping_seen:
            message = f"Wake-on-LAN did not produce a ping response after {max_attempts} attempt(s)"
            if last_error:
                message += f"; last send error: {last_error}"
            self._finish_wol_job(device_id, job_id, "failure", message, "error")
            return

        self._record_device_event(
            device_id, category="availability", event_type="wol_ping_confirmed", command="power_on",
            result="running", message="Ping response confirmed after Wake-on-LAN", source=source,
            job_id=job_id, job_status="confirming",
        )

        status_cfg = device.get("status", {})
        if not str(status_cfg.get("power_topic", "")).strip():
            self._finish_wol_job(device_id, job_id, "success", "Ping confirmed; MQTT power status is not configured")
            return

        self._update_panel_job(
            device_id, job_id, status="confirming", updated_at=datetime.now().isoformat(timespec="seconds"),
            message="Ping confirmed; waiting for MQTT online",
        )
        deadline = time.time() + wait_for_mqtt
        while time.time() <= deadline:
            if cancel_event.is_set():
                self._finish_wol_job(device_id, job_id, "cancelled", "Wake-on-LAN confirmation cancelled by user")
                return
            if self._device_mqtt_online(device):
                self._finish_wol_job(device_id, job_id, "success", "Device online confirmed by both ping and MQTT")
                return
            time.sleep(1)

        self._finish_wol_job(device_id, job_id, "failure", "Ping is online, but MQTT did not confirm online before the timeout", "error")

    def start_wol_job(self, device_id: str, source: str) -> tuple[bool, str]:
        """Validate and start one asynchronous Wake-on-LAN retry job."""
        device = self._remote_devices().get(device_id)
        if not device:
            return False, f"Ukendt remote enhed: {device_id}"
        wol_cfg = device.get("wol", {})
        if not wol_cfg.get("enabled"):
            return False, f"Wake-on-LAN er ikke aktiveret for {device['title']}"
        if not str(wol_cfg.get("mac", "")).strip():
            return False, f"Wake-on-LAN MAC mangler for {device['title']}"
        if self.wol_job_active(device_id):
            return False, f"Wake-on-LAN kører allerede for {device['title']}"

        job_id = f"wol-{uuid.uuid4().hex[:10]}"
        cancel_event = threading.Event()
        with self._wol_jobs_lock:
            self._wol_jobs[device_id] = {"job_id": job_id, "cancel": cancel_event, "active": True}
        threading.Thread(target=self._wol_worker, args=(device_id, job_id, source), daemon=True).start()
        return True, f"Wake-on-LAN job startet for {device['title']} (job {job_id})"

    def cancel_wol_job(self, device_id: str, source: str) -> tuple[bool, str]:
        """Signal cancellation for an active WoL retry job."""
        with self._wol_jobs_lock:
            job = self._wol_jobs.get(device_id)
            if not job or not job.get("active"):
                return False, "Der er ingen aktiv Wake-on-LAN retry at annullere"
            job["cancel"].set()
            job["active"] = False
            job_id = str(job.get("job_id", ""))
        self._record_device_event(
            device_id, category="power", event_type="wol_cancel_requested", command="cancel_wol",
            result="sent", message="Wake-on-LAN cancel requested", source=source, job_id=job_id,
        )
        return True, "Wake-on-LAN retry annulleres"

    def cancel_power_confirmation(self, device_id: str) -> None:
        """Cancel an outstanding shutdown/reboot confirmation worker."""
        with self._power_confirm_lock:
            event = self._power_confirm_cancel.get(device_id)
            if event:
                event.set()

    def power_confirmation_worker(self, device_id: str, command: str, job_id: str, confirmation: str) -> None:
        """Confirm shutdown/reboot using both ping and MQTT state transitions."""
        device = self._remote_devices()[device_id]
        confirm_cfg = device.get("confirmation", {}) or {}
        timeout = max(10, int(confirm_cfg.get("shutdown_timeout_seconds", 180) if confirmation == "shutdown" else confirm_cfg.get("reboot_timeout_seconds", 300)))

        cancel_event = threading.Event()
        with self._power_confirm_lock:
            previous = self._power_confirm_cancel.get(device_id)
            if previous:
                previous.set()
            self._power_confirm_cancel[device_id] = cancel_event

        now = datetime.now().isoformat(timespec="seconds")
        self._update_panel_job(device_id, job_id, status="confirming", updated_at=now, message=f"Waiting to confirm {confirmation}")
        ip = str(device.get("wol", {}).get("ip", "")).strip()
        deadline = time.time() + timeout
        saw_offline = False

        while time.time() <= deadline and not cancel_event.is_set():
            ping_ok = self._ping_host(ip) if ip else False
            mqtt_offline = self._device_mqtt_offline(device)
            mqtt_online = self._device_mqtt_online(device)

            if not ping_ok and mqtt_offline:
                if confirmation == "shutdown":
                    self._set_expected_state(device_id, "offline", "Shutdown confirmed")
                    finished = datetime.now().isoformat(timespec="seconds")
                    self._update_panel_job(device_id, job_id, status="success", finished_at=finished, updated_at=finished, message="Shutdown confirmed: ping offline and MQTT offline")
                    self._record_device_event(
                        device_id, category="power", event_type="shutdown_confirmed", command=command,
                        result="success", message="Shutdown confirmed by both ping offline and MQTT offline",
                        job_id=job_id, job_status="success",
                    )
                    return
                saw_offline = True
                self._set_expected_state(device_id, "restarting", "Reboot offline phase confirmed")

            if confirmation == "reboot" and saw_offline and ping_ok and mqtt_online:
                self._set_expected_state(device_id, "online", "Reboot confirmed")
                finished = datetime.now().isoformat(timespec="seconds")
                self._update_panel_job(device_id, job_id, status="success", finished_at=finished, updated_at=finished, message="Reboot confirmed: device went offline and returned with ping + MQTT")
                self._record_device_event(
                    device_id, category="power", event_type="reboot_confirmed", command=command,
                    result="success", message="Reboot confirmed: offline transition followed by ping + MQTT online",
                    job_id=job_id, job_status="success",
                )
                return
            time.sleep(2)

        if cancel_event.is_set():
            return
        finished = datetime.now().isoformat(timespec="seconds")
        self._update_panel_job(device_id, job_id, status="failure", finished_at=finished, updated_at=finished, message=f"Timed out waiting to confirm {confirmation}")
        self._record_device_event(
            device_id, category="power", event_type=f"{confirmation}_confirmation_timeout", command=command,
            result="failure", message=f"Timed out waiting for {confirmation} confirmation", severity="error",
            job_id=job_id, job_status="failure",
        )

    def execute_remote_action(self, device_id: str, command: str, job_id: str = "", source: str = "Homelab Panel") -> tuple[bool, str]:
        """Resolve one configured remote action and publish only its allow-listed payload."""
        device = self._remote_devices().get(device_id)
        if not device:
            return False, f"Ukendt remote enhed: {device_id}"
        if command == "power_on":
            return self.start_wol_job(device_id, source)
        if command == "cancel_wol":
            return self.cancel_wol_job(device_id, source)

        resolved_command = {"shutdown": "shutdown_delay", "reboot": "reboot_delay"}.get(command, command)
        mqtt_cfg = device.get("mqtt_controls")
        if not mqtt_cfg:
            return False, f"Der er ingen MQTT-kontrol for {device['title']}"
        button = self._get_device_button(device, resolved_command)
        if not button:
            return False, f"Ukendt handling '{command}' for {device['title']}"
        topic = str(mqtt_cfg.get("topic", "")).strip()
        payload = str(button.get("payload", "")).strip()
        if not topic or not payload:
            return False, f"Ufuldstændig MQTT-konfiguration for handling '{command}'"

        if bool(mqtt_cfg.get("json_jobs", False)):
            wire_payload = json.dumps({"command": payload, "job_id": job_id, "source": source}, ensure_ascii=False, separators=(",", ":"))
        else:
            wire_payload = payload
        ok, message = self._mqtt_publish(topic, wire_payload)
        if ok:
            return True, f"MQTT command '{payload}' sendt til '{topic}'"
        return False, message
