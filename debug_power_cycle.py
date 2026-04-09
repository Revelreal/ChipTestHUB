#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ChipTestHub CLI 调试工具
用于在 CLI 环境下直接调用 power_cycle 相关函数进行调试

用法:
    python debug_power_cycle.py [--simulate]
    python debug_power_cycle.py [--regex "Cycle 2/10 ON (3/20)"]
    python debug_power_cycle.py [--parse-status "Cycle 2/10 ON (3/20)"]
"""
import re
import sys
import argparse

def parse_progress_message(msg: str):
    """
    模拟 task_manager 中的解析逻辑。
    从 set_progress 的消息中提取 cycle 和 ON/OFF 状态。
    """
    m = re.search(r"Cycle (\d+)/(\d+).*?(ON|OFF)", msg)
    if m:
        return {
            "cycle": int(m.group(1)),
            "total": int(m.group(2)),
            "status": m.group(3),
            "raw": m.group(0)
        }
    return None


def simulate_taskinfo_state(messages: list):
    """
    模拟 task_manager 中 TaskInfo 的状态变化过程。
    传入所有 set_progress 调用的消息列表，打印每一步的状态。
    """
    class MockTaskInfo:
        def __init__(self):
            self.current_cycle = None
            self.current_status = None
            self.progress = 0.0
            self.message = ""

    info = MockTaskInfo()
    print(f"{'Step':>4}  {'Cycle':>6}  {'Status':>6}  {'Message'}")
    print("-" * 60)
    for i, msg in enumerate(messages, 1):
        result = parse_progress_message(msg)
        if result:
            info.current_cycle = result["cycle"]
            info.current_status = result["status"]
        else:
            result = {"cycle": info.current_cycle, "status": info.current_status}
        info.progress = i / len(messages)
        info.message = msg
        marker = "✓" if result["status"] == get_expected_status(i) else "✗ MISMATCH"
        print(f"{i:>4}  {result['cycle'] or '-':>6}  {result['status'] or '-':>6}  {msg} {marker}")
    print()


def get_expected_status(step: int) -> str:
    """根据 step 判断应该是 ON 还是 OFF（1-based）"""
    return "ON" if step % 2 == 1 else "OFF"


def test_regex(message: str):
    """测试单条消息的正则解析"""
    print(f"输入消息: {repr(message)}")
    result = parse_progress_message(message)
    if result:
        print(f"  解析结果: cycle={result['cycle']}, total={result['total']}, status={result['status']}")
        print(f"  正则匹配段: {repr(result['raw'])}")
    else:
        print("  正则匹配失败！")
    print()


def interactive_debug():
    """交互式调试模式"""
    print("=" * 60)
    print("ChipTestHub Power Cycle 调试工具")
    print("=" * 60)
    print("命令:")
    print("  parse <消息>   - 解析单条 set_progress 消息")
    print("  status <step> - 查看指定 step 预期的 ON/OFF 状态")
    print("  simulate       - 运行完整的状态模拟")
    print("  trace          - 追踪所有 ON 状态的 step 序号")
    print("  quit           - 退出")
    print()

    history = []

    while True:
        try:
            line = input("debug> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break

        if not line:
            continue

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "quit":
            break
        elif cmd == "parse":
            if arg:
                test_regex(arg)
            else:
                print("用法: parse <消息>")
        elif cmd == "status":
            if arg.isdigit():
                step = int(arg)
                print(f"Step {step}: 预期 {get_expected_status(step)}")
            else:
                print("用法: status <step>")
        elif cmd == "simulate":
            # 生成完整的 10-cycle 测试消息
            messages = []
            total = 10
            total_steps = total * 2
            for cycle in range(1, total + 1):
                on_step = (cycle - 1) * 2 + 1
                off_step = on_step + 1
                messages.append(f"Cycle {cycle}/{total} ON ({on_step}/{total_steps})")
                messages.append(f"Cycle {cycle}/{total} OFF ({off_step}/{total_steps})")
            simulate_taskinfo_state(messages)
        elif cmd == "trace":
            # 追踪所有 ON 状态出现在哪些 step
            print("追踪 ON 状态出现的 step:")
            for step in range(1, 21):
                if get_expected_status(step) == "ON":
                    cycle = (step + 1) // 2
                    print(f"  Step {step:>2} -> Cycle {cycle} ON")
            print()
        elif cmd == "help":
            print("命令: parse, status, simulate, trace, help, quit")
        else:
            print(f"未知命令: {cmd}")


def main():
    parser = argparse.ArgumentParser(description="ChipTestHub 调试工具")
    parser.add_argument("--regex", metavar="MSG", help="测试正则解析单条消息")
    parser.add_argument("--simulate", action="store_true", help="运行完整状态模拟")
    parser.add_argument("--trace", action="store_true", help="追踪 ON/OFF 状态分布")
    args = parser.parse_args()

    if args.regex:
        test_regex(args.regex)
        return

    if args.simulate:
        messages = []
        total = 10
        total_steps = total * 2
        for cycle in range(1, total + 1):
            on_step = (cycle - 1) * 2 + 1
            off_step = on_step + 1
            messages.append(f"Cycle {cycle}/{total} ON ({on_step}/{total_steps})")
            messages.append(f"Cycle {cycle}/{total} OFF ({off_step}/{total_steps})")
        simulate_taskinfo_state(messages)
        return

    if args.trace:
        print("Step -> Expected Status:")
        for step in range(1, 21):
            print(f"  Step {step:>2}: {get_expected_status(step)}")
        print()
        print("ON 状态出现的 step:", [step for step in range(1, 21) if get_expected_status(step) == "ON"])
        print("OFF 状态出现的 step:", [step for step in range(1, 21) if get_expected_status(step) == "OFF"])
        return

    # 默认进入交互模式
    interactive_debug()


if __name__ == "__main__":
    main()
