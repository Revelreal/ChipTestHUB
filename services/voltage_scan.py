# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional

logger = logging.getLogger("voltage_scan")


def _frange(start: float, stop: float, step: float) -> Iterable[float]:
    if step == 0:
        raise ValueError("step must not be 0")
    n = 0
    x = start
    if step > 0:
        while x <= stop + 1e-9:
            yield round(x, 6)
            n += 1
            x = start + n * step
    else:
        while x >= stop - 1e-9:
            yield round(x, 6)
            n += 1
            x = start + n * step


def run_voltage_scan(
    payload: Dict[str, Any],
    *,
    emit: Callable[[str], None],
    set_progress: Callable[[float, str], None],
    stop_event,  # threading.Event
) -> str:
    """
    Voltage scan task.
    """
    logger.info(f"===== run_voltage_scan 开始执行 =====")
    logger.info(f"payload = {payload}")

    power_mode: str = "auto"

    voltage_min = float(payload.get("voltage_min", 8))
    voltage_max = float(payload.get("voltage_max", 19))
    voltage_step = float(payload.get("voltage_step", 1))
    repeat_count = int(payload.get("repeat_count", 10))
    device_num = int(payload.get("device_num", 1))
    nad_start = int(payload.get("nad_start", 1))
    settle_s = float(payload.get("settle_s", 0.5))

    gateway_port = str(payload.get("gateway_port", "COM3"))
    gateway_baudrate = int(payload.get("gateway_baudrate", 115200))
    power_address = str(payload.get("power_address", ""))

    emit(f"[DEBUG] ====== 接收到的参数 ======")
    emit(f"[DEBUG] gateway_port = '{gateway_port}'")
    emit(f"[DEBUG] gateway_baudrate = {gateway_baudrate}")
    emit(f"[DEBUG] nad_start = {nad_start}")
    emit(f"[DEBUG] power_address = '{power_address}'")
    emit(f"[DEBUG] ==========================")

    if repeat_count <= 0:
        raise ValueError("repeat_count must be > 0")
    if device_num <= 0:
        raise ValueError("device_num must be > 0")

    os.makedirs("test_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = os.path.join("test_results", f"voltage_scan_{ts}.csv")

    voltages = list(_frange(voltage_min, voltage_max, voltage_step))
    total_steps = max(1, len(voltages) * repeat_count * device_num)

    emit(f"[voltage_scan] power_mode=auto V={voltage_min}..{voltage_max} step={voltage_step} repeat={repeat_count} devices={device_num}")
    set_progress(0.0, "Preparing")

    power = None
    gateway = None

    emit(f"[DEBUG] 进入自动控制电源模式，检查电源地址...")
    if not power_address:
        emit(f"[ERROR] power_address 为空！")
        raise ValueError("power_address is required for voltage scan")
    emit(f"[voltage_scan] connecting power: {power_address}")
    from IT6322A_USB import drivers as PowerDriver

    power = PowerDriver(power_address)
    power.Enter_Remote()
    power.TunrOn_Output()

    emit(f"[voltage_scan] connecting gateway: {gateway_port} @ {gateway_baudrate}")
    from LINGateWay import drivers as GatewayDriver

    gateway = GatewayDriver(gateway_port, gateway_baudrate)
    emit(f"[INFO] 电源和LIN网关已连接")

    with open(result_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "seq",
                "time",
                "set_vbat",
                "nad",
                "command",
                "ledindex",
                "reserved",
                "led_volt0",
                "led_volt1",
                "led_volt2",
                "vbat_v",
                "vbuck_v",
                "chiptemp",
            ]
        )

        seq = 0
        for v in voltages:
            if stop_event.is_set():
                emit("[voltage_scan] stop requested (before set voltage)")
                break

            current_voltage_idx = voltages.index(v)
            p = current_voltage_idx / len(voltages)
            set_progress(p, f"Testing {v}V ({current_voltage_idx+1}/{len(voltages)})")

            emit(f"[voltage_scan] set VBAT={v}V")
            if power is not None:
                power.Set_OutputVolt_CH1(v)
            time.sleep(settle_s)

            for r in range(1, repeat_count + 1):
                if stop_event.is_set():
                    emit("[voltage_scan] stop requested")
                    break

                for nad in range(nad_start, nad_start + device_num):
                    if stop_event.is_set():
                        break

                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    try:
                        data = gateway.GET_RUN_Voltage(nad)
                    except Exception as e:
                        logger.exception(f"[LIN] 通讯异常! nad={nad}: {e}")
                        emit(f"[ERROR] LIN通讯异常 NAD={nad}: {e}")
                        continue
                    logger.info(f"[LIN] GET_RUN_Voltage(nad={nad}) 返回: {data}")
                    if data == -1:
                        logger.error(f"[LIN] 3C通讯错误 (请求发送失败)! nad={nad}")
                        emit(f"[ERROR] 3C通讯错误 NAD={nad}")
                        continue
                    if data == -2:
                        logger.error(f"[LIN] 3D通讯错误 (无响应)! nad={nad} - 请检查: 1.芯片是否上电 2.NAD地址是否正确 3.LIN总线连接")
                        emit(f"[ERROR] 3D通讯错误 NAD={nad} - 芯片无响应，请检查电源和连接!")
                        continue
                    if not isinstance(data, tuple) or len(data) < 9:
                        logger.error(f"[LIN] 数据格式错误! nad={nad}, data={data}")
                        emit(f"[ERROR] 数据格式错误 NAD={nad}")
                        continue
                    command = data[0]
                    ledindex = data[1]
                    reserved = data[2]
                    led_volt0 = data[3]
                    led_volt1 = data[4]
                    led_volt2 = data[5]
                    vbat_v = data[6] if data[6] is not None else 0
                    vbuck_v = data[7]
                    chiptemp = data[8]
                    emit(f"[OK] NAD={nad} LED={ledindex} VBAT={vbat_v}V Temp={chiptemp}°C")

                    seq += 1
                    w.writerow(
                        [
                            seq,
                            now,
                            v,
                            nad,
                            command,
                            ledindex,
                            reserved,
                            led_volt0,
                            led_volt1,
                            led_volt2,
                            vbat_v,
                            vbuck_v,
                            chiptemp,
                        ]
                    )

                    if seq % 10 == 0 or seq == 1:
                        p = seq / total_steps
                        set_progress(p, f"Running {int(p * 100)}% (V={v}, r={r}/{repeat_count}, NAD={nad}/{device_num})")

                if stop_event.is_set():
                    break

        set_progress(1.0, "Completed")
        emit(f"[voltage_scan] result saved: {result_path}")
    return result_path

