# ChipTestHub CLI 调试工具

## 简介

`debug_power_cycle.py` 是一个独立运行的 CLI 调试工具，用于在**不启动 Web 服务**的情况下调试 power_cycle 的状态解析逻辑。

## 环境要求

- Python 3.8+
- 无需启动 Flask 服务
- 无需任何外部依赖（只用到 Python 内置 `re` 模块）

## 使用方法

### 交互式调试模式（默认）

```bash
cd C:/Users/public.DESKTOP-1D39QRK/Desktop/Docs/chip_test_hub芯片测试站
python debug_power_cycle.py
```

进入交互式界面后，可使用以下命令：

| 命令 | 说明 |
|------|------|
| `simulate` | 运行完整的 10-cycle 状态模拟，验证每一步的 ON/OFF |
| `trace` | 显示所有 step 对应的 ON/OFF 预期状态 |
| `parse <消息>` | 解析单条 set_progress 消息 |
| `status <step>` | 查看指定 step 预期的 ON/OFF |
| `help` | 显示帮助 |
| `quit` | 退出 |

### 非交互模式

```bash
# 追踪 ON/OFF 状态分布
python debug_power_cycle.py --trace

# 运行完整状态模拟
python debug_power_cycle.py --simulate

# 测试单条消息解析
python debug_power_cycle.py --regex "Cycle 2/10 ON (3/20)"
```

## 常用调试流程

### 1. 验证正则解析是否正确

```bash
$ python debug_power_cycle.py
debug> simulate
  Step   Cycle  Status  Message
  ------------------------------------------------------------
     1       1      ON  Cycle 1/10 ON (1/20) ✓
     2       1     OFF  Cycle 1/10 OFF (2/20) ✓
     3       2      ON  Cycle 2/10 ON (3/20) ✓   ← 验证 cycle 2 ON
     4       2     OFF  Cycle 2/10 OFF (4/20) ✓
  ...
```

### 2. 验证特定消息解析

```bash
debug> parse Cycle 2/10 ON (3/20)
输入消息: 'Cycle 2/10 ON (3/20)'
  解析结果: cycle=2, total=10, status=ON
  正则匹配段: 'Cycle 2/10 ON'

debug> parse Cycle 2/10 OFF (4/20)
输入消息: 'Cycle 2/10 OFF (4/20)'
  解析结果: cycle=2, total=10, status=OFF
```

### 3. 追踪 step 与 ON/OFF 的对应关系

```bash
debug> trace
追踪 ON 状态出现的 step:
  Step  3 -> Cycle 2 ON
  Step  5 -> Cycle 3 ON
  ...
```

## 如果模拟结果正确但线上仍有问题

说明问题不在解析逻辑本身，可能原因：

1. **服务器未重启** — 修改代码后需要重启 Flask 服务（Ctrl+C → 重新 `python app.py`）
2. **浏览器缓存** — 需要强刷浏览器 Ctrl+Shift+R
3. **HTTP 响应顺序问题** — 可以加 DEBUG 日志查看服务器收到的请求顺序
4. **多浏览器 Tab** — 不同 Tab 的 Socket.IO 或轮询互相干扰

## DEBUG 日志

如需查看服务器的运行时日志，Flask 日志文件位于：

```
C:/Users/public.DESKTOP-1D39QRK/Desktop/Docs/chip_test_hub芯片测试站/logs/hub_YYYYMMDD.log
```

其中 `[task_manager]` 行会显示 progress 回调的详细调用：

```
[TASK xxxxx] power_cycle runner started with payload: {...}
[power_cycle] Cycle 2/10 ON (3/20)  ← set_progress 收到的消息
```

如发现 step 3 的消息中状态是 OFF，说明 service 代码与预期不符，需检查 `services/power_cycle.py` 中的 `set_progress` 调用位置。
