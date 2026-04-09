# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict

logger = logging.getLogger("power_cycle")


def run_power_cycle(
    payload: Dict[str, Any],
    *,
    emit: Callable[[str], None],
    set_progress: Callable[[float, str], None],
    stop_event,
) -> str:
    """
    Power cycle test - repeatedly turn power on/off to test device reliability.
    Used to verify that BIN settings and functionality remain unchanged after power cycles.
    """
    logger.info(f"===== run_power_cycle 开始执行 =====")
    logger.info(f"payload = {payload}")

    cycle_count = int(payload.get("cycle_count", 10))
    voltage = float(payload.get("voltage", 12))
    on_time_s = float(payload.get("on_time_s", 2))
    off_time_s = float(payload.get("off_time_s", 1))
    power_address = str(payload.get("power_address", ""))

    emit(f"[DEBUG] ====== 上下电耐受测试参数 ======")
    emit(f"[DEBUG] cycle_count = {cycle_count}")
    emit(f"[DEBUG] voltage = {voltage}V")
    emit(f"[DEBUG] on_time_s = {on_time_s}s")
    emit(f"[DEBUG] off_time_s = {off_time_s}s")
    emit(f"[DEBUG] power_address = '{power_address}'")
    emit(f"[DEBUG] ==========================")

    os.makedirs("test_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = os.path.join("test_results", f"power_cycle_{ts}.csv")

    set_progress(0.0, "Preparing")

    if not power_address:
        emit(f"[ERROR] power_address 为空！")
        raise ValueError("power_address is required for power cycle test")

    try:
        emit(f"[power_cycle] connecting power: {power_address}")
        from IT6322A_USB import drivers as PowerDriver
    except Exception as e:
        emit(f"[ERROR] 导入电源驱动失败: {e}")
        raise

    power = None

    try:
        power = PowerDriver(power_address)
        power.Enter_Remote()
        power.Set_OutputVolt_CH1(voltage)
        emit(f"[INFO] 电源已连接，电压设置为 {voltage}V")
    except Exception as e:
        emit(f"[ERROR] 连接电源失败: {e}")
        raise

    total_cycles = cycle_count
    total_steps = total_cycles * 2  # ON + OFF per cycle
    current_step = 0

    try:
        with open(result_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "seq",
                "time",
                "cycle_number",
                "action",
                "voltage",
                "measured_voltage",
                "status",
            ])

            seq = 0
            emit(f"[INFO] 开始循环上下电测试: {total_cycles}次, {voltage}V, 开{on_time_s}s/关{off_time_s}s")

            for cycle in range(1, total_cycles + 1):
                if stop_event.is_set():
                    emit("[power_cycle] stop requested")
                    break

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                seq += 1
                current_step += 1

                # Power ON
                try:
                    emit(f"[→] Cycle {cycle}/{total_cycles} - Power ON")
                    power.TunrOn_Output()
                    time.sleep(on_time_s)
                    measured = power.Get_MeasuredVolt_CH1()
                    w.writerow([seq, now, cycle, "ON", voltage, measured, "OK"])
                    f.flush()
                    emit(f"[OK] ON done, measured={measured:.2f}V")
                except Exception as e:
                    logger.exception(f"[power_cycle] Power ON error cycle={cycle}: {e}")
                    w.writerow([seq, now, cycle, "ON", voltage, 0, f"ERROR: {e}"])
                    f.flush()
                    emit(f"[ERROR] ON failed: {e}")

                p = current_step / total_steps
                set_progress(p, f"Cycle {cycle}/{total_cycles} ON ({current_step}/{total_steps})")

                if stop_event.is_set():
                    emit("[power_cycle] stop requested")
                    break

                # Power OFF
                seq += 1
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_step += 1
                try:
                    emit(f"[→] Cycle {cycle}/{total_cycles} - Power OFF")
                    power.TurnOff_Output()
                    time.sleep(off_time_s)
                    measured = power.Get_MeasuredVolt_CH1()
                    w.writerow([seq, now, cycle, "OFF", voltage, measured, "OK"])
                    f.flush()
                    emit(f"[OK] OFF done, measured={measured:.2f}V")
                except Exception as e:
                    logger.exception(f"[power_cycle] Power OFF error cycle={cycle}: {e}")
                    w.writerow([seq, now, cycle, "OFF", voltage, 0, f"ERROR: {e}"])
                    f.flush()
                    emit(f"[ERROR] OFF failed: {e}")

                p = current_step / total_steps
                set_progress(p, f"Cycle {cycle}/{total_cycles} OFF ({current_step}/{total_steps})")

            if not stop_event.is_set():
                emit(f"[INFO] 测试完成，共完成 {(current_step // 2)} 次完整上下电")

            # Final power ON state
            try:
                power.TunrOn_Output()
                emit(f"[INFO] 电源已开启")
            except Exception as e:
                emit(f"[WARN] 最终开启电源失败: {e}")

        emit(f"[DEBUG] 循环结束, 共完成 {cycle - 1} 次完整上下电")

    finally:
        if power:
            try:
                power.close()
            except Exception:
                pass

    set_progress(1.0, "Completed")
    emit(f"[power_cycle] result saved: {result_path}")
    return result_path
