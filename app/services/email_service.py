import os
import smtplib
from email.message import EmailMessage


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME)


def send_verification_email(to_email: str, verification_link: str) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD or not EMAIL_FROM:
        raise RuntimeError("SMTP variables are not configured")

    message = EmailMessage()
    message["Subject"] = "Verify your InstantBarbers email"
    message["From"] = f"InstantBarbers <{EMAIL_FROM}>"
    message["To"] = to_email

    message.set_content(
        f"""
Welcome to InstantBarbers!

Please verify your email address by opening this link:

{verification_link}

If you did not create this account, you can ignore this email.
"""
    )

    message.add_alternative(
        f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Welcome to InstantBarbers!</h2>

                <p>Please verify your email address to activate your account.</p>

                <p>
                    <a href="{verification_link}"
                       style="
                           display: inline-block;
                           padding: 12px 20px;
                           background-color: #111827;
                           color: white;
                           text-decoration: none;
                           border-radius: 6px;
                       ">
                        Verify my email
                    </a>
                </p>

                <p>If you did not create this account, you can ignore this email.</p>
            </body>
        </html>
        """,
        subtype="html",
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD or not EMAIL_FROM:
        raise RuntimeError("SMTP variables are not configured")

    message = EmailMessage()
    message["Subject"] = "Reset your InstantBarbers password"
    message["From"] = f"InstantBarbers <{EMAIL_FROM}>"
    message["To"] = to_email

    message.set_content(
        f"""
InstantBarbers password reset

We received a request to reset your password.

Open this link to create a new password:

{reset_link}

This link will expire for your security.

If you did not request a password reset, you can ignore this email.
"""
    )

    message.add_alternative(
        f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Reset your InstantBarbers password</h2>

                <p>We received a request to reset your password.</p>

                <p>Click the button below to create a new password.</p>

                <p>
                    <a href="{reset_link}"
                       style="
                           display: inline-block;
                           padding: 12px 20px;
                           background-color: #111827;
                           color: white;
                           text-decoration: none;
                           border-radius: 6px;
                       ">
                        Reset my password
                    </a>
                </p>

                <p>This link will expire for your security.</p>

                <p>
                    If you did not request a password reset,
                    you can ignore this email.
                </p>
            </body>
        </html>
        """,
        subtype="html",
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)


    
# BLOQUE 14 — CONFIRMACIÓN DE DIRECCIÓN DE CHEQUES

def send_cheque_delivery_confirmation_email(
    to_email: str,
    confirmation_link: str,
    language: str = "en",
) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD or not EMAIL_FROM:
        raise RuntimeError("SMTP variables are not configured")

    is_french = str(language).lower().startswith("fr")

    message = EmailMessage()
    message["From"] = f"InstantBarbers <{EMAIL_FROM}>"
    message["To"] = to_email

    if is_french:
        message["Subject"] = (
            "InstantBarbers - Confirmez votre adresse de paiement"
        )
        message.set_content(
            "Une demande de modification de votre adresse "
            "de paiement par chèque a été reçue.\n\n"
            "Confirmez cette demande avec le lien suivant :\n\n"
            f"{confirmation_link}\n\n"
            "Si vous n'avez pas demandé cette modification, "
            "n'ouvrez pas le lien et contactez InstantBarbers.\n\n"
            "Ne partagez jamais ce lien."
        )
    else:
        message["Subject"] = (
            "InstantBarbers - Confirm your payment address"
        )
        message.set_content(
            "We received a request to change your "
            "cheque delivery address.\n\n"
            "Confirm this request using the following link:\n\n"
            f"{confirmation_link}\n\n"
            "If you did not request this change, "
            "do not open the link and contact InstantBarbers.\n\n"
            "Never share this link."
        )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            SMTP_HOST, SMTP_PORT, timeout=20
        ) as smtp:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(
            SMTP_HOST, SMTP_PORT, timeout=20
        ) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
