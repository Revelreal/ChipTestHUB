# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from config import DEFAULT_DEVICE_CONFIG

test_bp = Blueprint("test", __name__)


def _json() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


@test_bp.get("/ports")
def list_serial_ports():
    import serial.tools.list_ports

    ports = serial.tools.list_ports.comports()
    port_list = [
        {
            "name": port.name,
            "port": port.device,
            "description": port.description,
            "hwid": port.hwid,
        }
        for port in ports
    ]
    return jsonify({"success": True, "ports": port_list})


@test_bp.get("/visa")
def list_visa_devices():
    try:
        import pyvisa

        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        visa_list = [{"resource": res} for res in resources]
        return jsonify({"success": True, "devices": visa_list})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "devices": []})


@test_bp.get("/tasks")
def list_tasks():
    from app import task_manager

    return jsonify({"success": True, "tasks": task_manager.list_tasks()})


@test_bp.post("/voltage/start")
def voltage_start():
    from app import app, task_manager

    payload = _json()
    app.logger.info(f"[voltage_start] 收到请求 payload = {payload}")

    gateway_port = payload.get("gateway_port", "").strip()
    power_address = payload.get("power_address", "").strip()

    if not gateway_port:
        return jsonify({"success": False, "message": "请选择串口 (LIN网关)"}), 400
    if not power_address:
        return jsonify({"success": False, "message": "请选择电源设备 (VISA)"}), 400

    payload["gateway_port"] = gateway_port
    payload["power_address"] = power_address

    payload.setdefault("gateway_baudrate", 115200)

    app.logger.info(f"[voltage_start] 最终 payload = {payload}")

    info = task_manager.start_voltage_scan(payload)
    return jsonify({"success": True, "task": info.to_dict()})


@test_bp.get("/voltage/status")
def voltage_status():
    from app import task_manager

    # Return latest voltage_scan task
    tasks = task_manager.list_tasks()
    latest = None
    for t in tasks.values():
        if t.get("task_type") != "voltage_scan":
            continue
        if latest is None or (t.get("started_at", 0) > latest.get("started_at", 0)):
            latest = t
    return jsonify({"success": True, "task": latest})


@test_bp.post("/voltage/stop")
def voltage_stop():
    from app import task_manager

    payload = _json()
    task_id = payload.get("task_id")
    if not task_id:
        return jsonify({"success": False, "message": "task_id required"}), 400
    ok = task_manager.stop_task(str(task_id))
    if ok:
        return jsonify({"success": True})
    info = task_manager.get_task(str(task_id))
    if not info:
        return jsonify({"success": False, "message": "Task not found"}), 404
    if info.status == "stopping" or info.status == "stopped":
        return jsonify({"success": True, "message": "Task already stopping"})
    return jsonify({"success": False, "message": f"Task already {info.status}"})


