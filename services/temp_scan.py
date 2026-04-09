# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("temp_scan")

TEMP_TOLERANCE = 1.0        # 温箱到温判定窗口 ±1°C
SOAK_TIME_S = 30             # 保温时间，单位秒
READ_INTERVAL_S = 1          # 读取间隔，单位秒
READ_COUNT_PER_POINT = 10   # 每温度点读取次数


def _build_temp_table(start: int, end: int, step: int) -> List[int]:
    if step <= 0:
        raise ValueError("温度步进必须大于 0")
    if start == end:
        raise ValueError("起始温度和终止温度不能相同")
    result = []
    x = start
    if step > 0:
        while x <= end:
            result.append(x)
            x += step
    else:
        while x >= end:
            result.append(x)
            x += step
    return result


@dataclass
class ChamberCtrl:
    """温箱控制器：SetChamberTemperature 在独立线程执行，stop 可立即中断"""
    chamber: Any
    origin: List[int]
    target_temp: Optional[float] = None
    done: bool = False
    error: Optional[str] = None
    lock: Optional[threading.Lock] = None

    def set_temp(self, temp: float) -> None:
        self.target_temp = temp
        self.done = False
        self.error = None
        t = threading.Thread(target=self._worker, daemon=True, name="chamber-ctrl")
        t.start()

    def _worker(self) -> None:
        try:
            # 温箱控制顺序：先停止 → 设温度 → 启动
            self.chamber.stop(self.origin)
            time.sleep(0.1)
            self.chamber.SetChamberTemperature(self.origin, int(self.target_temp))
            time.sleep(0.1)
            self.chamber.start(self.origin)
            self.done = True
        except Exception as e:
            self.error = str(e)
            self.done = True

    def wait_done(self, timeout: float = 999999.0) -> bool:
        """等待 SetChamberTemperature 完成（内部每秒检查 stop_event）"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.done:
                return self.error is None
            time.sleep(0.5)
        return False

    def is_done(self) -> bool:
        return self.done


def _stop_chamber(chamber, origin, chamber_ctrl):
    """统一停止温箱"""
    try:
        chamber.stop(origin)
        logger.info("[状态] 温箱已停止")
    except Exception as e:
        logger.warning(f"[WARN] 温箱停止异常: {e}")


def run_temp_scan(
    payload: Dict[str, Any],
    *,
    emit: Callable[[str], None],
    set_progress: Callable[[float, str], None],
    emit_data: Callable[[Dict[str, Any]], None],
    stop_event,  # threading.Event
) -> str:
    """
    温箱温度扫描任务:
      1. 自动寻址扫描 NAD
      2. 按用户设定的温度范围和步进执行温箱控温
      3. 每个温度点等待稳定后读取所有板子的芯片温度
      4. stop 具有最高优先级，收到信号立即停止温箱
    """
    logger.info("============================================================")
    logger.info("温度扫描任务启动")
    logger.info("============================================================")

    # -------- 用户设置的参数全部记录 --------
    gateway_port = str(payload.get("gateway_port", ""))
    gateway_baudrate = int(payload.get("gateway_baudrate", 115200))
    chamber_com = str(payload.get("chamber_com", ""))
    chamber_baudrate = int(payload.get("chamber_baudrate", 19200))
    temp_start = int(payload.get("temp_start", -40))
    temp_end = int(payload.get("temp_end", 150))
    temp_step = int(payload.get("temp_step", 10))
    nad_start = int(payload.get("nad_start", 1))
    device_count = int(payload.get("device_count", 5))
    soak_time = float(payload.get("soak_time", SOAK_TIME_S))
    read_interval = float(payload.get("read_interval", READ_INTERVAL_S))
    read_count = int(payload.get("read_count", READ_COUNT_PER_POINT))

    logger.info(f"[参数] 网关串口: {gateway_port} @ {gateway_baudrate} baud")
    logger.info(f"[参数] 温箱串口: {chamber_com} @ {chamber_baudrate} baud")
    logger.info(f"[参数] 温度范围: {temp_start}°C → {temp_end}°C (步进 {temp_step}°C)")
    logger.info(f"[参数] NAD范围: {nad_start} ~ {nad_start + device_count - 1} (共 {device_count} 个)")
    logger.info(f"[参数] 保温时间: {soak_time}s")
    logger.info(f"[参数] 每点读取: {read_count} 次, 间隔 {read_interval}s")
    emit(f"[INFO] 参数: {temp_start}~{temp_end}°C step={temp_step}°C NAD={nad_start}~{nad_start+device_count-1}")

    TEMP_TABLE = _build_temp_table(temp_start, temp_end, temp_step)
    logger.info(f"[参数] 生成的温度表 ({len(TEMP_TABLE)} 个节点): {TEMP_TABLE}")
    emit(f"[INFO] 温度表: {TEMP_TABLE}")

    set_progress(0.0, "Connecting devices")
    logger.info("[状态] 正在连接设备...")

    # -------- 连接 LIN 网关 --------
    try:
        from LINGateWay import drivers as GatewayDriver
        gateway = GatewayDriver(gateway_port, gateway_baudrate)
        logger.info(f"[OK] LIN网关连接成功: {gateway_port}")
        emit(f"[INFO] LIN网关已连接: {gateway_port}")
    except Exception as e:
        logger.error(f"[ERROR] LIN网关连接失败: {e}")
        emit(f"[ERROR] LIN网关连接失败: {e}")
        raise RuntimeError(f"LINGateway连接失败: {e}") from e

    # -------- 连接温箱 --------
    chamber_ctrl: Optional[ChamberCtrl] = None
    try:
        import TemperatureChamber
        chamber = TemperatureChamber.drivers(chamber_com, chamber_baudrate)
        origin = [0x00] * 8
        # 注意：先不调用 start()，只在每次设置温度时按【停止→设温度→启动】顺序执行
        chamber_ctrl = ChamberCtrl(chamber=chamber, origin=origin)
        logger.info(f"[OK] 温箱连接成功: {chamber_com}")
        emit(f"[INFO] 温箱已连接: {chamber_com}")
    except Exception as e:
        logger.error(f"[ERROR] 温箱连接失败: {e}")
        emit(f"[ERROR] 温箱连接失败: {e}")
        raise RuntimeError(f"TemperatureChamber连接失败: {e}") from e

    # -------- 自动寻址 --------
    set_progress(0.02, "Scanning NAD devices")
    logger.info(f"[状态] ===== 开始自动寻址 (NAD {nad_start} ~ {nad_start + device_count - 1}) =====")
    emit(f"[INFO] ===== 开始自动寻址 =====")
    found_nads: List[int] = []
    for nad in range(nad_start, nad_start + device_count):
        if stop_event.is_set():
            logger.info("[状态] 寻址中断 (stop)")
            emit("[INFO] 寻址中断")
            break
        try:
            data = gateway.GET_RUN_Voltage(nad)
            if data is not None and isinstance(data, tuple) and len(data) >= 9 and data[0] >= 0:
                found_nads.append(nad)
                temp_raw = data[8]
                if temp_raw > 32767:
                    temp_val = temp_raw - 65536
                else:
                    temp_val = temp_raw
                logger.info(f"[NAD扫描] ✓ NAD={nad}, 温度={temp_val}°C (原始={temp_raw})")
                emit(f"[OK] NAD={nad} 在线, 温度={temp_val}°C")
            else:
                logger.info(f"[NAD扫描] NAD={nad} 无响应")
                emit(f"[WARN] NAD={nad} 无响应")
        except Exception as e:
            logger.warning(f"[NAD扫描] NAD={nad} 异常: {e}")
            emit(f"[WARN] NAD={nad} 查询异常")
            time.sleep(0.2)

    logger.info(f"[NAD扫描] 完成, 找到 {len(found_nads)} 个: {found_nads}")
    emit(f"[INFO] 寻址完成, 找到 {len(found_nads)} 个设备: NAD={found_nads}")
    if not found_nads:
        raise RuntimeError("未找到任何设备，请检查连接和NAD地址！")

    # -------- 准备CSV --------
    os.makedirs("test_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = os.path.join("test_results", f"temp_scan_{ts}.csv")
    logger.info(f"[文件] 结果文件: {result_path}")

    total_points = len(TEMP_TABLE)
    seq = 0

    with open(result_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "seq", "time", "target_temp", "chamber_temp",
            "nad", "led_index", "led_volt0", "led_volt1", "led_volt2",
            "vbat", "vbuck", "chiptemp"
        ])

        for temp_idx, target_temp in enumerate(TEMP_TABLE):
            # ---- STOP 最高优先级：立即响应 ----
            if stop_event.is_set():
                logger.info(f"[状态] ===== 收到停止信号，退出任务 =====")
                emit(f"[状态] 收到停止信号，退出任务")
                break

            point_p = (temp_idx + 1) / total_points
            prev_p = temp_idx / total_points

            logger.info(f"============================================================")
            logger.info(f"[状态] 【温度节点 {temp_idx + 1}/{total_points}】目标={target_temp}°C")
            emit(f"\n{'='*60}")
            emit(f"[温点 {temp_idx + 1}/{total_points}] 目标={target_temp}°C")

            # ---- 发送温箱设定指令（非阻塞，stop 可立即中断）----
            set_progress(prev_p, f"[{temp_idx + 1}/{total_points}] 设定温箱 {target_temp}°C ...")
            logger.info(f"[→指令] 发送: 温箱设定 {target_temp}°C")
            emit(f"[→] 发送温箱设定: {target_temp}°C")
            try:
                chamber_ctrl.set_temp(float(target_temp))
                # 等待指令完成（最多 3 秒）
                ok = chamber_ctrl.wait_done(timeout=3.0)
                if not ok:
                    err = chamber_ctrl.error or "未知错误"
                    logger.error(f"[ERROR] 温箱指令失败: {err}")
                    emit(f"[ERROR] 温箱指令失败: {err}")
                    raise RuntimeError(f"温箱指令失败: {err}")
                logger.info(f"[→指令] 温箱指令已发送并确认")
                emit(f"[→] 温箱指令已确认")
            except Exception as e:
                logger.error(f"[ERROR] 温箱设定异常: {e}")
                emit(f"[ERROR] 温箱设定异常: {e}")
                raise RuntimeError(f"温箱通讯异常: {e}") from e

            # ---- 等待温箱稳定（每秒检查 stop）----
            logger.info(f"[状态] 等待温箱到达 {target_temp}°C (±{TEMP_TOLERANCE}°C) ...")
            emit(f"[INFO] 等待温箱到达 {target_temp}°C ...")
            reached = False
            wait_sec = 0
            while True:
                if stop_event.is_set():
                    logger.info(f"[状态] 等待到温中被【停止】, 立即退出")
                    emit(f"[状态] ★ 停止生效，立即退出")
                    _stop_chamber(chamber, origin, chamber_ctrl)
                    chamber_ctrl = None
                    break
                try:
                    # 清空串口缓冲区，避免残留数据干扰
                    _ = chamber.port.readall()
                    current_chamber_temp = chamber.GetChamberTemperature(origin)
                except Exception as e:
                    logger.warning(f"[WARN] 读取温箱温度异常: {e}")
                    current_chamber_temp = None

                if current_chamber_temp is not None:
                    logger.info(f"[温箱] {current_chamber_temp:.1f}°C / 目标 {target_temp}°C  (等待 {wait_sec}s)")
                    emit(f"[INFO] 温箱: {current_chamber_temp:.1f}°C / 目标 {target_temp}°C")
                    if (target_temp - TEMP_TOLERANCE) <= current_chamber_temp <= (target_temp + TEMP_TOLERANCE):
                        logger.info(f"[状态] ✓ 温箱到温: {current_chamber_temp:.1f}°C")
                        emit(f"[OK] ✓ 温箱到温: {current_chamber_temp:.1f}°C")
                        reached = True
                        break
                wait_sec += 1
                time.sleep(1)

            if stop_event.is_set():
                break
            if not reached:
                continue

            # ---- 保温阶段（每秒检查 stop）----
            logger.info(f"[状态] 保温 {soak_time}s ...")
            emit(f"[INFO] 保温 {soak_time}s ...")
            for sec in range(int(soak_time), 0, -1):
                if stop_event.is_set():
                    logger.info(f"[状态] 保温中被【停止】, 立即退出")
                    emit(f"[状态] ★ 停止生效，立即退出")
                    _stop_chamber(chamber, origin, chamber_ctrl)
                    chamber_ctrl = None
                    break
                soak_p = prev_p + 0.6 * point_p + 0.2 * point_p * (1 - sec / soak_time)
                set_progress(min(soak_p, point_p * 0.99),
                    f"[{temp_idx + 1}/{total_points}] 保温 {sec}s @ {target_temp}°C")
                time.sleep(1)
            time.sleep(1)

            if stop_event.is_set():
                break

            # ---- 读取温度数据（等温度点稳定后才记录）----
            logger.info(f"[状态] ===== 记录中 @ {target_temp}°C =====")
            emit(f"[记录] 开始记录 @ {target_temp}°C ...")

            # 内存聚合：每次读取轮次完成后，累加到对应NAD的列表
            chip_readings = {nad: [] for nad in found_nads}
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for read_i in range(read_count):
                if stop_event.is_set():
                    logger.info(f"[状态] 记录中被【停止】, 立即退出")
                    emit(f"[状态] ★ 停止生效，立即退出")
                    _stop_chamber(chamber, origin, chamber_ctrl)
                    chamber_ctrl = None
                    break

                # 每轮次：轮询所有NAD，实时写CSV，内存聚合温度
                read_now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for nad in found_nads:
                    if stop_event.is_set():
                        _stop_chamber(chamber, origin, chamber_ctrl)
                        chamber_ctrl = None
                        break

                    try:
                        data = gateway.GET_RUN_Voltage(nad)
                    except Exception as e:
                        logger.warning(f"[LIN] NAD={nad} 通讯异常: {e}")
                        emit(f"[ERROR] NAD={nad} 通讯异常")
                        continue

                    if data == -1:
                        logger.error(f"[LIN] NAD={nad} 3C通讯错误")
                        emit(f"[ERROR] NAD={nad} 3C通讯错误")
                        continue
                    if data == -2:
                        logger.error(f"[LIN] NAD={nad} 3D通讯错误 (无响应)")
                        emit(f"[ERROR] NAD={nad} 3D通讯错误")
                        continue
                    if not isinstance(data, tuple) or len(data) < 9:
                        logger.error(f"[LIN] NAD={nad} 数据格式错误: {data}")
                        emit(f"[ERROR] NAD={nad} 数据格式错误")
                        continue

                    chiptemp_raw = data[8]
                    if chiptemp_raw > 32767:
                        chiptemp = chiptemp_raw - 65536
                    else:
                        chiptemp = chiptemp_raw

                    logger.info(f"[读取] NAD={nad} 芯片温度={chiptemp}°C (原始={chiptemp_raw}) (温箱={current_chamber_temp}°C)")
                    emit(f"[OK] NAD={nad} {chiptemp}°C")

                    chip_readings[nad].append(chiptemp)
                    seq += 1
                    w.writerow([
                        seq, read_now_str, target_temp,
                        current_chamber_temp if current_chamber_temp is not None else "",
                        nad, data[1], data[3], data[4], data[5],
                        data[6] if data[6] is not None else 0, data[7], chiptemp
                    ])
                # 每轮次NAD全部写完后立即flush，确保断电/中断不丢数据
                f.flush()

                if stop_event.is_set():
                    break

                read_p = prev_p + 0.8 * point_p + 0.2 * point_p * (read_i + 1) / read_count
                set_progress(read_p,
                    f"[{temp_idx + 1}/{total_points}] 记录中 {target_temp}°C ({read_i + 1}/{read_count})")
                time.sleep(read_interval)

            # ---- 所有轮次完成后，发聚合平均值到图表 ----
            if not stop_event.is_set():
                final_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for nad in found_nads:
                    if len(chip_readings[nad]) > 0:
                        avg_chip = sum(chip_readings[nad]) / len(chip_readings[nad])
                        emit_data({
                            "seq": seq,
                            "time": final_time,
                            "target_temp": target_temp,
                            "chamber_temp": current_chamber_temp,
                            "nad": nad,
                            "chiptemp": avg_chip,
                            "is_final": True,
                            "label": f"{target_temp}°C",
                        })
                        logger.info(f"[图表] NAD={nad} {target_temp}°C 平均={avg_chip:.1f}°C ({len(chip_readings[nad])}次)")

            if stop_event.is_set():
                break

    # -------- 任务结束：确保温箱停止 --------
    _stop_chamber(chamber, origin, chamber_ctrl)

    logger.info("============================================================")
    logger.info(f"[完成] 测试结束, 共记录 {seq} 条数据")
    logger.info(f"[文件] 结果已保存: {result_path}")
    emit(f"[INFO] ===== 测试结束 =====")
    emit(f"[INFO] 共记录 {seq} 条数据")
    emit(f"[INFO] 结果文件: {result_path}")
    set_progress(1.0, "Completed")
    return result_path, found_nads
