"""
邮件发送工具 - 用于验证码、通知等，基于 SMTP 配置
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def send_email(
    smtp_host: str,
    smtp_port: int,
    to_email: str,
    subject: str,
    body: str,
    *,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
    from_email: Optional[str] = None,
    use_tls: bool = True,
) -> Tuple[bool, str]:
    """
    使用 SMTP 发送邮件。
    返回 (成功与否, 消息)。
    """
    if not smtp_host or not to_email:
        return False, "SMTP 主机和收件人不能为空"
    from_addr = from_email or smtp_user or "noreply@localhost"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True, "发送成功"
    except Exception as e:
        logger.exception("Send email failed: %s", e)
        return False, str(e)
