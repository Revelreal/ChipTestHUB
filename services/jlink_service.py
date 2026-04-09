# -*- coding: utf-8 -*-
"""
JLink 固件烧录与回读服务
封装 JFlash.exe / JLink.exe 命令行操作，提供烧录、回读、连接检测功能。
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jlink")


# jlink_tools 目录，相对于项目根目录
JLINK_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "jlink_tools"
)
# 系统已安装的 JFlash/JLink（优先用新版）
_JFLASH_NEW = r"C:\Program Files (x86)\SEGGER\JLink_V798h\JFlash.exe"
_JLINK_NEW = r"C:\Program Files (x86)\SEGGER\JLink_V798h\JLink.exe"
_JFLASH_OLD = r"C:\Program Files (x86)\SEGGER\JLink_V490\JFlash.exe"
_JLINK_OLD = r"C:\Program Files (x86)\SEGGER\JLink_V490\JLink.exe"
JFLASH_EXE = _JFLASH_NEW if os.path.exists(_JFLASH_NEW) else (_JFLASH_OLD if os.path.exists(_JFLASH_OLD) else os.path.join(JLINK_TOOLS_DIR, "JFlash.exe"))
JLINK_EXE = _JLINK_NEW if os.path.exists(_JLINK_NEW) else (_JLINK_OLD if os.path.exists(_JLINK_OLD) else os.path.join(JLINK_TOOLS_DIR, "JLink.exe"))
PROJECT_DIR = os.path.join(JLINK_TOOLS_DIR, "Project")

# iND23226 Flash 参数（单位：字节）
# 实测 JLink savebin 最大单次可读 64KB（0x10000）
FLASH_SIZE_DEFAULT = 0x10000  # 64KB for iND23226


@dataclass
class JLinkResult:
    success: bool
    message: str
    output: str = ""
    file_path: Optional[str] = None


def _run_jflash(args: list, timeout: int = 60) -> tuple:
    """
    执行 JFlash.exe 命令，返回 (returncode, stdout, stderr)。
    timeout: 超时秒数
    """
    cmd = [JFLASH_EXE] + args
    logger.info(f"[jlink] running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "JFlash.exe 执行超时"
    except FileNotFoundError:
        return -2, "", f"JFlash.exe 未找到: {JFLASH_EXE}"
    except Exception as e:
        return -3, "", str(e)


def _find_jflash_project(chip_name: str) -> Optional[str]:
    """
    根据芯片名称查找对应的 .jflash 工程文件。
    chip_name 例如 "iND23226"
    """
    if not os.path.exists(PROJECT_DIR):
        return None
    for f in os.listdir(PROJECT_DIR):
        if f.lower() == f"{chip_name.lower()}.jflash":
            return os.path.join(PROJECT_DIR, f)
    return None


def _run_jlink_script(script_lines: list, timeout: int = 60, cwd: str = None) -> tuple:
    """
    通过 cmd /c jlink < script.txt 方式执行 JLink 命令。
    script_lines: 命令字符串列表
    cwd: 工作目录（savebin 输出文件会生成在此目录）
    返回 (returncode, stdout, stderr)
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    script_path = os.path.join(project_root, "test_results", f"_jlink_script_{id(script_lines)}.txt")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines) + "\n")

    try:
        proc = subprocess.Popen(
            ["cmd", "/c", JLINK_EXE, "<", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd or project_root,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, "", "JLink.exe 执行超时"
    except FileNotFoundError:
        return -2, "", f"JLink.exe 未找到: {JLINK_EXE}"
    except Exception as e:
        return -3, "", str(e)
    finally:
        if os.path.exists(script_path):
            os.unlink(script_path)


# ────────────────────────────────────────────────────────────────
#  核心操作
# ────────────────────────────────────────────────────────────────

def check_connection(chip_name: str = "iND23226") -> JLinkResult:
    """
    检测 J-Link 是否已连接且能识别芯片。
    相当于 JFlash GUI 里点 "Target -> Connect"。
    """
    project = _find_jflash_project(chip_name)
    if not project:
        return JLinkResult(False, f"未找到芯片 {chip_name} 对应的 .jflash 工程文件")

    returncode, stdout, stderr = _run_jflash([
        "-openProject", project,
        "-connect",
        "-exit",
    ], timeout=30)

    combined = stdout + stderr

    if returncode == -2:
        return JLinkResult(False, "JFlash.exe 未找到，请检查 jlink_tools 目录")
    if "Could not open project" in combined:
        return JLinkResult(False, f"无法打开工程文件: {project}")
    if "No J-Link" in combined or "No device found" in combined or "J-Link not found" in combined:
        return JLinkResult(False, "未检测到 J-Link，请确认 USB 已连接且驱动正常")
    if "Failed to connect" in combined or "ERROR" in combined.upper():
        return JLinkResult(False, f"J-Link 连接失败: {combined[:200]}")

    logger.info(f"[jlink] connection check OK: {combined[:100]}")
    return JLinkResult(True, "J-Link 连接正常", combined[:200])


def burn_firmware(
    chip_name: str,
    firmware_path: str,
    *,
    verify: bool = True,
) -> JLinkResult:
    """
    烧录固件到芯片。

    参数:
        chip_name: 芯片型号，如 "iND23226"
        firmware_path: 固件 .bin 文件路径
        verify: 是否验证（-programverify）
    """
    project = _find_jflash_project(chip_name)
    if not project:
        return JLinkResult(False, f"未找到芯片 {chip_name} 对应的 .jflash 工程文件")

    if not os.path.exists(firmware_path):
        return JLinkResult(False, f"固件文件不存在: {firmware_path}")

    logger.info(f"[jlink] burning {firmware_path} to {chip_name} ...")

    args = [
        "-openProject", project,
        "-connect",
        "-openFirmware", firmware_path,
    ]

    if verify:
        args += ["-erasechip", "-programverify"]
    else:
        args += ["-erasechip", "-program"]

    args += ["-startapplication", "-exit"]

    returncode, stdout, stderr = _run_jflash(args, timeout=120)
    combined = stdout + stderr

    if returncode == -2:
        return JLinkResult(False, "JFlash.exe 未找到")
    if "ERROR" in combined or "Failed" in combined:
        return JLinkResult(False, f"烧录失败: {combined[:300]}", combined)
    if "Target programmed and verified successfully" in combined:
        return JLinkResult(True, "烧录成功（已验证）", combined, firmware_path)

    if returncode == 0:
        return JLinkResult(True, "烧录成功", combined, firmware_path)

    return JLinkResult(False, f"烧录异常（code={returncode}）: {combined[:300]}", combined)


def read_flash(
    chip_name: str,
    output_path: str,
    *,
    addr: int = 0x00000000,
    size: int = FLASH_SIZE_DEFAULT,
) -> JLinkResult:
    """
    回读芯片 Flash 内容并保存为 .bin 文件。
    JFlash.exe CLI 不支持读回，使用 JLink.exe savebin 命令代替。
    JLink savebin 单次最大 64KB，超出需要分块。

    参数:
        chip_name: 芯片型号，如 "iND23226"（自研芯片用 "Cortex-M0"）
        output_path: 保存路径，如 test_results/read_20260409.bin
        addr: 起始地址（默认 0x00000000）
        size: 回读长度（字节，默认 64KB）
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    project_root = os.path.dirname(os.path.dirname(__file__))
    work_dir = os.path.join(project_root, "test_results")
    logger.info(f"[jlink] reading flash {chip_name} @ 0x{addr:08X}, size=0x{size:X} -> {output_path}")

    CHUNK = 0x10000  # 64KB，单次最大可读块
    all_data = []
    offset = 0
    remaining = size

    while remaining > 0:
        chunk_size = min(remaining, CHUNK)
        chunk_addr = addr + offset
        chunk_basename = f"_chunk_{offset:08x}.bin"
        chunk_path = os.path.join(work_dir, chunk_basename)

        script = [
            "device Cortex-M0",
            "speed 4000",
            "connect",
            "S",
            f"savebin {chunk_basename},{chunk_addr:#x},0x{chunk_size:X}",
            "exit",
        ]

        returncode, stdout, stderr = _run_jlink_script(
            script, timeout=120, cwd=work_dir
        )
        combined = stdout + stderr

        if returncode != 0:
            return JLinkResult(False, f"JLink 读取失败（code={returncode}）: {combined[:300]}", combined)

        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            with open(chunk_path, "rb") as f:
                all_data.append(f.read())
            os.unlink(chunk_path)
            read_total = sum(len(d) for d in all_data)
            logger.info(f"[jlink] chunk @ 0x{chunk_addr:08X} size=0x{chunk_size:X} OK, total={read_total}")
        else:
            if "Could not read memory" in combined:
                logger.warning(f"[jlink] chunk @ 0x{chunk_addr:08X} not readable, stopping")
                break
            return JLinkResult(False, f"块 @ 0x{chunk_addr:08X} 读取失败: {combined[:300]}", combined)

        offset += chunk_size
        remaining -= chunk_size

    if not all_data:
        return JLinkResult(False, "未读取到任何数据", "")

    with open(output_path, "wb") as f:
        for chunk in all_data:
            f.write(chunk)

    final_size = os.path.getsize(output_path)
    logger.info(f"[jlink] read complete: {final_size} bytes -> {output_path}")
    return JLinkResult(True, f"回读成功（{final_size} 字节）", "", output_path)


def list_chip_projects() -> list:
    """返回所有可用的芯片 .jflash 工程列表"""
    if not os.path.exists(PROJECT_DIR):
        return []
    return sorted([
        f.replace(".jflash", "")
        for f in os.listdir(PROJECT_DIR)
        if f.endswith(".jflash")
    ])
