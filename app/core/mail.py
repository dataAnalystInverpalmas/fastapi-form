"""
Envío de correo electrónico por SMTP.

Usa únicamente la librería estándar (smtplib + email) para no añadir
dependencias nuevas al proyecto. La configuración del servidor (host,
puerto, usuario, TLS/SSL, remitente) se toma de app.core.settings y queda
expuesta en la pantalla de administración de configuración (grupo "Correo
electrónico"), igual que el resto de variables de la app.

Uso:
    from app.core.mail import send_email

    send_email(
        to=["destino@ejemplo.com"],
        subject="Asunto",
        body="Texto del mensaje",
    )
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from app.core.settings import settings

logger = logging.getLogger(__name__)


class MailNotConfiguredError(RuntimeError):
    """El envío de correo está deshabilitado o falta configuración SMTP."""


def _build_message(
    *,
    to: list[str],
    subject: str,
    body: str,
    html: bool,
    cc: list[str] | None,
    attachments: list[Path] | None,
) -> MIMEMultipart:
    message = MIMEMultipart()
    message["Subject"] = subject
    message["From"] = formataddr(
        (settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL or settings.SMTP_USER)
    )
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)

    message.attach(MIMEText(body, "html" if html else "plain", "utf-8"))

    for file_path in attachments or []:
        path = Path(file_path)
        with path.open("rb") as handle:
            part = MIMEApplication(handle.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        message.attach(part)

    return message


def send_email(
    to: list[str],
    subject: str,
    body: str,
    *,
    html: bool = False,
    cc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> None:
    """Envía un correo por SMTP usando la configuración de Settings.

    Lanza MailNotConfiguredError si SMTP_ENABLED es False o falta
    SMTP_HOST, para que quien llama decida si lo trata como error o lo
    omite en silencio (p.ej. una notificación opcional de un job ETL).
    """
    if not settings.SMTP_ENABLED:
        raise MailNotConfiguredError(
            "El envío de correo está deshabilitado (SMTP_ENABLED=False)."
        )
    if not settings.SMTP_HOST:
        raise MailNotConfiguredError("Falta configurar SMTP_HOST.")
    if not to:
        raise ValueError("Debe indicar al menos un destinatario en 'to'.")

    message = _build_message(to=to, subject=subject, body=body, html=html, cc=cc, attachments=attachments)
    recipients = [*to, *(cc or [])]

    if settings.SMTP_USE_SSL:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT, context=context
        ) as server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(message["From"], recipients, message.as_string())
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(message["From"], recipients, message.as_string())

    logger.info("Correo enviado a %s (asunto: %s)", recipients, subject)
