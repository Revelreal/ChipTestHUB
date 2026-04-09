# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("voltage_set")


def run_voltage_set(
    payload: Dict[str, Any],
    *,
    emit: Callable[[str], None],
    set_progress: Callable[[float, str], None],
    stop_event,
) -> str:
    """
    Voltage setting task - set a specific voltage and read device data.
    Used for OVP/UVP testing (over-voltage protection / under-voltage protection).
    """
    logger.info(f"===== run_voltage_set 开始执行 =====")
    logger.info(f"payload = {payload}")

    voltage_target = float(payload.get("voltage", 12))
    repeat_count = int(payload.get("repeat_count", 1))
    settle_s = float(payload.get("settle_s", 0.5))

    gateway_port = str(payload.get("gateway_port", "COM3"))
    gateway_baudrate = int(payload.get("gateway_baudrate", 115200))
    power_address = str(payload.get("power_address", ""))

    emit(f"[DEBUG] ====== 电压设置参数 ======")
    emit(f"[DEBUG] target_voltage = {voltage_target}V")
    emit(f"[DEBUG] repeat_count = {repeat_count}")
    emit(f"[DEBUG] gateway_port = '{gateway_port}'")
    emit(f"[DEBUG] power_address = '{power_address}'")
    emit(f"[DEBUG] ==========================")

    os.makedirs("test_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = os.path.join("test_results", f"voltage_set_{ts}.csv")

    set_progress(0.0, "Preparing")

    power = None
    gateway = None

    emit(f"[voltage_set] 设置目标电压: {voltage_target}V")

    if not power_address:
        emit(f"[ERROR] power_address 为空！")
        raise ValueError("power_address is required for voltage set")

    if not gateway_port:
        emit(f"[ERROR] gateway_port 为空！")
        raise ValueError("gateway_port is required for voltage set")

    try:
        emit(f"[voltage_set] connecting power: {power_address}")
        from IT6322A_USB import drivers as PowerDriver
    except Exception as e:
        emit(f"[ERROR] 导入电源驱动失败: {e}")
        raise

    try:
        power = PowerDriver(power_address)
        power.Enter_Remote()
        power.TunrOn_Output()
    except Exception as e:
        emit(f"[ERROR] 连接电源失败: {e}")
        raise

    try:
        emit(f"[voltage_set] connecting gateway: {gateway_port} @ {gateway_baudrate}")
        from LINGateWay import drivers as GatewayDriver
    except Exception as e:
        emit(f"[ERROR] 导入LIN网关驱动失败: {e}")
        raise

    try:
        gateway = GatewayDriver(gateway_port, gateway_baudrate)
    except Exception as e:
        emit(f"[ERROR] 连接LIN网关失败: {e}")
        raise

    emit(f"[INFO] 电源和LIN网关已连接")

    try:
        emit(f"[voltage_set] 设置输出电压: {voltage_target}V")
        if power is not None:
            power.Set_OutputVolt_CH1(voltage_target)
    except Exception as e:
        emit(f"[ERROR] 设置电压失败: {e}")
        raise
    
    time.sleep(settle_s)
    set_progress(0.2, f"Voltage set to {voltage_target}V")

    with open(result_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "seq",
                "time",
                "set_voltage",
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
        emit(f"[DEBUG] 开始循环读取数据, repeat_count={repeat_count}")

        for r in range(1, repeat_count + 1):
            emit(f"[DEBUG] 循环第 {r}/{repeat_count} 次")
            if stop_event.is_set():
                emit("[voltage_set] stop requested")
                break

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nad = int(payload.get("nad", 1))

            try:
                emit(f"[DEBUG] 调用 gateway.GET_RUN_Voltage({nad})")
                data = gateway.GET_RUN_Voltage(nad)
                emit(f"[DEBUG] GET_RUN_Voltage 返回: {data}")
            except Exception as e:
                logger.exception(f"[LIN] 通讯异常! nad={nad}: {e}")
                emit(f"[ERROR] LIN通讯异常 NAD={nad}: {e}")
                continue

            logger.info(f"[LIN] GET_RUN_Voltage(nad={nad}) 返回: {data}")
            emit(f"[DEBUG] 检查返回值: data={data}, type={type(data)}")

            if data == -1:
                logger.error(f"[LIN] 3C通讯错误 (请求发送失败)! nad={nad}")
                emit(f"[ERROR] 3C通讯错误 NAD={nad}")
                continue
            if data == -2:
                logger.error(f"[LIN] 3D通讯错误 (无响应)! nad={nad}")
                emit(f"[ERROR] 3D通讯错误 NAD={nad} - 芯片无响应，请检查电源和连接!")
                continue
            if not isinstance(data, tuple):
                logger.error(f"[LIN] 数据不是tuple类型! nad={nad}, data={data}, type={type(data)}")
                emit(f"[ERROR] 数据类型错误 NAD={nad}, type={type(data)}")
                continue
            if len(data) < 9:
                logger.error(f"[LIN] 数据长度不足! nad={nad}, data={data}, len={len(data)}")
                emit(f"[ERROR] 数据长度不足 NAD={nad}, len={len(data)}")
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

            emit(f"[OK] NAD={nad} LED={ledindex} VBAT={vbat_v}V VBuck={vbuck_v}V Temp={chiptemp}°C")

            seq += 1
            row_data = [
                seq,
                now,
                voltage_target,
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
            emit(f"[DEBUG] 写入CSV行: {row_data}")
            w.writerow(row_data)
            f.flush()
            emit(f"[DEBUG] CSV写入完成, 当前seq={seq}")

            p = 0.2 + (0.8 * r / repeat_count)
            set_progress(p, f"Reading {r}/{repeat_count}")

            time.sleep(0.3)

        emit(f"[DEBUG] 循环结束, 共写入 {seq} 条数据")

    set_progress(1.0, "Completed")
    emit(f"[voltage_set] result saved: {result_path}")
    return result_path
