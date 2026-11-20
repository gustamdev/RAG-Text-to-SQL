"""Envio de e-mail transacional (só OTP). `console` imprime no log (dev); `smtp` usa smtplib (STARTTLS)."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_S = 10
_SUBJECTS = {"signup": "Confirme seu e-mail", "login": "Seu código de acesso", "reset": "Redefinir senha"}


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def send_otp(email: str, code: str, purpose: str) -> None:
    """Bloqueante: chame via asyncio.to_thread. Corpo = só código e validade."""
    if settings.MAIL_BACKEND == "console":
        if settings.is_prod:  # defesa extra: o Settings já recusa essa combinação no start
            raise RuntimeError("MAIL_BACKEND=console não é permitido em prod.")
        label = "redefinir senha" if purpose == "reset" else purpose
        logger.info("[mail:console] código %s para %s (%s)", code, mask_email(email), label)
        return
    subject = _SUBJECTS.get(purpose, "Seu código")
    # Anti-injeção de cabeçalho: nada de CR/LF no destinatário nem no assunto.
    if any(c in v for v in (email, subject) for c in "\r\n"):
        raise ValueError("Cabeçalho de e-mail inválido.")
    minutes = max(1, -(-settings.OTP_TTL_S // 60))
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, email, subject
    what = "para redefinir sua senha " if purpose == "reset" else ""
    msg.set_content(f"Seu código {what}é {code}. Válido por {minutes} minutos.")
    _smtp_send(msg)


def send_password_changed(email: str) -> None:
    """Aviso de senha alterada (bloqueante: chame via asyncio.to_thread). Sem código nem dado extra."""
    if settings.MAIL_BACKEND == "console":
        if settings.is_prod:
            raise RuntimeError("MAIL_BACKEND=console não é permitido em prod.")
        logger.info("[mail:console] aviso de senha alterada para %s", mask_email(email))
        return
    if any(c in email for c in "\r\n"):
        raise ValueError("Cabeçalho de e-mail inválido.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, email, "Sua senha foi alterada"
    msg.set_content("Sua senha foi alterada. Se não foi você, redefina a senha de novo e fale com o suporte.")
    _smtp_send(msg)


def _smtp_send(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_S) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
        smtp.send_message(msg)
