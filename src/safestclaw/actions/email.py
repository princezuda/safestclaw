"""
SafestClaw Email Action - IMAP/SMTP email integration.

No API keys required - uses standard email protocols.
"""

import email
import imaplib
import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Represents an email message."""
    id: str
    subject: str
    sender: str
    recipient: str
    date: datetime | None
    body: str
    body_html: str | None = None
    is_read: bool = False
    has_attachments: bool = False


@dataclass
class EmailConfig:
    """Email server configuration."""
    # Required fields first (no defaults)
    imap_server: str
    smtp_server: str

    # IMAP settings (for reading)
    imap_port: int = 993
    imap_ssl: bool = True

    # SMTP settings (for sending)
    smtp_port: int = 587
    smtp_ssl: bool = False
    smtp_tls: bool = True

    # Credentials
    username: str = ""
    password: str = ""  # App password recommended

    @classmethod
    def gmail(cls, username: str, password: str) -> "EmailConfig":
        """Create Gmail configuration."""
        return cls(
            imap_server="imap.gmail.com",
            imap_port=993,
            smtp_server="smtp.gmail.com",
            smtp_port=587,
            username=username,
            password=password,
        )

    @classmethod
    def outlook(cls, username: str, password: str) -> "EmailConfig":
        """Create Outlook/Hotmail configuration."""
        return cls(
            imap_server="outlook.office365.com",
            imap_port=993,
            smtp_server="smtp.office365.com",
            smtp_port=587,
            username=username,
            password=password,
        )

    @classmethod
    def yahoo(cls, username: str, password: str) -> "EmailConfig":
        """Create Yahoo configuration."""
        return cls(
            imap_server="imap.mail.yahoo.com",
            imap_port=993,
            smtp_server="smtp.mail.yahoo.com",
            smtp_port=587,
            username=username,
            password=password,
        )


class EmailClient:
    """
    Email client for reading and sending emails.

    Uses IMAP for reading and SMTP for sending.
    No API keys required - standard protocols.
    """

    def __init__(self, config: EmailConfig):
        self.config = config
        self._imap: imaplib.IMAP4_SSL | None = None

    def _decode_header_value(self, header: str) -> str:
        """Decode email header value."""
        if not header:
            return ""

        decoded_parts = decode_header(header)
        result = []

        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                result.append(str(part))

        return ''.join(result)

    def _parse_email(self, msg_data: bytes, msg_id: str) -> EmailMessage:
        """Parse raw email data into EmailMessage."""
        msg = email.message_from_bytes(msg_data)

        # Get subject
        subject = self._decode_header_value(msg.get('Subject', ''))

        # Get sender
        sender = self._decode_header_value(msg.get('From', ''))

        # Get recipient
        recipient = self._decode_header_value(msg.get('To', ''))

        # Get date
        date_str = msg.get('Date', '')
        date = None
        if date_str:
            try:
                date = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                pass

        # Get body
        body = ""
        body_html = None
        has_attachments = False

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    has_attachments = True
                elif content_type == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='replace')
                elif content_type == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_html = payload.decode('utf-8', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='replace')

        # If no plain text, try to extract from HTML
        if not body and body_html:
            body = re.sub(r'<[^>]+>', '', body_html)
            body = re.sub(r'\s+', ' ', body).strip()

        return EmailMessage(
            id=msg_id,
            subject=subject,
            sender=sender,
            recipient=recipient,
            date=date,
            body=body[:5000],  # Limit body length
            body_html=body_html,
            has_attachments=has_attachments,
        )

    def connect_imap(self) -> bool:
        """Connect to IMAP server."""
        try:
            if self.config.imap_ssl:
                self._imap = imaplib.IMAP4_SSL(
                    self.config.imap_server,
                    self.config.imap_port,
                )
            else:
                self._imap = imaplib.IMAP4(
                    self.config.imap_server,
                    self.config.imap_port,
                )

            self._imap.login(self.config.username, self.config.password)
            return True
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return False

    def disconnect_imap(self) -> None:
        """Disconnect from IMAP server."""
        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def get_unread_count(self, folder: str = "INBOX") -> int:
        """Get count of unread emails."""
        if not self._imap:
            if not self.connect_imap():
                return 0

        try:
            self._imap.select(folder)
            _, data = self._imap.search(None, 'UNSEEN')
            return len(data[0].split())
        except Exception as e:
            logger.error(f"Failed to get unread count: {e}")
            return 0

    def get_emails(
        self,
        folder: str = "INBOX",
        limit: int = 10,
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """Fetch emails from folder."""
        if not self._imap:
            if not self.connect_imap():
                return []

        try:
            self._imap.select(folder)

            # Search for emails
            search_criteria = 'UNSEEN' if unread_only else 'ALL'
            _, data = self._imap.search(None, search_criteria)

            email_ids = data[0].split()
            if not email_ids:
                return []

            # Get most recent
            email_ids = email_ids[-limit:][::-1]

            emails = []
            for eid in email_ids:
                _, msg_data = self._imap.fetch(eid, '(RFC822)')
                if msg_data and msg_data[0]:
                    raw_email = msg_data[0][1]
                    email_msg = self._parse_email(raw_email, eid.decode())
                    emails.append(email_msg)

            return emails
        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}")
            return []

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> bool:
        """Send an email via SMTP."""
        try:
            # Create message
            if html:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(body, 'html'))
            else:
                msg = MIMEText(body)

            msg['Subject'] = subject
            msg['From'] = self.config.username
            msg['To'] = to

            # Connect and send
            if self.config.smtp_ssl:
                server = smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                )
            else:
                server = smtplib.SMTP(
                    self.config.smtp_server,
                    self.config.smtp_port,
                )
                if self.config.smtp_tls:
                    server.starttls()

            server.login(self.config.username, self.config.password)
            server.send_message(msg)
            server.quit()

            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        """Mark an email as read."""
        if not self._imap:
            if not self.connect_imap():
                return False

        try:
            self._imap.select(folder)
            self._imap.store(email_id.encode(), '+FLAGS', '\\Seen')
            return True
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False


class EmailAction(BaseAction):
    """
    Email action for SafestClaw.

    Commands:
    - check email / inbox
    - unread emails
    - send email to X
    """

    name = "email"
    description = "Check and send emails"

    def __init__(self):
        self._client: EmailClient | None = None

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute email action."""
        subcommand = params.get("subcommand", "check")

        # Load email config from user preferences
        config = await self._get_config(user_id, engine)
        if not config:
            return (
                "Email not configured. Set up with:\n"
                "  `email setup gmail your@email.com your-app-password`\n"
                "Note: Use an app password, not your regular password."
            )

        self._client = EmailClient(config)

        try:
            if subcommand in ("check", "inbox"):
                return await self._check_inbox(params)
            elif subcommand == "unread":
                return await self._check_unread()
            elif subcommand == "send":
                return await self._send_email(params)
            elif subcommand == "count":
                return await self._get_count()
            else:
                return await self._check_inbox(params)
        finally:
            if self._client:
                self._client.disconnect_imap()

    async def _get_config(
        self,
        user_id: str,
        engine: "SafestClaw",
    ) -> EmailConfig | None:
        """Get email configuration for user."""
        config_data = await engine.memory.get_preference(user_id, "email_config")
        if not config_data:
            return None

        return EmailConfig(
            imap_server=config_data.get("imap_server", ""),
            imap_port=config_data.get("imap_port", 993),
            smtp_server=config_data.get("smtp_server", ""),
            smtp_port=config_data.get("smtp_port", 587),
            username=config_data.get("username", ""),
            password=config_data.get("password", ""),
        )

    async def _check_inbox(self, params: dict) -> str:
        """Check inbox."""
        limit = params.get("limit", 5)
        emails = self._client.get_emails(limit=limit)

        if not emails:
            return "📭 No emails found."

        lines = [f"📬 **Inbox** ({len(emails)} recent emails)", ""]

        for em in emails:
            date_str = em.date.strftime("%b %d") if em.date else ""
            read_icon = "📧" if not em.is_read else "📩"
            lines.append(f"{read_icon} **{em.subject[:50]}**")
            lines.append(f"   From: {em.sender} • {date_str}")
            if em.body:
                preview = em.body[:100].replace('\n', ' ')
                lines.append(f"   _{preview}..._")
            lines.append("")

        return "\n".join(lines)

    async def _check_unread(self) -> str:
        """Check unread emails only."""
        emails = self._client.get_emails(unread_only=True, limit=10)

        if not emails:
            return "✅ No unread emails!"

        lines = [f"📬 **{len(emails)} Unread Emails**", ""]

        for em in emails:
            date_str = em.date.strftime("%b %d %H:%M") if em.date else ""
            lines.append(f"• **{em.subject[:50]}**")
            lines.append(f"  From: {em.sender} • {date_str}")
            lines.append("")

        return "\n".join(lines)

    async def _send_email(self, params: dict) -> str:
        """Send an email."""
        to = params.get("recipient", "")
        subject = params.get("subject", "")
        body = params.get("body", "")

        if not to:
            return "Please specify a recipient email address."

        if not subject and not body:
            return "Please provide a subject and/or body for the email."

        success = self._client.send_email(to, subject or "(No subject)", body)

        if success:
            return f"✅ Email sent to {to}"
        else:
            return f"❌ Failed to send email to {to}"

    async def _get_count(self) -> str:
        """Get unread email count."""
        count = self._client.get_unread_count()
        if count == 0:
            return "✅ No unread emails"
        elif count == 1:
            return "📧 You have 1 unread email"
        else:
            return f"📧 You have {count} unread emails"
