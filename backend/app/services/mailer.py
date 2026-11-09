"""Отправка писем. Без настроек SMTP письмо печатается в лог — удобно при разработке."""

import logging
import smtplib
from email.message import EmailMessage

from fastapi.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send_mail(to: str, subject: str, body: str) -> None:
    """Вызывается в фоне, после ответа клиенту: ошибку показать уже некому, поэтому только лог."""
    if not settings.smtp_host:
        if settings.cookie_secure:
            # На сервере тело письма в лог не пишем: в нём ссылка для сброса пароля
            logger.error("SMTP не настроен, письмо для %s не отправлено: %s", to, subject)
        else:
            logger.warning("SMTP не настроен. Письмо для %s: %s\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        # smtplib синхронный — в отдельном потоке он не блокирует остальные запросы
        await run_in_threadpool(_send_smtp, message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Не удалось отправить письмо на %s", to)


async def send_password_reset(to: str, token: str) -> None:
    await send_mail(
        to,
        "Сброс пароля Walletly",
        "Чтобы задать новый пароль, откройте ссылку (действует 1 час):\n"
        f"{settings.app_url}/reset-password?token={token}\n\n"
        "Если вы не запрашивали сброс, просто проигнорируйте это письмо.",
    )


async def send_email_verification(to: str, token: str) -> None:
    await send_mail(
        to,
        "Подтвердите email в Walletly",
        f"Чтобы подтвердить адрес, откройте ссылку:\n{settings.app_url}/verify-email?token={token}",
    )
