"""
Email Service Module
Sends Gmail notifications for ticket creation and developer assignment
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
from .config import Config


class EmailService:
    """Gmail SMTP email service for ticket notifications"""

    def __init__(
        self,
        gmail_address: Optional[str] = None,
        app_password: Optional[str] = None,
    ):
        self.gmail_address = gmail_address or Config.GMAIL_ADDRESS
        self.app_password = app_password or Config.GMAIL_APP_PASSWORD

    def _is_configured(self) -> bool:
        return bool(self.gmail_address and self.app_password)

    def _send(self, msg: MIMEMultipart) -> bool:
        """Send an email message via Gmail SMTP SSL"""
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.gmail_address, self.app_password)
                server.send_message(msg)
            return True
        except smtplib.SMTPAuthenticationError:
            raise ValueError(
                "Gmail authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD. "
                "Make sure you're using an App Password (not your regular Gmail password)."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to send email: {e}") from e

    def send_customer_confirmation(
        self,
        to_email: str,
        user_name: str,
        ticket_id: str,
        category: str,
        priority: str,
        ai_response: str,
        sla_hours: int,
    ) -> bool:
        """
        Send ticket confirmation email to the customer.

        Args:
            to_email: Customer's email address
            user_name: Customer's name
            ticket_id: Generated ticket ID
            category: Ticket category
            priority: Priority level
            ai_response: Initial AI-generated response
            sla_hours: Expected resolution time in hours

        Returns:
            True if sent successfully
        """
        if not self._is_configured():
            print("⚠️ Email not configured — skipping customer confirmation email")
            return False

        priority_colors = {
            "urgent": "#C62828",
            "high": "#E65100",
            "medium": "#1565C0",
            "low": "#2E7D32",
        }
        color = priority_colors.get(priority.lower(), "#1565C0")

        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
          <div style="background:#1E88E5;padding:20px;border-radius:8px 8px 0 0;">
            <h2 style="color:white;margin:0;">Support Ticket Created</h2>
          </div>
          <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;">
            <p>Dear <strong>{user_name}</strong>,</p>
            <p>Your support ticket has been received and is being reviewed by our team.</p>

            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr>
                <td style="padding:8px;background:#f5f5f5;font-weight:bold;width:40%;">Ticket ID</td>
                <td style="padding:8px;background:#f5f5f5;font-family:monospace;">{ticket_id}</td>
              </tr>
              <tr>
                <td style="padding:8px;font-weight:bold;">Category</td>
                <td style="padding:8px;">{category}</td>
              </tr>
              <tr>
                <td style="padding:8px;background:#f5f5f5;font-weight:bold;">Priority</td>
                <td style="padding:8px;background:#f5f5f5;">
                  <span style="color:{color};font-weight:bold;">{priority.upper()}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:8px;font-weight:bold;">Expected Resolution</td>
                <td style="padding:8px;">Within {sla_hours} hours</td>
              </tr>
            </table>

            <h3 style="color:#1E88E5;">Initial AI Response</h3>
            <div style="background:#f9f9f9;padding:16px;border-left:4px solid #1E88E5;border-radius:4px;">
              {ai_response.replace(chr(10), '<br>')}
            </div>

            <p style="margin-top:24px;color:#666;font-size:0.9em;">
              If this response didn't fully resolve your issue, a human support agent will
              follow up within the time mentioned above. Please reply to this email with
              your ticket ID if you have additional information to add.
            </p>
            <p style="color:#999;font-size:0.8em;">— AI Customer Support System</p>
          </div>
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{ticket_id}] Support Ticket Received — {category}"
        msg["From"] = self.gmail_address
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        return self._send(msg)

    def send_developer_alert(
        self,
        ticket_id: str,
        user_name: str,
        user_email: str,
        issue_description: str,
        category: str,
        priority: str,
        sentiment: str,
        ai_response: str,
        screenshot_path: Optional[str] = None,
        attempt_history: Optional[list] = None,
    ) -> bool:
        """
        Send ticket assignment alert to the developer/support team.

        Returns:
            True if sent successfully
        """
        developer_email = Config.DEVELOPER_EMAIL
        if not self._is_configured() or not developer_email:
            print("⚠️ Email not configured — skipping developer alert email")
            return False

        priority_colors = {
            "urgent": "#C62828",
            "high": "#E65100",
            "medium": "#1565C0",
            "low": "#2E7D32",
        }
        color = priority_colors.get(priority.lower(), "#1565C0")

        attempts_html = ""
        if attempt_history:
            attempts_html = "<h3>Self-Help Attempts (before ticket creation)</h3><ol>"
            for i, attempt in enumerate(attempt_history, 1):
                attempts_html += f"<li><strong>Attempt {i}:</strong> {attempt}</li>"
            attempts_html += "</ol>"

        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: auto;">
          <div style="background:#D32F2F;padding:20px;border-radius:8px 8px 0 0;">
            <h2 style="color:white;margin:0;">
              🎫 New Support Ticket —
              <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:4px;">
                {priority.upper()}
              </span>
            </h2>
          </div>
          <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;">

            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
              <tr>
                <td style="padding:8px;background:#f5f5f5;font-weight:bold;width:35%;">Ticket ID</td>
                <td style="padding:8px;background:#f5f5f5;font-family:monospace;">{ticket_id}</td>
              </tr>
              <tr>
                <td style="padding:8px;font-weight:bold;">Customer Name</td>
                <td style="padding:8px;">{user_name}</td>
              </tr>
              <tr>
                <td style="padding:8px;background:#f5f5f5;font-weight:bold;">Customer Email</td>
                <td style="padding:8px;background:#f5f5f5;">{user_email}</td>
              </tr>
              <tr>
                <td style="padding:8px;font-weight:bold;">Category</td>
                <td style="padding:8px;">{category}</td>
              </tr>
              <tr>
                <td style="padding:8px;background:#f5f5f5;font-weight:bold;">Priority</td>
                <td style="padding:8px;background:#f5f5f5;">
                  <span style="color:{color};font-weight:bold;">{priority.upper()}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:8px;font-weight:bold;">Sentiment</td>
                <td style="padding:8px;">{sentiment.capitalize()}</td>
              </tr>
            </table>

            <h3>Issue Description</h3>
            <div style="background:#fff3e0;padding:16px;border-left:4px solid #E65100;border-radius:4px;">
              {issue_description.replace(chr(10), '<br>')}
            </div>

            {attempts_html}

            <h3>AI Initial Response (sent to customer)</h3>
            <div style="background:#e8f5e9;padding:16px;border-left:4px solid #2E7D32;border-radius:4px;">
              {ai_response.replace(chr(10), '<br>')}
            </div>

            <p style="margin-top:20px;color:#666;font-size:0.9em;">
              Please review and follow up with the customer within the SLA window.
            </p>
          </div>
        </body></html>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"[{priority.upper()}] New Ticket {ticket_id} — {category}"
        msg["From"] = self.gmail_address
        msg["To"] = developer_email

        msg.attach(MIMEText(html_body, "html"))

        # Attach screenshot if provided
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                with open(screenshot_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(screenshot_path)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)
            except Exception as e:
                print(f"⚠️ Could not attach screenshot: {e}")

        return self._send(msg)
