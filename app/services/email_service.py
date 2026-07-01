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