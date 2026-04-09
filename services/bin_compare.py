# -*- coding: utf-8 -*-
"""
BIN / Flash 内容对比服务
对比上下电前后的 Flash 读回数据，高亮差异地址。
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import BinaryIO
from typing.io import IO


@dataclass
class DiffEntry:
    addr: int
    before: int  # 0-255 byte value before
    after: int   # 0-255 byte value after
    diff: int    # after - before


@dataclass
class CompareResult:
    identical: bool
    total_bytes: int
    diff_count: int
    diff_entries: list  # list of DiffEntry
    csv_path: str       # 详细差异报告路径


def _read_chunk(f: BinaryIO, size: int) -> bytes:
    """读取指定字节数，不足则返回实际读取量"""
    data = f.read(size)
    return data


def compare_bin_files(
    file_before: str,
    file_after: str,
    output_csv: str,
) -> CompareResult:
    """
    比较两个 .bin 文件，输出差异报告。

    返回 CompareResult，其中：
      - identical: True 表示完全相同
      - diff_count: 不同字节数量
      - diff_entries: [DiffEntry, ...] 差异列表
      - csv_path: 详细 CSV 报告路径
    """
    if not os.path.exists(file_before):
        raise FileNotFoundError(f"参考文件不存在: {file_before}")
    if not os.path.exists(file_after):
        raise FileNotFoundError(f"对比文件不存在: {file_after}")

    size_before = os.path.getsize(file_before)
    size_after = os.path.getsize(file_after)
    total_bytes = max(size_before, size_after)

    diff_entries: list = []

    with open(file_before, "rb") as fa, open(file_after, "rb") as fb:
        offset = 0
        while True:
            chunk_a = fa.read(8192)
            chunk_b = fb.read(8192)

            if not chunk_a and not chunk_b:
                break

            min_len = min(len(chunk_a), len(chunk_b))
            for i in range(min_len):
                if chunk_a[i] != chunk_b[i]:
                    addr = offset + i
                    diff_entries.append(DiffEntry(
                        addr=addr,
                        before=chunk_a[i],
                        after=chunk_b[i],
                        diff=chunk_b[i] - chunk_a[i],
                    ))

            offset += min_len

            # 文件长度不同，多出的部分也算差异
            if len(chunk_a) != len(chunk_b):
                longer = chunk_a if len(chunk_a) > len(chunk_b) else chunk_b
                for i in range(min_len, len(longer)):
                    addr = offset + i - (len(chunk_a) if len(chunk_a) > len(chunk_b) else 0)
                    after_val = chunk_b[i] if i < len(chunk_b) else 0
                    before_val = chunk_a[i] if i < len(chunk_a) else 0
                    diff_entries.append(DiffEntry(
                        addr=addr,
                        before=before_val,
                        after=after_val,
                        diff=after_val - before_val,
                    ))

    identical = len(diff_entries) == 0

    # 写入 CSV 报告
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["地址(hex)", "地址(dec)", "变化前", "变化后", "差值", "变化字节数"])
        for d in diff_entries:
            w.writerow([
                f"0x{d.addr:08X}",
                d.addr,
                f"0x{d.before:02X} ({d.before})",
                f"0x{d.after:02X} ({d.after})",
                f"+{d.diff}" if d.diff >= 0 else str(d.diff),
                abs(d.diff),
            ])
        if not diff_entries:
            w.writerow(["（两文件完全相同，无差异）"])

    return CompareResult(
        identical=identical,
        total_bytes=total_bytes,
        diff_count=len(diff_entries),
        diff_entries=diff_entries,
        csv_path=output_csv,
    )
