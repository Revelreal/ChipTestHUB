# -*- coding: utf-8 -*-

from dataclasses import dataclass, field


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465
    from_email: str = ""
    to_email: str = ""
    api_key: str = ""  # 授权码/密码


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""
    method: str = "POST"
    headers: dict = field(default_factory=dict)


@dataclass
class NotificationConfig:
    email: EmailConfig = field(default_factory=EmailConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass(frozen=True)
class DeviceConfig:
    gateway_port: str = "COM3"
    gateway_baudrate: int = 115200

    # IT6322A 电源 VISA 地址（默认取自你现有脚本，可在前端请求里覆盖）
    power_address: str = "USB0::0xFFFF::0x6300::802071092767510250::INSTR"
    power_vbat_channel: int = 1


@dataclass(frozen=True)
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 5000


DEFAULT_DEVICE_CONFIG = DeviceConfig()
DEFAULT_APP_CONFIG = AppConfig()

