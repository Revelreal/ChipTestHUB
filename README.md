# ChipTestHUB 芯片测试站

一款面向芯片研发场景的自动化测试平台，支持 ITECH 电源控制、上下电耐受测试、J-Link 固件烧录与 Flash 回读校验。

---

## 功能模块

### 上下电耐受测试
- 通过 VISA 接口控制 ITECH IT6322A 电源
- 可配置目标电压、循环次数、开启/关闭时长
- 实时显示当前周期、电压值、测试状态
- 测试数据自动保存为 CSV

### J-Link 固件烧录（可选）
- JFlash CLI 驱动烧录，支持主流 J-Link 型号
- 烧录固件 (.bin)，支持烧录后自动校验
- 自动检测 J-Link 连接状态

### Flash 回读与 BIN 对比（可选）
- JLink savebin 分块读取 Flash（最大 64KB/次）
- Beyond Compare 风格十六进制对比视图
- 差异字节红色高亮，支持下载差异 CSV 报告

---

## 技术栈

- **后端**：Flask + Flask-SocketIO
- **前端**：原生 HTML/CSS/JS，Swiss Design 风格
- **仪器驱动**：PyVISA（IT6322A 电源）
- **固件工具**：SEGGER JFlash / JLink CLI

---

## 项目结构

```
chip_test_hub芯片测试站/
├── app.py                      # Flask 入口
├── config.py                   # 配置文件
├── routes/                     # 路由层
│   ├── test_routes.py          # 测试 API（J-Link、烧录、对比）
│   ├── main_routes.py          # 页面路由
│   └── settings_routes.py      # 设置 API
├── services/                   # 业务逻辑层
│   ├── jlink_service.py        # J-Link 封装
│   ├── power_cycle.py          # 上下电测试逻辑
│   ├── bin_compare.py          # BIN 对比引擎
│   └── voltage_scan.py         # 电压扫描
├── templates/                  # HTML 模板
│   ├── power_cycle.html        # 上下电测试页面
│   └── ...
├── static/                     # 静态资源
├── utils/                      # 工具函数
└── jlink_tools/                # J-Link 工具（可选）
```

---

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

推荐使用 Python 3.10+，已在 Windows 环境下测试。

### 2. 配置 J-Link 驱动（可选）

烧录/回读功能需要安装 SEGGER J-Link 软件（V7.98h 或更高）：

- 安装路径：`C:\Program Files (x86)\SEGGER\JLink_V798h\`
- 软件包含 JFlash.exe（烧录）和 JLink.exe（脚本）两个工具

### 3. 启动服务

```bash
python app.py
# 或双击
start.bat
```

服务启动后访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)

### 4. 连接 ITECH 电源

通过 USB 连接 IT6322A 电源，点击刷新按钮加载 VISA 资源地址。

---

## 主要依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| Flask | ≥2.0 | Web 框架 |
| Flask-SocketIO | ≥5.0 | 实时日志推送 |
| Flask-CORS | ≥4.0 | 跨域支持 |
| pyvisa | ≥1.13 | VISA 仪器控制 |
| pyvisa-py | ≥0.7 | VISA 后端实现 |

---

## 注意事项

- 上下电测试功能独立运行，不依赖 J-Link 模块
- J-Link 相关功能为**可选模块**，不安装不影响主测试流程
- Flash 回读最大单次 64KB，超出自动分块读取
- 芯片 iND23226 使用 `Cortex-M0` 作为 JLink 设备名称