@test_bp.get("/voltage-set/latest")
def voltage_set_latest():
    import os
    import glob

    csv_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_results")
    if not os.path.exists(csv_dir):
        return jsonify({"success": False, "message": "No test results directory"}), 404

    csv_files = glob.glob(os.path.join(csv_dir, "voltage_set_*.csv"))
    if not csv_files:
        return jsonify({"success": False, "message": "No voltage set results found"}), 404

    latest_file = max(csv_files, key=os.path.getmtime)

    try:
        import csv
        with open(latest_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return jsonify({"success": False, "message": "CSV file is empty"}), 404

            latest_row = rows[-1]
            return jsonify({
                "success": True,
                "data": {
                    "seq": int(latest_row.get("seq", 0)),
                    "time": latest_row.get("time", ""),
                    "set_voltage": float(latest_row.get("set_voltage", 0)),
                    "nad": int(latest_row.get("nad", 0)),
                    "ledindex": int(latest_row.get("ledindex", 0)),
                    "led_volt0": int(latest_row.get("led_volt0", 0)),
                    "led_volt1": int(latest_row.get("led_volt1", 0)),
                    "led_volt2": int(latest_row.get("led_volt2", 0)),
                    "vbat_v": int(latest_row.get("vbat_v", 0)),
                    "vbuck_v": int(latest_row.get("vbuck_v", 0)),
                    "chiptemp": float(latest_row.get("chiptemp", 0)),
                },
                "file": os.path.basename(latest_file)
            })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@test_bp.post("/voltage-set/start")
def voltage_set_start():
    from app import app, task_manager

    payload = _json()
    app.logger.info(f"[voltage_set_start] 收到请求 payload = {payload}")

    gateway_port = payload.get("gateway_port", "").strip()
    power_address = payload.get("power_address", "").strip()
    voltage = payload.get("voltage")
    nad = payload.get("nad", 1)

    if not gateway_port:
        return jsonify({"success": False, "message": "请选择串口 (LIN网关)"}), 400
    if not power_address:
        return jsonify({"success": False, "message": "请选择电源设备 (VISA)"}), 400
    if voltage is None:
        return jsonify({"success": False, "message": "请输入目标电压"}), 400

    try:
        voltage = float(voltage)
        if voltage < 0 or voltage > 24:
            return jsonify({"success": False, "message": "电压值超出范围 (0-24V)"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "电压值无效"}), 400

    payload["gateway_port"] = gateway_port
    payload["power_address"] = power_address
    payload["nad"] = int(nad)
    payload["gateway_baudrate"] = 115200
    payload["settle_s"] = 0.5
    payload.setdefault("repeat_count", 1)

    app.logger.info(f"[voltage_set_start] 最终 payload = {payload}")

    info = task_manager.start_voltage_set(payload)
    return jsonify({"success": True, "task": info.to_dict()})


@test_bp.get("/voltage-set/status")
def voltage_set_status():
    from app import task_manager

    tasks = task_manager.list_tasks()
    latest = None
    for t in tasks.values():
        if t.get("task_type") != "voltage_set":
            continue
        if latest is None or (t.get("started_at", 0) > latest.get("started_at", 0)):
            latest = t
    return jsonify({"success": True, "task": latest})


@test_bp.post("/voltage-set/stop")
def voltage_set_stop():
    from app import task_manager

    payload = _json()
    task_id = payload.get("task_id")
    if not task_id:
        return jsonify({"success": False, "message": "task_id required"}), 400
    ok = task_manager.stop_task(str(task_id))
    if ok:
        return jsonify({"success": True})
    info = task_manager.get_task(str(task_id))
    if not info:
        return jsonify({"success": False, "message": "Task not found"}), 404
    if info.status == "stopping" or info.status == "stopped":
        return jsonify({"success": True, "message": "Task already stopping"})
    return jsonify({"success": False, "message": f"Task already {info.status}"})


@test_bp.post("/power-cycle/start")
def power_cycle_start():
    from app import app, task_manager

    payload = _json()
    app.logger.info(f"[power_cycle_start] 收到请求 payload = {payload}")

    power_address = payload.get("power_address", "").strip()
    voltage = payload.get("voltage")
    cycle_count = payload.get("cycle_count", 10)
    on_time_s = payload.get("on_time_s", 2)
    off_time_s = payload.get("off_time_s", 1)

    if not power_address:
        return jsonify({"success": False, "message": "请选择电源设备 (VISA)"}), 400
    if voltage is None:
        return jsonify({"success": False, "message": "请输入目标电压"}), 400

    try:
        voltage = float(voltage)
        if voltage < 0 or voltage > 24:
            return jsonify({"success": False, "message": "电压值超出范围 (0-24V)"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "电压值无效"}), 400

    try:
        cycle_count = int(cycle_count)
        if cycle_count < 1:
            return jsonify({"success": False, "message": "开关次数必须大于0"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "开关次数无效"}), 400

    payload["power_address"] = power_address
    payload["voltage"] = voltage
    payload["cycle_count"] = cycle_count
    payload["on_time_s"] = float(on_time_s)
    payload["off_time_s"] = float(off_time_s)

    app.logger.info(f"[power_cycle_start] 最终 payload = {payload}")

    info = task_manager.start_power_cycle(payload)
    return jsonify({"success": True, "task": info.to_dict()})


@test_bp.get("/power-cycle/status")
def power_cycle_status():
    from app import task_manager

    tasks = task_manager.list_tasks()
    latest = None
    for t in tasks.values():
        if t.get("task_type") != "power_cycle":
            continue
        if latest is None or (t.get("started_at", 0) > latest.get("started_at", 0)):
            latest = t
    return jsonify({"success": True, "task": latest})


@test_bp.post("/power-cycle/stop")
def power_cycle_stop():
    from app import task_manager

    payload = _json()
    task_id = payload.get("task_id")
    if not task_id:
        return jsonify({"success": False, "message": "task_id required"}), 400
    ok = task_manager.stop_task(str(task_id))
    if ok:
        return jsonify({"success": True})
    info = task_manager.get_task(str(task_id))
    if not info:
        return jsonify({"success": False, "message": "Task not found"}), 404
    if info.status == "stopping" or info.status == "stopped":
        return jsonify({"success": True, "message": "Task already stopping"})
    return jsonify({"success": False, "message": f"Task already {info.status}"})


# -------- 温度扫描 --------
@test_bp.post("/temp/start")
def temp_start():
    from app import app, task_manager

    payload = _json()
    app.logger.info(f"[temp_start] 收到请求 payload = {payload}")

    gateway_port = payload.get("gateway_port", "").strip()
    chamber_com = payload.get("chamber_com", "").strip()

    if not gateway_port:
        return jsonify({"success": False, "message": "请选择 LIN 网关串口"}), 400
    if not chamber_com:
        return jsonify({"success": False, "message": "请选择温箱串口"}), 400

    temp_start_val = int(payload.get("temp_start", -40))
    temp_end = int(payload.get("temp_end", 150))
    temp_step = int(payload.get("temp_step", 10))

    if temp_step <= 0:
        return jsonify({"success": False, "message": "温度步进必须大于 0"}), 400
    if temp_start_val == temp_end:
        return jsonify({"success": False, "message": "起始温度和终止温度不能相同"}), 400

    payload["gateway_port"] = gateway_port
    payload["chamber_com"] = chamber_com
    payload.setdefault("gateway_baudrate", 115200)
    payload.setdefault("chamber_baudrate", 19200)
    payload.setdefault("nad_start", 1)
    payload.setdefault("device_count", 5)

    # NAD 列表（用于邮件图表）
    nad_start = int(payload.get("nad_start", 1))
    device_count = int(payload.get("device_count", 5))
    payload["nad_list"] = list(range(nad_start, nad_start + device_count))

    app.logger.info(f"[temp_start] 最终 payload = {payload}")

    info = task_manager.start_temp_scan(payload)
    return jsonify({"success": True, "task": info.to_dict()})


@test_bp.get("/temp/status")
def temp_status():
    from app import task_manager
    tasks = task_manager.list_tasks()
    latest = None
    for t in tasks.values():
        if t.get("task_type") != "temp_scan":
            continue
        if latest is None or (t.get("started_at", 0) > latest.get("started_at", 0)):
            latest = t
    return jsonify({"success": True, "task": latest})


@test_bp.post("/temp/stop")
def temp_stop():
    from app import task_manager

    payload = _json()
    task_id = payload.get("task_id")
    if not task_id:
        return jsonify({"success": False, "message": "task_id required"}), 400
    ok = task_manager.stop_task(str(task_id))
    if ok:
        return jsonify({"success": True})
    info = task_manager.get_task(str(task_id))
    if not info:
        return jsonify({"success": False, "message": "Task not found"}), 404
    if info.status in ("stopping", "stopped"):
        return jsonify({"success": True, "message": f"Task already {info.status}"})
    return jsonify({"success": False, "message": f"Task already {info.status}"})


@test_bp.get("/temp/latest")
def temp_latest():
    """读取最新生成的温度扫描 CSV，返回 JSON"""
    import csv
    import glob
    import os

    csv_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_results")
    if not os.path.exists(csv_dir):
        return jsonify({"success": False, "message": "结果文件夹不存在"}), 404

    csv_files = glob.glob(os.path.join(csv_dir, "temp_scan_*.csv"))
    if not csv_files:
        return jsonify({"success": False, "message": "暂无温度扫描结果"}), 404

    latest_file = max(csv_files, key=os.path.getmtime)

    try:
        rows = []
        with open(latest_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        from collections import defaultdict
        data_by_nad = defaultdict(list)
        for row in rows:
            try:
                nad = int(row.get("nad", 0))
                target = float(row.get("target_temp", 0))
                chip = float(row.get("chiptemp", ""))
                chamber = row.get("chamber_temp", "")
                if chip and str(chip) != "None":
                    data_by_nad[nad].append({
                        "target_temp": target,
                        "chiptemp": chip,
                        "chamber_temp": float(chamber) if chamber not in ("", "None") else None,
                        "time": row.get("time", ""),
                    })
            except (ValueError, TypeError):
                continue

        result = {}
        for nad, records in data_by_nad.items():
            temp_groups = defaultdict(list)
            for r in records:
                temp_groups[r["target_temp"]].append(r["chiptemp"])
            agg = []
            for t in sorted(temp_groups.keys()):
                vals = temp_groups[t]
                agg.append({
                    "target_temp": t,
                    "chiptemp": round(sum(vals) / len(vals), 2),
                    "count": len(vals),
                })
            result[nad] = agg

        return jsonify({
            "success": True,
            "filename": os.path.basename(latest_file),
            "nad_data": result,
            "total_rows": len(rows),
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@test_bp.post("/nad/scan")
def scan_nad():
    from app import app

    payload = _json()
    gateway_port = payload.get("gateway_port", "COM3")
    gateway_baudrate = payload.get("gateway_baudrate", 115200)
    nad_start = payload.get("nad_start", 1)
    nad_end = payload.get("nad_end", 15)

    app.logger.info(f"[nad_scan] 开始扫描 NAD {nad_start}-{nad_end} @ {gateway_port}")

    try:
        from LINGateWay import drivers as GatewayDriver

        gateway = GatewayDriver(gateway_port, gateway_baudrate)
        found_devices = []

        for nad in range(nad_start, nad_end + 1):
            try:
                data = gateway.GET_RUN_Voltage(nad)
                if data is not None and isinstance(data, tuple) and len(data) >= 9:
                    if data[0] >= 0:
                        found_devices.append({
                            "nad": nad,
                            "command": data[0],
                            "led_index": data[1],
                            "led_volt0": data[3],
                            "led_volt1": data[4],
                            "led_volt2": data[5],
                            "vbat": data[6],
                            "vbuck": data[7],
                            "temp": data[8],
                        })
                        app.logger.info(f"[nad_scan] 找到设备 NAD={nad}")
            except Exception as e:
                pass

        return jsonify({
            "success": True,
            "found_devices": found_devices,
            "scanned_range": f"{nad_start}-{nad_end}"
        })
    except Exception as e:
        app.logger.error(f"[nad_scan] 错误: {e}")
        return jsonify({"success": False, "message": str(e)})


@test_bp.get("/results/<filename>")
def download_result(filename):
    import os
    from flask import send_from_directory

    result_dir = os.path.join(os.getcwd(), "test_results")
    return send_from_directory(result_dir, filename, as_attachment=True)


@test_bp.get("/results/")
def list_results():
    import os
    from datetime import datetime

    result_dir = os.path.join(os.getcwd(), "test_results")
    if not os.path.isdir(result_dir):
        return jsonify({"success": True, "files": []})

    files = []
    for f in os.listdir(result_dir):
        if f.endswith(".csv"):
            path = os.path.join(result_dir, f)
            stat = os.stat(path)
            files.append({
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"success": True, "files": files})


@test_bp.post("/results/open-folder")
def open_results_folder():
    import subprocess
    import sys

    result_dir = os.path.join(os.getcwd(), "test_results")
    if not os.path.isdir(result_dir):
        return jsonify({"success": False, "message": "结果文件夹不存在"}), 404

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", result_dir])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", result_dir])
        else:
            subprocess.Popen(["xdg-open", result_dir])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# JLink / Flash 操作
# ──────────────────────────────────────────────────────────────────────────────

@test_bp.get("/jlink/list-chips")
def jlink_list_chips():
    """返回所有可用的芯片列表"""
    from services.jlink_service import list_chip_projects
    chips = list_chip_projects()
    return jsonify({"success": True, "chips": chips})


@test_bp.get("/jlink/check")
def jlink_check():
    """检测 J-Link 连接状态"""
    from services.jlink_service import check_connection
    chip = request.args.get("chip", "iND23226")
    result = check_connection(chip)
    return jsonify({"success": result.success, "message": result.message})


@test_bp.post("/jlink/burn")
def jlink_burn():
    """烧录固件到芯片"""
    from services.jlink_service import burn_firmware
    from app import task_manager

    payload = request.get_json() or {}
    chip_name = str(payload.get("chip_name", "iND23226"))
    firmware_path = str(payload.get("firmware_path", ""))

    if not firmware_path:
        return jsonify({"success": False, "message": "firmware_path 不能为空"}), 400
    if not os.path.exists(firmware_path):
        return jsonify({"success": False, "message": f"固件文件不存在: {firmware_path}"}), 400

    result = burn_firmware(chip_name, firmware_path)
    return jsonify({
        "success": result.success,
        "message": result.message,
        "output": result.output[:500],
    })


@test_bp.post("/jlink/read-flash")
def jlink_read_flash():
    """回读芯片 Flash"""
    from services.jlink_service import read_flash

    payload = request.get_json() or {}
    chip_name = str(payload.get("chip_name", "iND23226"))
    output_path = str(payload.get("output_path", ""))
    addr = int(payload.get("addr", 0x00000000), 16) if isinstance(payload.get("addr"), str) else int(payload.get("addr", 0x00000000))
    _size = payload.get("size", 0x20000)
    size = int(_size, 16) if isinstance(_size, str) else int(_size)

    if not output_path:
        return jsonify({"success": False, "message": "output_path 不能为空"}), 400

    result = read_flash(chip_name, output_path, addr=addr, size=size)
    return jsonify({
        "success": result.success,
        "message": result.message,
        "file_path": result.file_path,
    })


@test_bp.post("/jlink/compare")
def jlink_compare():
    """对比两个 BIN 文件"""
    from services.bin_compare import compare_bin_files

    payload = request.get_json() or {}
    file_before = str(payload.get("file_before", ""))
    file_after = str(payload.get("file_after", ""))
    output_csv = str(payload.get("output_csv", ""))

    if not file_before or not file_after:
        return jsonify({"success": False, "message": "file_before 和 file_after 不能为空"}), 400
    if not os.path.exists(file_before):
        return jsonify({"success": False, "message": f"参考文件不存在: {file_before}"}), 400
    if not os.path.exists(file_after):
        return jsonify({"success": False, "message": f"对比文件不存在: {file_after}"}), 400

    if not output_csv:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = os.path.join("test_results", f"bin_diff_{ts}.csv")

    result = compare_bin_files(file_before, file_after, output_csv)

    # 读取两个文件的原始字节（用于填充无差异位置）
    with open(file_before, "rb") as f:
        before_bytes = f.read()
    with open(file_after, "rb") as f:
        after_bytes = f.read()

    ROW_SIZE = 16
    rows = []
    diff_map = {e.addr: (e.before, e.after) for e in result.diff_entries}
    diff_set = set(diff_map.keys())

    def _build_row(start: int, bdata: bytes, adata: bytes) -> dict:
        """构建单行十六进制数据"""
        before_row = []
        after_row = []
        has_diff = False
        for i in range(start, start + ROW_SIZE):
            if i in diff_map:
                b, a = diff_map[i]
                before_row.append(f"{b:02X}")
                after_row.append(f"{a:02X}")
                if b != a:
                    has_diff = True
            elif i < len(bdata) and i < len(adata):
                before_row.append(f"{bdata[i]:02X}")
                after_row.append(f"{adata[i]:02X}")
            else:
                before_row.append(None)
                after_row.append(None)
        return {
            "addr": f"0x{start:04X}",
            "before": before_row,
            "after": after_row,
            "has_diff": has_diff,
        }

    if result.identical:
        MAX_ROWS_IDENTICAL = 32
        for r in range(min(MAX_ROWS_IDENTICAL, (result.total_bytes + ROW_SIZE - 1) // ROW_SIZE)):
            rows.append(_build_row(r * ROW_SIZE, before_bytes, after_bytes))
        has_more = result.total_bytes > MAX_ROWS_IDENTICAL * ROW_SIZE
        rows_to_send = rows
    else:
        diff_rows = set(addr // ROW_SIZE for addr in diff_set)
        shown_rows = set()
        CONTEXT = 2

        for row_addr in sorted(diff_rows):
            for r in range(max(0, row_addr - CONTEXT), row_addr + CONTEXT + 1):
                if r not in shown_rows:
                    shown_rows.add(r)
                    rows.append(_build_row(r * ROW_SIZE, before_bytes, after_bytes))

        rows_to_send = rows[:100]
        has_more = len(rows) > 100

    return jsonify({
        "success": True,
        "identical": result.identical,
        "total_bytes": result.total_bytes,
        "diff_count": result.diff_count,
        "rows": rows_to_send,
        "csv_path": result.csv_path,
        "has_more": has_more,
    })


