(() => {
  const logBox = document.getElementById("logBox");
  const themeToggle = document.getElementById("themeToggle");
  const themeToggleText = document.getElementById("themeToggleText");

  const voltageStartBtn = document.getElementById("voltageStartBtn");
  const voltageStopBtn = document.getElementById("voltageStopBtn");
  const voltageProgressFill = document.getElementById("voltageProgressFill");
  const voltageProgressText = document.getElementById("voltageProgressText");
  const gatewayPortSelect = document.getElementById("gatewayPort");
  const powerAddressSelect = document.getElementById("powerAddress");
  const refreshPortsBtn = document.getElementById("refreshPortsBtn");

  let currentVoltageTaskId = null;
  let isVoltageScanRunning = false;

  async function loadDevices() {
    try {
      const [portsResp, visaResp] = await Promise.all([
        fetch("/test/ports").then(r => r.json().catch(() => ({success: false, ports: []}))),
        fetch("/test/visa").then(r => r.json().catch(() => ({success: false, devices: []}))),
      ]);

      if (gatewayPortSelect) {
        gatewayPortSelect.innerHTML = "";
        const defaultOpt = document.createElement("option");
        defaultOpt.value = "";
        defaultOpt.textContent = "-- 选择串口 --";
        gatewayPortSelect.appendChild(defaultOpt);

        if (portsResp.success && portsResp.ports?.length > 0) {
          for (const p of portsResp.ports) {
            const opt = document.createElement("option");
            opt.value = p.port;
            opt.textContent = `${p.port} - ${p.description || p.name || "未知设备"}`;
            gatewayPortSelect.appendChild(opt);
          }
        } else {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "未找到串口设备";
          gatewayPortSelect.appendChild(opt);
        }
      }

      if (powerAddressSelect) {
        powerAddressSelect.innerHTML = "";
        const defaultOpt = document.createElement("option");
        defaultOpt.value = "";
        defaultOpt.textContent = "-- 选择电源 --";
        powerAddressSelect.appendChild(defaultOpt);

        if (visaResp.success && visaResp.devices?.length > 0) {
          for (const d of visaResp.devices) {
            const opt = document.createElement("option");
            opt.value = d.resource;
            opt.textContent = d.resource;
            powerAddressSelect.appendChild(opt);
          }
        } else {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "未找到 VISA 设备";
          powerAddressSelect.appendChild(opt);
        }
      }

      addLog(`[INFO] 已加载 ${portsResp.ports?.length || 0} 个串口, ${visaResp.devices?.length || 0} 个 VISA 设备`);
    } catch (e) {
      addLog(`[ERROR] 加载设备列表失败: ${e?.message || e}`);
    }
  }

  function getTheme() {
    const attr = document.documentElement.getAttribute("data-theme");
    return attr === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("chip_test_hub_theme", next);
    } catch (e) {
      // ignore
    }
    if (themeToggle) themeToggle.setAttribute("aria-pressed", String(next === "dark"));
    if (themeToggleText) themeToggleText.textContent = next === "dark" ? "Dark" : "Light";
  }

  function addLog(line) {
    if (!logBox) return;
    const div = document.createElement("div");
    div.className = "log-line";
    div.textContent = line;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
   }

  let voltageAutoStopTimer = null;
  let voltageAutoStopStarted = false;
  const VOLTAGE_AUTO_STOP_DELAY = 2000;

  function startVoltageAutoStopTimer() {
    if (voltageAutoStopStarted) {
      if (voltageAutoStopTimer) {
        clearTimeout(voltageAutoStopTimer);
      }
    }
    
    if (isVoltageScanRunning && currentVoltageTaskId) {
      voltageAutoStopStarted = true;
      voltageAutoStopTimer = setTimeout(async () => {
        const taskIdToStop = currentVoltageTaskId;
        currentVoltageTaskId = null;
        isVoltageScanRunning = false;
        voltageAutoStopStarted = false;
        if (taskIdToStop) {
          addLog("[WARN] 2秒内无新数据，自动停止测试...");
          try {
            await postJson("/test/voltage/stop", { task_id: taskIdToStop });
            addLog("[INFO] 自动停止完成");
          } catch (e) {
            addLog(`[ERROR] 自动停止失败: ${e?.message || e}`);
          } finally {
            voltageAutoStopTimer = null;
          }
        }
      }, VOLTAGE_AUTO_STOP_DELAY);
    }
  }

  function resetVoltageAutoStopTimer() {
    if (voltageAutoStopTimer) {
      clearTimeout(voltageAutoStopTimer);
    }
    startVoltageAutoStopTimer();
  }

  async function postJson(url, data) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
    });
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok || json.success === false) {
      const msg = json.message || `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    return json;
  }

  function setVoltageProgress(p, msg) {
    const pct = Math.max(0, Math.min(100, Math.round(p * 100)));
    if (voltageProgressFill) voltageProgressFill.style.width = `${pct}%`;
    if (voltageProgressText) voltageProgressText.textContent = msg || `${pct}%`;
  }

  window.addEventListener("DOMContentLoaded", () => {
    if (themeToggle) {
      setTheme(getTheme());
      themeToggle.addEventListener("click", () => {
        setTheme(getTheme() === "dark" ? "light" : "dark");
      });
    }

    loadDevices();

    if (typeof io !== "function") {
      addLog("[WARN] Socket.IO 客户端未加载，请刷新页面重试");
      console.warn("Socket.IO not loaded");
      return;
    }

    const socket = io();
    console.log("Socket.IO initialized");

    socket.on("connect", () => {
      addLog("[INFO] ✓ Socket.IO 日志连接已建立");
      console.log("Socket.IO connected, id:", socket.id);
    });
    socket.on("disconnect", () => {
      addLog("[WARN] ✗ Socket.IO 日志连接已断开");
      console.log("Socket.IO disconnected");
    });
    socket.on("connect_error", (err) => {
      addLog("[ERROR] Socket.IO 连接错误: " + (err?.message || err));
      console.error("Socket.IO connect_error:", err);
    });
    socket.on("error", (err) => {
      addLog("[ERROR] Socket.IO 错误: " + (err?.message || err));
      console.error("Socket.IO error:", err);
    });

    socket.on("log_message", (data) => {
      console.log("Received log_message:", data);
      if (!data?.message) return;
      const line = `[${data?.timestamp || "--:--:--"}] ${data?.test_type || "hub"} ${data?.message || ""}`.trim();
      addLog(line);
    });

    if (voltageStartBtn) {
      voltageStartBtn.addEventListener("click", async () => {
        try {
          voltageStartBtn.disabled = true;

          const gatewayPort = document.getElementById("gatewayPort")?.value || "";
          const powerAddress = document.getElementById("powerAddress")?.value || "";

          console.log("[DEBUG] ====== 前端发送的数据 ======");
          console.log("[DEBUG] gatewayPort:", gatewayPort);
          console.log("[DEBUG] powerAddress:", powerAddress);

          const payload = {
            voltage_min: Number(document.getElementById("voltageMin")?.value || 8),
            voltage_max: Number(document.getElementById("voltageMax")?.value || 19),
            voltage_step: Number(document.getElementById("voltageStep")?.value || 1),
            repeat_count: Number(document.getElementById("repeatCount")?.value || 20),
            device_num: Number(document.getElementById("deviceNum")?.value || 1),
            nad_start: Number(document.getElementById("nadStart")?.value || 1),
            power_mode: "auto",
            gateway_port: gatewayPort,
            gateway_baudrate: 115200,
            power_address: powerAddress,
          };

          setVoltageProgress(0, "Starting...");
          const json = await postJson("/test/voltage/start", payload);
          currentVoltageTaskId = json?.task?.task_id || null;
          isVoltageScanRunning = !!currentVoltageTaskId;
          voltageAutoStopStarted = false;
          addLog(`[INFO] voltage_scan started task_id=${currentVoltageTaskId}`);
          if (voltageStopBtn) voltageStopBtn.disabled = !currentVoltageTaskId;
        } catch (e) {
          addLog(`[ERROR] start failed: ${e?.message || e}`);
          setVoltageProgress(0, "Idle");
          isVoltageScanRunning = false;
        } finally {
          voltageStartBtn.disabled = false;
        }
      });
    }

    if (refreshPortsBtn) {
      refreshPortsBtn.addEventListener("click", () => {
        addLog("[INFO] 正在刷新设备列表...");
        loadDevices();
      });
    }

    if (voltageStopBtn) {
      voltageStopBtn.addEventListener("click", async () => {
        if (!currentVoltageTaskId) return;
        try {
          voltageStopBtn.disabled = true;
          if (voltageAutoStopTimer) {
            clearTimeout(voltageAutoStopTimer);
            voltageAutoStopTimer = null;
          }
          isVoltageScanRunning = false;
          voltageAutoStopStarted = false;
          await postJson("/test/voltage/stop", { task_id: currentVoltageTaskId });
          addLog(`[INFO] stop requested task_id=${currentVoltageTaskId}`);
        } catch (e) {
          addLog(`[ERROR] stop failed: ${e?.message || e}`);
        } finally {
          voltageStopBtn.disabled = false;
        }
      });
    }

    const nadScanBtn = document.getElementById("nadScanBtn");
    const scanResult = document.getElementById("scanResult");
    const scanGatewayPort = document.getElementById("scanGatewayPort");
    const refreshScanPortsBtn = document.getElementById("refreshScanPortsBtn");

    function loadScanPorts() {
      fetch("/test/ports")
        .then(r => r.json())
        .then(data => {
          if (scanGatewayPort) {
            scanGatewayPort.innerHTML = "";
            const defaultOpt = document.createElement("option");
            defaultOpt.value = "";
            defaultOpt.textContent = "-- 选择串口 --";
            scanGatewayPort.appendChild(defaultOpt);

            if (data.success && data.ports?.length > 0) {
              for (const p of data.ports) {
                const opt = document.createElement("option");
                opt.value = p.port;
                opt.textContent = `${p.port} - ${p.description || p.name || "未知设备"}`;
                scanGatewayPort.appendChild(opt);
              }
            }
          }
        })
        .catch(() => {});
    }

    if (refreshScanPortsBtn) {
      refreshScanPortsBtn.addEventListener("click", () => {
        loadScanPorts();
      });
    }

    const quickSetBtn = document.getElementById("quickSetBtn");
    const setGatewayPort = document.getElementById("setGatewayPort");
    const setPowerAddress = document.getElementById("setPowerAddress");

    function loadSetPorts() {
      fetch("/test/ports")
        .then(r => r.json())
        .then(data => {
          if (setGatewayPort) {
            setGatewayPort.innerHTML = "";
            const defaultOpt = document.createElement("option");
            defaultOpt.value = "";
            defaultOpt.textContent = "-- 选择串口 --";
            setGatewayPort.appendChild(defaultOpt);

            if (data.success && data.ports?.length > 0) {
              for (const p of data.ports) {
                const opt = document.createElement("option");
                opt.value = p.port;
                opt.textContent = p.port + " - " + (p.description || p.name || "未知设备");
                setGatewayPort.appendChild(opt);
              }
            }
          }
        })
        .catch(() => {});

      fetch("/test/visa")
        .then(r => r.json())
        .then(data => {
          if (setPowerAddress) {
            setPowerAddress.innerHTML = "";
            const defaultOpt = document.createElement("option");
            defaultOpt.value = "";
            defaultOpt.textContent = "-- 选择电源 --";
            setPowerAddress.appendChild(defaultOpt);

            if (data.success && data.devices?.length > 0) {
              for (const d of data.devices) {
                const opt = document.createElement("option");
                opt.value = d.resource;
                opt.textContent = d.resource;
                setPowerAddress.appendChild(opt);
              }
            }
          }
        })
        .catch(() => {});
    }

    if (quickSetBtn) {
      quickSetBtn.addEventListener("click", async () => {
        const port = setGatewayPort?.value;
        const power = setPowerAddress?.value;
        const voltage = parseFloat(document.getElementById("setVoltage")?.value);
        const nad = parseInt(document.getElementById("setNad")?.value || 1);

        if (!port) {
          addLog("[ERROR] 请选择串口 (LIN网关)");
          alert("请选择串口");
          return;
        }
        if (!power) {
          addLog("[ERROR] 请选择电源设备 (VISA)");
          alert("请选择电源设备");
          return;
        }
        if (isNaN(voltage) || voltage < 0 || voltage > 24) {
          addLog("[ERROR] 电压值无效 (0-24V)");
          alert("请输入有效的电压值 (0-24V)");
          return;
        }

        quickSetBtn.disabled = true;
        addLog("[INFO] 开始设置电压: " + voltage + "V (NAD=" + nad + ")");

        try {
          const json = await postJson("/test/voltage-set/start", {
            voltage: voltage,
            nad: nad,
            repeat_count: 1,
            gateway_port: port,
            power_address: power,
          });
          addLog("[INFO] voltage_set started, task_id=" + (json?.task?.task_id || "unknown"));
        } catch (e) {
          addLog("[ERROR] 启动失败: " + (e?.message || e));
          quickSetBtn.disabled = false;
        }
      });
    }

    loadSetPorts();

    if (nadScanBtn && scanResult) {
      nadScanBtn.addEventListener("click", async () => {
        const port = scanGatewayPort?.value;
        if (!port) {
          scanResult.innerHTML = '<span class="device-not-found">请选择串口</span>';
          return;
        }

        const nadStart = parseInt(document.getElementById("nadStartScan")?.value || 1);
        const nadEnd = parseInt(document.getElementById("nadEndScan")?.value || 15);

        nadScanBtn.disabled = true;
        nadScanBtn.textContent = "扫描中...";
        scanResult.innerHTML = '<span class="hint-text">正在扫描...</span>';

        try {
          const resp = await postJson("/test/nad/scan", {
            gateway_port: port,
            gateway_baudrate: 115200,
            nad_start: nadStart,
            nad_end: nadEnd
          });

          if (resp.success) {
            if (resp.found_devices && resp.found_devices.length > 0) {
              let html = "";
              for (const dev of resp.found_devices) {
                const vbatV = (dev.vbat / 1000).toFixed(2);
                html += `
                  <div class="device-item">
                    <div class="device-header">
                      <span class="device-nad">NAD=${dev.nad}</span>
                      <span class="device-status">✓ 在线</span>
                    </div>
                    <div class="device-details">
                      <span>VBAT: ${vbatV}V</span>
                      <span>Temp: ${dev.temp}°C</span>
                      <span>LED: ${dev.led_index}</span>
                    </div>
                  </div>
                `;
              }
              scanResult.innerHTML = html;
            } else {
              scanResult.innerHTML = '<span class="device-not-found">未找到任何设备</span>';
            }
          } else {
            scanResult.innerHTML = `<span class="device-not-found">错误: ${resp.message}</span>`;
          }
        } catch (e) {
          scanResult.innerHTML = `<span class="device-not-found">扫描失败: ${e?.message || e}</span>`;
        } finally {
          nadScanBtn.disabled = false;
          nadScanBtn.textContent = "开始扫描";
        }
      });
    }

    loadScanPorts();

    const openResultsFolderBtn = document.getElementById("openResultsFolderBtn");
    const clearLogBtn = document.getElementById("clearLogBtn");
    const latestVoltageResult = document.getElementById("latestVoltageResult");
    const noResultHint = document.getElementById("noResultHint");
    const resultTitle = document.getElementById("resultTitle");
    const resultTime = document.getElementById("resultTime");
    const resultPath = document.getElementById("resultPath");
    const downloadResultBtn = document.getElementById("downloadResultBtn");
    const copyPathBtn = document.getElementById("copyPathBtn");
    const resultFilesList = document.getElementById("resultFilesList");
    const loadingFilesHint = document.getElementById("loadingFilesHint");

    let currentResultPath = null;
    let currentResultType = "scan";

    async function loadResultFiles() {
       if (!resultFilesList) return;
       try {
         const resp = await fetch("/test/results/");
         const json = await resp.json();
         if (json.success && json.files && json.files.length > 0) {
           const filteredFiles = json.files.filter(function(f) {
             const name = f.name || "";
             if (currentResultType === "scan") {
               return name.startsWith("voltage_scan_");
             } else {
               return name.startsWith("voltage_set_");
             }
           }).slice(0, 10);

           if (filteredFiles.length > 0) {
             if (loadingFilesHint) loadingFilesHint.style.display = "none";
             resultFilesList.innerHTML = filteredFiles.map(function(f) {
               return '<div class="result-file-item" data-filename="' + f.name + '">' +
                 '<span class="result-file-name">' + f.name + '</span>' +
                 '<span class="result-file-time">' + f.modified + '</span>' +
               '</div>';
             }).join("");
             resultFilesList.querySelectorAll(".result-file-item").forEach(function(item) {
               item.addEventListener("click", function() {
                 const filename = this.getAttribute("data-filename");
                 if (filename) {
                   window.location.href = "/voltage/results?file=" + encodeURIComponent(filename);
                 }
               });
             });
           } else {
             if (loadingFilesHint) {
               loadingFilesHint.style.display = "block";
               loadingFilesHint.textContent = currentResultType === "scan" ? "暂无扫描结果" : "暂无设置结果";
             }
           }
         } else {
           if (loadingFilesHint) loadingFilesHint.textContent = "暂无测试结果";
         }
       } catch (e) {
         console.error("加载结果文件失败:", e);
         if (loadingFilesHint) loadingFilesHint.textContent = "加载失败";
       }
     }

    document.querySelectorAll(".result-tab").forEach(function(tab) {
      tab.addEventListener("click", function() {
        document.querySelectorAll(".result-tab").forEach(function(t) { t.classList.remove("active"); });
        this.classList.add("active");
        currentResultType = this.getAttribute("data-type");
        loadResultFiles();
        if (resultTitle) {
          resultTitle.textContent = currentResultType === "scan" ? "电压扫描测试" : "电压设置测试";
        }
      });
    });

    loadResultFiles();

    if (openResultsFolderBtn) {
      openResultsFolderBtn.addEventListener("click", async function() {
        try {
          await postJson("/test/results/open-folder", {});
        } catch (e) {
          addLog("[ERROR] 打开文件夹失败: " + (e?.message || e));
        }
      });
    }

    if (clearLogBtn) {
      clearLogBtn.addEventListener("click", () => {
        if (logBox) {
          logBox.innerHTML = '<div class="log-line">日志已清空</div>';
        }
      });
    }

    if (downloadResultBtn) {
      downloadResultBtn.addEventListener("click", () => {
        if (currentResultPath) {
          window.open(`/test/results/${encodeURIComponent(currentResultPath)}`, "_blank");
        }
      });
    }

    if (copyPathBtn) {
      copyPathBtn.addEventListener("click", () => {
        if (currentResultPath) {
          navigator.clipboard.writeText(currentResultPath).then(() => {
            addLog("[INFO] 路径已复制到剪贴板");
          });
        }
      });
    }

    function showVoltageResult(filename, timestamp, fullPath) {
      currentResultPath = filename;
      if (latestVoltageResult) {
        latestVoltageResult.style.display = "block";
      }
      if (noResultHint) {
        noResultHint.style.display = "none";
      }
      if (resultTime) {
        resultTime.textContent = timestamp || "";
      }
      if (resultPath) {
        resultPath.textContent = fullPath || "";
      }
      if (downloadResultBtn) {
        downloadResultBtn.onclick = () => {
          window.open(`/test/results/${encodeURIComponent(filename)}`, "_blank");
        };
      }
      if (voltageStartBtn) voltageStartBtn.disabled = false;
      if (voltageStopBtn) voltageStopBtn.disabled = true;
      loadResultFiles();
    }

    if (socket && typeof socket.on === "function") {
      socket.on("test_progress", (data) => {
        console.log("Received test_progress:", data);
        if (data?.test_type !== "voltage_scan") return;
        
        if (isVoltageScanRunning) {
          resetVoltageAutoStopTimer();
        }
        
        const progress = Number(data?.progress || 0);
        const msg = data?.message || "Running";
        setVoltageProgress(progress, msg);
        if (progress >= 1.0) {
          if (voltageStartBtn) voltageStartBtn.disabled = false;
          if (voltageStopBtn) voltageStopBtn.disabled = true;
          if (voltageAutoStopTimer) {
            clearTimeout(voltageAutoStopTimer);
            voltageAutoStopTimer = null;
          }
          isVoltageScanRunning = false;
          voltageAutoStopStarted = false;
        }

        if (data?.test_type === "voltage_set" && quickSetBtn) {
          quickSetBtn.disabled = false;
        }
      });

      socket.on("test_completed", (data) => {
        console.log("Received test_completed:", data);
        addLog(`[INFO] 测试完成! 结果文件: ${data?.filename}`);
        setVoltageProgress(1.0, "Completed");
        if (data?.filename) {
          showVoltageResult(data.filename, data?.timestamp, data?.result_path);
        }
        loadResultFiles();

        if (voltageAutoStopTimer) {
          clearTimeout(voltageAutoStopTimer);
          voltageAutoStopTimer = null;
        }

        if (data?.test_type === "voltage_scan") {
          isVoltageScanRunning = false;
          voltageAutoStopStarted = false;
        }

        if (data?.test_type === "voltage_set" && quickSetBtn) {
          quickSetBtn.disabled = false;
        }
      });
    }
  });
})();

