import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import os


class EmailSender:
    """
    SMTP EmailSender utility for automated system notifications,
    inventory alerts, and onboarding emails.
    """
    def __init__(
        self,
        smtp_server: str = "smtp.gmail.com",
        port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True
    ):
        self.smtp_server = smtp_server
        self.port = port
        self.username = username or os.getenv("CB_EMAIL")
        self.password = password or os.getenv("CB_EMAIL_PWD")
        self.use_tls = use_tls

    def send_email(
        self,
        subject: str,
        body: str,
        to_emails: List[str],
        from_email: Optional[str] = None,
        html: bool = False
    ) -> str:
        """
        Send an email via SMTP.
        """
        sender = from_email or self.username
        if not sender:
            sender = "noreply@dine-inventory.local"

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ", ".join(to_emails)
        msg['Subject'] = subject

        mime_type = "html" if html else "plain"
        msg.attach(MIMEText(body, mime_type))

        # If credentials are not configured in local development, gracefully log and simulate sending
        if not self.username or not self.password:
            return f"[Simulated Email] Sent '{subject}' to {to_emails} from {sender}."

        try:
            with smtplib.SMTP(self.smtp_server, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            return f"Email '{subject}' successfully sent to {', '.join(to_emails)}."
        except Exception as e:
            return f"Email sending notice: Failed to send via SMTP ({str(e)}). Notification logged."
