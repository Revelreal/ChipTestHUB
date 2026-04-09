# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, render_template, request

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.get("/notification")
def notification_page():
    return render_template("settings_notification.html")


@settings_bp.get("/api/notification")
def get_notification_config():
    from utils.notification_service import get_notification_service

    svc = get_notification_service()
    cfg = svc.get_config()
    return jsonify({
        "success": True,
        "email": {
            "enabled": cfg.email.enabled,
            "smtp_host": cfg.email.smtp_host,
            "smtp_port": cfg.email.smtp_port,
            "from_email": cfg.email.from_email,
            "to_email": cfg.email.to_email,
            "api_key": cfg.email.api_key,
        },
        "webhook": {
            "enabled": cfg.webhook.enabled,
            "url": cfg.webhook.url,
            "method": cfg.webhook.method,
            "headers": cfg.webhook.headers,
        },
    })


@settings_bp.post("/api/notification/email")
def update_email_config():
    from utils.notification_service import get_notification_service

    data = request.get_json() or {}
    svc = get_notification_service()
    svc.update_email(
        enabled=bool(data.get("enabled", False)),
        smtp_host=str(data.get("smtp_host", "")),
        smtp_port=int(data.get("smtp_port", 465)),
        from_email=str(data.get("from_email", "")),
        to_email=str(data.get("to_email", "")),
        api_key=str(data.get("api_key", "")),
    )
    return jsonify({"success": True})


@settings_bp.post("/api/notification/webhook")
def update_webhook_config():
    from utils.notification_service import get_notification_service

    data = request.get_json() or {}
    svc = get_notification_service()
    svc.update_webhook(
        enabled=bool(data.get("enabled", False)),
        url=str(data.get("url", "")),
        method=str(data.get("method", "POST")),
        headers=data.get("headers") or {},
    )
    return jsonify({"success": True})


@settings_bp.post("/api/notification/test-email")
def test_email():
    """发送测试邮件，使用请求参数中的配置而非已保存的配置。"""
    from utils.notification_service import get_notification_service

    data = request.get_json() or {}
    smtp_host = str(data.get("smtp_host", ""))
    smtp_port = int(data.get("smtp_port", 465))
    from_email = str(data.get("from_email", ""))
    to_email = str(data.get("to_email", ""))
    api_key = str(data.get("api_key", ""))

    if not smtp_host or not from_email or not to_email or not api_key:
        return jsonify({"success": False, "message": "缺少必要的邮件配置参数"}), 400

    svc = get_notification_service()

    # 构造临时 EmailConfig 用于发送测试邮件
    from config import EmailConfig
    import smtplib
    from email.header import Header
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = Header("Chip Test HUB 邮件通知测试", "utf-8")
        body = (
            "这是一封来自 Chip Test HUB 的测试邮件。\n"
            "如果您收到此邮件，说明通知配置正确，测试任务完成/失败时将自动发送结果通知。"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        server.login(from_email, api_key)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        return jsonify({"success": True, "message": "测试邮件发送成功"})
    except smtplib.SMTPAuthenticationError:
        return jsonify({"success": False, "message": "SMTP 认证失败，请检查邮箱地址和授权码"}), 400
    except smtplib.SMTPException as e:
        return jsonify({"success": False, "message": f"SMTP 发送失败: {e}"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"发送异常: {e}"}), 400
