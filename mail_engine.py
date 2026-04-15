import smtplib
import re
import os
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "info@slci.in")
SENDER_PASS = os.getenv("SENDER_PASSWORD", "")


def _smtp_send(msg: MIMEMultipart) -> bool:
    """Internal: Send email via SMTP"""
    if not SENDER_PASS:
        print("⚠ SMTP password not configured")
        return False
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ SMTP error: {e}")
        return False


def extract_email_address(sender_string: str) -> str:
    """Extract clean email from header string"""
    if not sender_string:
        return ""
    if "<" in sender_string and ">" in sender_string:
        return sender_string.split("<")[-1].split(">")[0].strip()
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    match = re.search(pattern, sender_string)
    return match.group(0) if match else sender_string.strip()


def send_department_reply(to_email: str, subject: str, body: str, from_user) -> bool:
    """Send reply from department user to customer - Professional Format"""
    if not SENDER_PASS:
        print("⚠ SMTP not configured - skipping reply")
        return False

    to_email = extract_email_address(to_email)
    
    # ✅ Clean reply body - Professional signature, NO internal IDs
    full_body = f"""{body}

{'─'*60}
Best regards,
{from_user.email}
{from_user.department} Team
SLCI - National Career Service
info@slci.in | 📞 1800-425-1514

⚠ This is an auto-generated reply. Please do not reply directly to this email for new queries."""

    msg = MIMEMultipart("alternative")
    msg["From"] = f"SLCI {from_user.department} Team <{SENDER_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = f"Re: {subject}"  # ✅ Clean subject, no HTML
    
    # Plain text version
    msg.attach(MIMEText(full_body, "plain"))
    
    # HTML version with proper formatting
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;line-height:1.6;color:#333">
        <div style="max-width:600px;margin:0 auto">
            <p>{html.escape(body).replace(chr(10), '<br>')}</p>
            <hr style="border:none;border-top:1px solid #ccc;margin:20px 0">
            <p style="color:#666;font-size:14px;margin:0">
                Best regards,<br>
                <strong>{html.escape(from_user.email)}</strong><br>
                {html.escape(from_user.department)} Team<br>
                SLCI - National Career Service<br>
                <a href="mailto:info@slci.in" style="color:#2ea3f2">info@slci.in</a> | 📞 1800-425-1514
            </p>
            <p style="color:#999;font-size:11px;margin-top:15px;border-top:1px solid #eee;padding-top:10px">
                ⚠ This is an auto-generated reply. Please do not reply directly to this email for new queries.
            </p>
        </div>
    </body></html>
    """
    msg.attach(MIMEText(html_body, "html"))

    ok = _smtp_send(msg)
    if ok:
        print(f"✓ Dept reply sent → {to_email}")
    return ok