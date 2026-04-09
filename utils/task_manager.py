# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import os
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class TaskInfo:
    task_id: str
    task_type: str
    status: str  # queued|running|completed|failed|stopped|stopping
    progress: float  # 0..1
    message: str
    started_at: float
    finished_at: Optional[float] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    # 邮件配置
    email_to: Optional[str] = None
    email_config: Optional[dict] = None
    # 实时状态（power_cycle 等任务用于更新 UI）
    current_cycle: Optional[int] = None
    current_status: Optional[str] = None  # "ON" | "OFF" | None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskManager:
    def __init__(
        self,
        emit_log: Callable[[str, str], None],
        emit_progress: Callable[[str, float, str], None],
        emit_test_completed: Callable[[str, str, str], None] = None,
        emit_temp_data: Callable[[dict], None] = None,
        notification_service=None,
    ) -> None:
        self._emit_log = emit_log
        self._emit_progress = emit_progress
        self._emit_test_completed = emit_test_completed
        self._emit_temp_data = emit_temp_data
        self._notification_service = notification_service
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskInfo] = {}
        self._stop_flags: Dict[str, threading.Event] = {}
        self.logger = logging.getLogger("task_manager")

    def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {tid: info.to_dict() for tid, info in self._tasks.items()}

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        with self._lock:
            return self._tasks.get(task_id)

    def stop_task(self, task_id: str) -> bool:
        with self._lock:
            ev = self._stop_flags.get(task_id)
            info = self._tasks.get(task_id)
            if not ev or not info:
                return False
            if info.status not in ("queued", "running"):
                return False
            ev.set()
            info.status = "stopping"
            info.message = "Stopping..."
            return True

    def _new_task(self, task_type: str, message: str) -> TaskInfo:
        task_id = uuid.uuid4().hex[:12]
        info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status="queued",
            progress=0.0,
            message=message,
            started_at=time.time(),
        )
        with self._lock:
            self._tasks[task_id] = info
            self._stop_flags[task_id] = threading.Event()
        return info

    def start_voltage_scan(self, payload: Dict[str, Any]) -> TaskInfo:
        info = self._new_task("voltage_scan", "Queued")

        def runner() -> None:
            from services.voltage_scan import run_voltage_scan

            self.logger.info(f"[TASK {info.task_id}] runner started with payload: {payload}")
            self._emit_log(info.task_type, f"[TASK {info.task_id}] started")
            with self._lock:
                info.status = "running"
                info.message = "Running"

            stop_event = self._stop_flags[info.task_id]

            def emit(msg: str) -> None:
                self._emit_log(info.task_type, msg)

            def progress(p: float, msg: str) -> None:
                with self._lock:
                    info.progress = max(0.0, min(1.0, float(p)))
                    info.message = msg
                self._emit_progress(info.task_type, info.progress, msg)

            try:
                result_path = run_voltage_scan(payload, emit=emit, set_progress=progress, stop_event=stop_event)
                with self._lock:
                    if stop_event.is_set():
                        info.status = "stopped"
                        info.message = "Stopped"
                    else:
                        info.status = "completed"
                        info.message = "Completed"
                        info.result_path = result_path
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] done")
                self._emit_progress(info.task_type, info.progress, info.message)
                self._emit_log(info.task_type, f"[INFO] 结果已保存: {result_path}")
                if self._emit_test_completed:
                    try:
                        self._emit_test_completed(info.task_type, info.task_id, result_path)
                    except Exception as e:
                        self.logger.error(f"Emit test_completed failed: {e}")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, result_path)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")
            except Exception as e:  # noqa: BLE001
                error_trace = traceback.format_exc()
                self.logger.error(f"[TASK {info.task_id}] Exception in voltage_scan:\n{error_trace}")
                with self._lock:
                    info.status = "failed"
                    info.error = str(e)
                    info.message = "Failed"
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] failed: {e}")
                self._emit_log(info.task_type, f"[ERROR DETAILS]: {error_trace}")
                self._emit_progress(info.task_type, info.progress, "Failed")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, None)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")

        t = threading.Thread(target=runner, name=f"task-{info.task_id}", daemon=True)
        t.start()
        return info

    def start_voltage_set(self, payload: Dict[str, Any]) -> TaskInfo:
        info = self._new_task("voltage_set", "Queued")

        def runner() -> None:
            from services.voltage_set import run_voltage_set

            self.logger.info(f"[TASK {info.task_id}] voltage_set runner started with payload: {payload}")
            self._emit_log(info.task_type, f"[TASK {info.task_id}] started")
            with self._lock:
                info.status = "running"
                info.message = "Running"

            stop_event = self._stop_flags[info.task_id]

            def emit(msg: str) -> None:
                self._emit_log(info.task_type, msg)

            def progress(p: float, msg: str) -> None:
                with self._lock:
                    info.progress = max(0.0, min(1.0, float(p)))
                    info.message = msg
                self._emit_progress(info.task_type, info.progress, msg)

            try:
                result_path = run_voltage_set(payload, emit=emit, set_progress=progress, stop_event=stop_event)
                with self._lock:
                    if stop_event.is_set():
                        info.status = "stopped"
                        info.message = "Stopped"
                    else:
                        info.status = "completed"
                        info.message = "Completed"
                        info.result_path = result_path
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] done")
                self._emit_progress(info.task_type, info.progress, info.message)
                self._emit_log(info.task_type, f"[INFO] 结果已保存: {result_path}")
                if self._emit_test_completed:
                    try:
                        self._emit_test_completed(info.task_type, info.task_id, result_path)
                    except Exception as e:
                        self.logger.error(f"Emit test_completed failed: {e}")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, result_path)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")
            except Exception as e:  # noqa: BLE001
                error_trace = traceback.format_exc()
                self.logger.error(f"[TASK {info.task_id}] Exception in voltage_set:\n{error_trace}")
                with self._lock:
                    info.status = "failed"
                    info.error = str(e)
                    info.message = "Failed"
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] failed: {e}")
                self._emit_log(info.task_type, f"[ERROR DETAILS]: {error_trace}")
                self._emit_progress(info.task_type, info.progress, "Failed")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, None)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")

        t = threading.Thread(target=runner, name=f"task-{info.task_id}", daemon=True)
        t.start()
        return info

    def start_power_cycle(self, payload: Dict[str, Any]) -> TaskInfo:
        info = self._new_task("power_cycle", "Queued")

        def runner() -> None:
            from services.power_cycle import run_power_cycle

            self.logger.info(f"[TASK {info.task_id}] power_cycle runner started with payload: {payload}")
            self._emit_log(info.task_type, f"[TASK {info.task_id}] started")
            with self._lock:
                info.status = "running"
                info.message = "Running"

            stop_event = self._stop_flags[info.task_id]

            def emit(msg: str) -> None:
                self._emit_log(info.task_type, msg)

            def progress(p: float, msg: str) -> None:
                import re
                with self._lock:
                    info.progress = max(0.0, min(1.0, float(p)))
                    info.message = msg
                    # 从消息中解析 cycle 和 ON/OFF 状态
                    m = re.search(r"Cycle (\d+)/(\d+).*?(ON|OFF)", msg)
                    if m:
                        info.current_cycle = int(m.group(1))
                        info.current_status = m.group(3)
                self._emit_progress(info.task_type, info.progress, msg)

            try:
                result_path = run_power_cycle(payload, emit=emit, set_progress=progress, stop_event=stop_event)
                with self._lock:
                    if stop_event.is_set():
                        info.status = "stopped"
                        info.message = "Stopped"
                    else:
                        info.status = "completed"
                        info.message = "Completed"
                        info.result_path = result_path
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] done")
                self._emit_progress(info.task_type, info.progress, info.message)
                self._emit_log(info.task_type, f"[INFO] 结果已保存: {result_path}")
                if self._emit_test_completed:
                    try:
                        self._emit_test_completed(info.task_type, info.task_id, result_path)
                    except Exception as e:
                        self.logger.error(f"Emit test_completed failed: {e}")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, result_path)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")
            except Exception as e:  # noqa: BLE001
                error_trace = traceback.format_exc()
                self.logger.error(f"[TASK {info.task_id}] Exception in power_cycle:\n{error_trace}")
                with self._lock:
                    info.status = "failed"
                    info.error = str(e)
                    info.message = "Failed"
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] failed: {e}")
                self._emit_log(info.task_type, f"[ERROR DETAILS]: {error_trace}")
                self._emit_progress(info.task_type, info.progress, "Failed")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, None)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")

        t = threading.Thread(target=runner, name=f"task-{info.task_id}", daemon=True)
        t.start()
        return info

    def start_temp_scan(self, payload: Dict[str, Any]) -> TaskInfo:
        info = self._new_task("temp_scan", "Queued")

        def runner() -> None:
            from services.temp_scan import run_temp_scan

            self.logger.info(f"[TASK {info.task_id}] temp_scan runner started with payload: {payload}")
            self._emit_log(info.task_type, f"[TASK {info.task_id}] started")
            with self._lock:
                info.status = "running"
                info.message = "Running"

            stop_event = self._stop_flags[info.task_id]

            def emit(msg: str) -> None:
                self._emit_log(info.task_type, msg)

            def progress(p: float, msg: str) -> None:
                with self._lock:
                    info.progress = max(0.0, min(1.0, float(p)))
                    info.message = msg
                self._emit_progress(info.task_type, info.progress, msg)

            def emit_data(data: Dict[str, Any]) -> None:
                if self._emit_temp_data:
                    self._emit_temp_data(data)

            try:
                result_path, found_nads = run_temp_scan(payload, emit=emit, set_progress=progress, emit_data=emit_data, stop_event=stop_event)
                with self._lock:
                    if stop_event.is_set():
                        info.status = "stopped"
                        info.message = "Stopped"
                    else:
                        info.status = "completed"
                        info.message = "Completed"
                        info.result_path = result_path
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] done")
                self._emit_progress(info.task_type, info.progress, info.message)
                self._emit_log(info.task_type, f"[INFO] 结果已保存: {result_path}")
                if self._emit_test_completed:
                    try:
                        self._emit_test_completed(info.task_type, info.task_id, result_path)
                    except Exception as e:
                        self.logger.error(f"Emit test_completed failed: {e}")
                if self._notification_service:
                    try:
                        self._notification_service.notify(
                            info.task_type, info.status, result_path,
                            extra={"nad_list": found_nads}
                        )
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")
            except Exception as e:  # noqa: BLE001
                error_trace = traceback.format_exc()
                self.logger.error(f"[TASK {info.task_id}] Exception in temp_scan:\n{error_trace}")
                with self._lock:
                    info.status = "failed"
                    info.error = str(e)
                    info.message = "Failed"
                    info.finished_at = time.time()
                self._emit_log(info.task_type, f"[TASK {info.task_id}] failed: {e}")
                self._emit_log(info.task_type, f"[ERROR DETAILS]: {error_trace}")
                self._emit_progress(info.task_type, info.progress, "Failed")
                if self._notification_service:
                    try:
                        self._notification_service.notify(info.task_type, info.status, None)
                    except Exception as e:
                        self.logger.error(f"[TASK {info.task_id}] notify failed: {e}")

        t = threading.Thread(target=runner, name=f"task-{info.task_id}", daemon=True)
        t.start()
        return info


