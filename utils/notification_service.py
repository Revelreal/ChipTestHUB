# -*- coding: utf-8 -*-

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from config import EmailConfig, NotificationConfig, WebhookConfig

logger = logging.getLogger("notification")


class NotificationService:
    """
    全局通知服务，解耦于任务逻辑。
    所有任务完成时统一调用 notify()，由本服务决定是否发送邮件/机器人通知。
    """

    CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "settings", "notification.json"
    )

    # 通知内容模板，按 task_type 索引
    _TEMPLATES = {
        "temp_scan": {
            "subject": "温度扫描测试完成 - {time}",
            "body": (
                "温度扫描测试已于 {time} 完成。\n"
                "测试结果：{result}\n"
                "结果文件：{result_path}\n"
            ),
        },
        "power_cycle": {
            "subject": "上下电耐受测试完成 - {time}",
            "body": (
                "上下电耐受测试已于 {time} 完成。\n"
                "测试结果：{result}\n"
                "结果文件：{result_path}\n"
            ),
        },
        "voltage_scan": {
            "subject": "电压扫描测试完成 - {time}",
            "body": (
                "电压扫描测试已于 {time} 完成。\n"
                "测试结果：{result}\n"
                "结果文件：{result_path}\n"
            ),
        },
        "voltage_set": {
            "subject": "电压设置测试完成 - {time}",
            "body": (
                "电压设置测试已于 {time} 完成。\n"
                "测试结果：{result}\n"
                "结果文件：{result_path}\n"
            ),
        },
    }

    def __init__(self) -> None:
        self._config = self._load()

    # ── 配置读写 ────────────────────────────────────────────────

    def _load(self) -> NotificationConfig:
        """从 JSON 文件加载通知配置，不存在则返回默认配置。"""
        if not os.path.exists(self.CONFIG_PATH):
            return NotificationConfig()
        try:
            with open(self.CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            email_data = data.get("email", {})
            webhook_data = data.get("webhook", {})
            email_cfg = EmailConfig(
                enabled=bool(email_data.get("enabled", False)),
                smtp_host=str(email_data.get("smtp_host", "")),
                smtp_port=int(email_data.get("smtp_port", 465)),
                from_email=str(email_data.get("from_email", "")),
                to_email=str(email_data.get("to_email", "")),
                api_key=str(email_data.get("api_key", "")),
            )
            webhook_cfg = WebhookConfig(
                enabled=bool(webhook_data.get("enabled", False)),
                url=str(webhook_data.get("url", "")),
                method=str(webhook_data.get("method", "POST")),
                headers=webhook_data.get("headers", {}),
            )
            cfg = NotificationConfig(email=email_cfg, webhook=webhook_cfg)
            logger.info(f"[notification] 配置已加载 from {self.CONFIG_PATH}")
            return cfg
        except Exception as e:
            logger.warning(f"[notification] 加载配置失败，使用默认配置: {e}")
            return NotificationConfig()

    def _save(self) -> None:
        """将当前配置写回 JSON 文件。"""
        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        data = {
            "email": {
                "enabled": self._config.email.enabled,
                "smtp_host": self._config.email.smtp_host,
                "smtp_port": self._config.email.smtp_port,
                "from_email": self._config.email.from_email,
                "to_email": self._config.email.to_email,
                "api_key": self._config.email.api_key,
            },
            "webhook": {
                "enabled": self._config.webhook.enabled,
                "url": self._config.webhook.url,
                "method": self._config.webhook.method,
                "headers": self._config.webhook.headers,
            },
        }
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[notification] 配置已保存到 {self.CONFIG_PATH}")

    def get_config(self) -> NotificationConfig:
        return self._config

    def update_email(self, enabled: bool, smtp_host: str, smtp_port: int,
                     from_email: str, to_email: str, api_key: str) -> None:
        self._config.email.enabled = enabled
        self._config.email.smtp_host = smtp_host
        self._config.email.smtp_port = smtp_port
        self._config.email.from_email = from_email
        self._config.email.to_email = to_email
        self._config.email.api_key = api_key
        self._save()

    def update_webhook(self, enabled: bool, url: str, method: str,
                       headers: dict) -> None:
        self._config.webhook.enabled = enabled
        self._config.webhook.url = url
        self._config.webhook.method = method
        self._config.webhook.headers = headers
        self._save()

    # ── 发送通知 ────────────────────────────────────────────────

    def notify(
        self,
        task_type: str,
        task_status: str,          # "completed" | "failed"
        result_path: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        任务完成/失败时统一调用的通知入口。
        返回 (success, message)。
        """
        if task_status not in ("completed", "failed"):
            return True, "skipped (not completed/failed)"

        if not self._config.email.enabled and not self._config.webhook.enabled:
            return True, "skipped (all channels disabled)"

        success = True
        messages = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_label = "通过" if task_status == "completed" else "失败"

        # --- Email ---
        if self._config.email.enabled:
            try:
                ok, msg = self._send_email(
                    task_type=task_type,
                    task_status=task_status,
                    result_label=result_label,
                    result_path=result_path or "",
                    now_str=now_str,
                    extra=extra,
                )
                messages.append(msg)
                if not ok:
                    success = False
            except Exception as e:
                messages.append(f"邮件发送异常: {e}")
                success = False

        # --- Webhook（预留接口）---
        if self._config.webhook.enabled:
            try:
                ok, msg = self._send_webhook(
                    task_type=task_type,
                    task_status=task_status,
                    result_label=result_label,
                    result_path=result_path or "",
                    now_str=now_str,
                    extra=extra,
                )
                messages.append(msg)
                if not ok:
                    success = False
            except Exception as e:
                messages.append(f"Webhook 发送异常: {e}")
                success = False

        final_msg = "; ".join(messages)
        logger.info(f"[notification] notify done: {final_msg}")
        return success, final_msg

    def _send_email(
        self,
        task_type: str,
        task_status: str,
        result_label: str,
        result_path: str,
        now_str: str,
        extra: Optional[Dict[str, Any]],
    ) -> tuple:
        """发送邮件通知。"""
        from utils.email_sender import send_result_email

        tmpl = self._TEMPLATES.get(task_type, {
            "subject": f"{task_type} 测试完成 - {now_str}",
            "body": f"测试已于 {now_str} 完成，结果：{result_label}\n结果文件：{result_path}",
        })

        subject = tmpl.get("subject", "{task_type} 测试完成 - {time}").format(
            time=now_str
        )
        body = tmpl.get("body", "").format(
            time=now_str,
            result=result_label,
            result_path=result_path,
        )

        # 温度测试走专用邮件函数（带图表）
        if task_type == "temp_scan" and result_path and os.path.exists(result_path):
            nad_list = []
            if extra and "nad_list" in extra:
                nad_list = extra["nad_list"]
            if not nad_list:
                nad_list = [1]  # fallback
            ok, msg = send_result_email(
                csv_path=result_path,
                nad_list=nad_list,
                to_email=self._config.email.to_email,
                smtp_host=self._config.email.smtp_host,
                smtp_port=self._config.email.smtp_port,
                from_email=self._config.email.from_email,
                api_key=self._config.email.api_key,
            )
            return ok, f"邮件: {msg}"

        # 通用纯文本邮件
        return self._send_text_email(subject, body)

    def _send_text_email(self, subject: str, body: str) -> tuple:
        """发送纯文本邮件（不带附件）。"""
        import smtplib
        from email.header import Header
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = self._config.email.from_email
            msg["To"] = self._config.email.to_email
            msg["Subject"] = Header(subject, "utf-8")
            msg.attach(MIMEText(body, "plain", "utf-8"))

            cfg = self._config.email
            if cfg.smtp_port == 465:
                server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port)
            else:
                server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port)
                server.starttls()

            server.login(cfg.from_email, cfg.api_key)
            server.sendmail(cfg.from_email, [cfg.to_email], msg.as_string())
            server.quit()
            return True, "发送成功"
        except Exception as e:
            return False, str(e)

    def _send_webhook(
        self,
        task_type: str,
        task_status: str,
        result_label: str,
        result_path: str,
        now_str: str,
        extra: Optional[Dict[str, Any]],
    ) -> tuple:
        """
        发送 Webhook 通知（预留接口）。
        目前返回 NotImplemented，后续可接入钉钉/飞书机器人。
        """
        # TODO: 接入钉钉/飞书机器人
        logger.warning("[notification] Webhook 通道暂未实现，跳过")
        return True, "Webhook: skipped (not implemented)"


# 全局单例
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
