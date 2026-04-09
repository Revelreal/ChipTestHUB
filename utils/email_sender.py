# -*- coding: utf-8 -*-

import csv
import io
import logging
import smtplib
import time
from datetime import datetime
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger("email_sender")


def generate_chart_images(csv_path: str, nad_list: List[int]) -> dict:
    """
    从 CSV 生成每个 NAD 的温度折线图（聚合版本）。

    图表逻辑：
      - X 轴：目标温度点（target_temp），各温度点的 10 次读取取平均值
      - Y 轴：芯片平均温度
      - 每 NAD 一张子图，含芯片温度曲线 + 温箱设定温度曲线
    返回 {nad: png_bytes} 字典。失败时返回空字典。
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        logger.warning(f"[邮件] matplotlib 不可用，跳过图表生成: {e}")
        return {}

    try:
        from collections import defaultdict

        rows = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return {}

        # 1. 按 (nad, target_temp) 分组，累计温度和与计数
        chip_sum = defaultdict(float)   # (nad, target_temp) -> sum
        chip_cnt = defaultdict(int)    # (nad, target_temp) -> count
        chamber_by_target = {}          # target_temp -> [chamber_temp values]

        for row in rows:
            try:
                nad = int(row.get("nad", 0))
                target = float(row.get("target_temp", 0))
                chip = float(row.get("chiptemp", ""))
                chamber = row.get("chamber_temp", "")
            except (ValueError, TypeError):
                continue

            if chip and chip != "None" and str(chip) != "":
                chip_sum[(nad, target)] += chip
                chip_cnt[(nad, target)] += 1

            if chamber not in ("", "None") and str(chamber) != "":
                try:
                    if target not in chamber_by_target:
                        chamber_by_target[target] = []
                    chamber_by_target[target].append(float(chamber))
                except (ValueError, TypeError):
                    pass

        # 2. 计算每个 target_temp 的温箱平均温度
        chamber_avg = {
            t: sum(vals) / len(vals)
            for t, vals in chamber_by_target.items()
        }

        # 3. 生成每个 NAD 的图表
        charts = {}
        for nad in nad_list:
            # 收集该 NAD 的所有 (target, avg_chip_temp)
            points = []
            for (n, t), cnt in chip_cnt.items():
                if n == nad and cnt > 0:
                    avg_chip = chip_sum[(n, t)] / cnt
                    points.append((t, avg_chip))

            if not points:
                continue

            # 按温度排序
            points.sort(key=lambda x: x[0])
            temps = [p[0] for p in points]
            chip_avgs = [p[1] for p in points]
            chamber_avgs = [chamber_avg.get(t, None) for t in temps]

            # 绘图
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.plot(temps, chip_avgs,
                    marker="o", markersize=5,
                    label="芯片平均温度 (°C)",
                    color="#00d2ff", linewidth=2)
            ax.plot(temps, chamber_avgs,
                    marker="x", markersize=5,
                    label="温箱温度 (°C)",
                    color="#ff6b6b", linewidth=2, linestyle="--")

            ax.set_title(f"NAD={nad} 温度特性曲线", fontsize=13)
            ax.set_xlabel("目标温度 (°C)")
            ax.set_ylabel("芯片温度 (°C)")
            ax.legend(loc="best")
            ax.grid(True, alpha=0.3)

            # 标注温度点数量
            ax.set_title(f"NAD={nad} 温度特性曲线  ({len(temps)}个温度点)", fontsize=13)

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=130)
            plt.close()
            buf.seek(0)
            charts[nad] = buf.getvalue()

        return charts
    except Exception as e:
        logger.warning(f"[邮件] 生成图表失败: {e}")
        return {}

def build_html_report(csv_path: str, nad_list: List[int]) -> str:
    """生成 HTML 报告正文。"""
    try:
        rows = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return "<p>无数据记录。</p>"

        # 统计每个 NAD 的温度
        stats = {}
        for nad in nad_list:
            temps = []
            for row in rows:
                if str(row.get("nad", "")) == str(nad):
                    t = row.get("chiptemp", "")
                    try:
                        if t not in ("", "None"):
                            temps.append(float(t))
                    except (ValueError, TypeError):
                        pass
            if temps:
                stats[nad] = {
                    "min": min(temps),
                    "max": max(temps),
                    "avg": sum(temps) / len(temps),
                    "count": len(temps),
                }

        # 生成温箱温度范围
        chamber_temps = []
        for row in rows:
            t = row.get("chamber_temp", "")
            try:
                if t not in ("", "None"):
                    chamber_temps.append(float(t))
            except (ValueError, TypeError):
                pass
        chamber_range = f"{min(chamber_temps):.1f}°C ~ {max(chamber_temps):.1f}°C" if chamber_temps else "N/A"

        html = f"""
        <h2>温度扫描测试报告</h2>
        <p><b>生成时间：</b>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><b>温度范围：</b>{chamber_range}</p>
        <p><b>设备数量：</b>{len(nad_list)} (NAD={', '.join(str(n) for n in nad_list)})</p>
        <p><b>记录条数：</b>{len(rows)}</p>
        <hr/>
        <h3>芯片温度统计</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
          <tr bgcolor="#d4a72c">
            <th>NAD</th><th>最小值</th><th>最大值</th><th>平均值</th><th>采样次数</th>
          </tr>
        """
        for nad, st in stats.items():
            html += f"""
          <tr>
            <td align="center">{nad}</td>
            <td align="center">{st['min']:.1f}°C</td>
            <td align="center">{st['max']:.1f}°C</td>
            <td align="center">{st['avg']:.1f}°C</td>
            <td align="center">{st['count']}</td>
          </tr>"""
        html += "</table>"
        return html
    except Exception as e:
        logger.warning(f"[邮件] 生成HTML报告失败: {e}")
        return f"<p>报告生成失败: {e}</p>"


def send_result_email(
    csv_path: str,
    nad_list: List[int],
    *,
    to_email: str,
    smtp_host: str,
    smtp_port: int,
    from_email: str,
    api_key: str,
) -> tuple:
    """
    发送测试结果邮件，包含 CSV 附件、HTML 报告和图表。
    返回 (success, message)。
    """
    logger.info(f"[邮件] 开始发送邮件 to={to_email} csv={csv_path}")

    try:
        charts = generate_chart_images(csv_path, nad_list)
        html_body = build_html_report(csv_path, nad_list)

        msg = MIMEMultipart("mixed")
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = Header(
            f"温度扫描报告 {datetime.now().strftime('%Y%m%d %H:%M')}", "utf-8"
        )

        # HTML 正文
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # CSV 附件
        with open(csv_path, encoding="utf-8") as f:
            csv_bytes = f.read().encode("utf-8")
        csv_part = MIMEApplication(csv_bytes, Name=f"temp_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        csv_part["Content-Disposition"] = 'attachment; filename="temp_scan_report.csv"'
        msg.attach(csv_part)

        # 图表附件
        for nad, img_bytes in charts.items():
            img_part = MIMEApplication(img_bytes, Name=f"NAD{nad}_chart.png")
            img_part["Content-Disposition"] = f'attachment; filename="NAD{nad}_chart.png"'
            msg.attach(img_part)

        # 发送
        logger.info(f"[邮件] 连接 SMTP {smtp_host}:{smtp_port}")
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()

        server.login(from_email, api_key)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()

        logger.info(f"[邮件] 发送成功 to={to_email}")
        return True, "发送成功"

    except smtplib.SMTPAuthenticationError:
        msg = "SMTP 认证失败，请检查邮箱地址和 API 密钥（授权码）"
        logger.error(f"[邮件] {msg}")
        return False, msg
    except smtplib.SMTPException as e:
        msg = f"SMTP 发送失败: {e}"
        logger.error(f"[邮件] {msg}")
        return False, msg
    except Exception as e:
        msg = f"邮件发送异常: {e}"
        logger.error(f"[邮件] {msg}")
        return False, msg
