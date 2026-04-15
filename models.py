# ═══════════════════════════════════════════════════════════════
# FILE: models.py - SLCI Email Router (WITH ATTACHMENT STORAGE)
# ═══════════════════════════════════════════════════════════════

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib
import html
import json
import re

db = SQLAlchemy()

DEPARTMENTS = ["Client Relations", "Audit", "Legal", "Accounts", "Admin"]


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password   = db.Column(db.String(256), nullable=False)
    role       = db.Column(db.String(50),  nullable=False, default="user")
    department = db.Column(db.String(80),  nullable=False, default="Client Relations")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @staticmethod
    def hash_password(pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    def check_password(self, pw: str) -> bool:
        return self.password == self.hash_password(pw)

    def __repr__(self):
        return f"<User {self.email}>"


# ── HTML colour-stripping helpers ──────────────────────────────

def _strip_color_styles(html_text: str) -> str:
    if not html_text:
        return html_text

    def _clean_style_attr(m: re.Match) -> str:
        style_value = m.group(1)
        props_to_remove = [
            r'color\s*:[^;]+;?',
            r'background(?:-color)?\s*:[^;]+;?',
            r'font-color\s*:[^;]+;?',
        ]
        cleaned = style_value
        for pat in props_to_remove:
            cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip().strip(';').strip()
        return f'style="{cleaned}"' if cleaned else ''

    result = re.sub(
        r'style\s*=\s*"([^"]*)"',
        _clean_style_attr,
        html_text,
        flags=re.IGNORECASE,
    )

    def _clean_style_single(m: re.Match) -> str:
        style_value = m.group(1)
        props_to_remove = [
            r'color\s*:[^;]+;?',
            r'background(?:-color)?\s*:[^;]+;?',
            r'font-color\s*:[^;]+;?',
        ]
        cleaned = style_value
        for pat in props_to_remove:
            cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip().strip(';').strip()
        return f"style='{cleaned}'" if cleaned else ''

    result = re.sub(
        r"style\s*=\s*'([^']*)'",
        _clean_style_single,
        result,
        flags=re.IGNORECASE,
    )

    result = re.sub(r'\s*\bcolor\s*=\s*"[^"]*"',   '', result, flags=re.IGNORECASE)
    result = re.sub(r"\s*\bcolor\s*=\s*'[^']*'",   '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s*\bbgcolor\s*=\s*"[^"]*"', '', result, flags=re.IGNORECASE)
    result = re.sub(r"\s*\bbgcolor\s*=\s*'[^']*'", '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s*\btext\s*=\s*"[^"]*"',    '', result, flags=re.IGNORECASE)
    return result


# ══════════════════════════════════════════════════════════════
#  NEW: EmailAttachment model — stores actual file data in DB
#  (For production with many large files, use filesystem/S3 instead)
# ══════════════════════════════════════════════════════════════

class EmailAttachment(db.Model):
    __tablename__ = "email_attachments"

    id           = db.Column(db.Integer, primary_key=True)
    email_id     = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False, index=True)
    filename     = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(200), default="application/octet-stream")
    file_size    = db.Column(db.Integer, default=0)           # bytes
    file_data    = db.Column(db.LargeBinary, nullable=False)  # actual binary content
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to email
    email = db.relationship("Email", backref=db.backref("attachment_files", lazy="dynamic"))

    def get_icon(self) -> str:
        """Return emoji icon based on file type."""
        ct = (self.content_type or "").lower()
        fn = (self.filename or "").lower()
        if "pdf" in ct or fn.endswith(".pdf"):
            return "📄"
        if "excel" in ct or "spreadsheet" in ct or fn.endswith((".xlsx", ".xls", ".csv")):
            return "📊"
        if "word" in ct or "document" in ct or fn.endswith((".docx", ".doc")):
            return "📝"
        if "image" in ct or fn.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            return "🖼️"
        if "zip" in ct or "rar" in ct or fn.endswith((".zip", ".rar", ".7z", ".tar", ".gz")):
            return "🗜️"
        if "text" in ct or fn.endswith((".txt", ".log", ".md")):
            return "📃"
        if "presentation" in ct or fn.endswith((".pptx", ".ppt")):
            return "📊"
        return "📎"

    def is_viewable_in_browser(self) -> bool:
        """Return True if browser can display this file inline."""
        ct = (self.content_type or "").lower()
        fn = (self.filename or "").lower()
        viewable_types = [
            "application/pdf",
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/svg+xml",
            "text/plain", "text/html", "text/csv",
        ]
        viewable_exts = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".txt"]
        return ct in viewable_types or any(fn.endswith(e) for e in viewable_exts)

    def get_size_display(self) -> str:
        """Human-readable file size."""
        size = self.file_size or 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def __repr__(self):
        return f"<EmailAttachment {self.filename} for email {self.email_id}>"


class Email(db.Model):
    __tablename__ = "emails"

    id = db.Column(db.Integer, primary_key=True)

    # ── Email Content ──────────────────────────────────────────
    sender      = db.Column(db.String(200), nullable=False)
    sender_name = db.Column(db.String(200), default="")
    recipient   = db.Column(db.String(200), default="info@slci.in")
    subject     = db.Column(db.String(500), nullable=False)
    body        = db.Column(db.Text, nullable=False)
    body_html   = db.Column(db.Text, default="")
    cc          = db.Column(db.String(500), default="")
    reply_to    = db.Column(db.String(200), default="")

    # ── Classification & Routing ───────────────────────────────
    category      = db.Column(db.String(80),  default="General Inquiry")
    assigned_role = db.Column(db.String(80))
    assigned_to   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_at   = db.Column(db.DateTime)

    # ── Status ─────────────────────────────────────────────────
    status     = db.Column(db.String(50), default="unread")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # ── Reply Tracking ─────────────────────────────────────────
    replied        = db.Column(db.Boolean, default=False)
    reply_sent_at  = db.Column(db.DateTime)
    reply_by       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reply_content  = db.Column(db.Text)

    # ── Gmail / IMAP Metadata ──────────────────────────────────
    message_id       = db.Column(db.String(300), unique=True, nullable=True, index=True)
    has_attachments  = db.Column(db.Boolean, default=False)
    attachments_info = db.Column(db.Text, default="[]")  # JSON metadata (filenames, sizes)

    # ── Relationships ──────────────────────────────────────────
    replies  = db.relationship("EmailReply", backref="email",   lazy="dynamic", cascade="all, delete-orphan")
    assignee = db.relationship("User",       foreign_keys=[assigned_to], backref="assigned_emails")

    # ── Helper Methods ─────────────────────────────────────────

    def get_attachments(self) -> list:
        """Return parsed attachment metadata list (from JSON field)."""
        try:
            data = self.attachments_info or "[]"
            if isinstance(data, list):
                return data
            return json.loads(data)
        except Exception:
            return []

    def get_attachment_files(self):
        """Return actual EmailAttachment DB records for this email."""
        return self.attachment_files.all()

    def get_body_preview(self, length: int = 80) -> str:
        text = (self.body or "").strip()
        if len(text) <= length:
            return text
        return text[:length] + "…"

    def get_body_for_display(self) -> str:
        if self.body_html:
            cleaned = _strip_color_styles(self.body_html)
            return f'<div class="email-html-body">{cleaned}</div>'
        if not self.body:
            return ""
        escaped = html.escape(self.body)
        return f'<pre class="email-plain-body">{escaped}</pre>'

    def get_sender_display(self) -> str:
        if self.sender_name:
            return f"{self.sender_name} <{self.sender}>"
        return self.sender

    def can_user_access(self, user) -> bool:
        if user.role.lower() == "admin":
            return True
        if self.assigned_to == user.id:
            return True
        if self.assigned_role and self.assigned_role.lower() == user.department.lower():
            return True
        return False

    def __repr__(self):
        return f"<Email {self.subject[:50]} from {self.sender}>"


class EmailReply(db.Model):
    __tablename__ = "email_replies"

    id            = db.Column(db.Integer, primary_key=True)
    email_id      = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False)
    replied_by    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reply_content = db.Column(db.Text, nullable=False)
    replied_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    department    = db.Column(db.String(80))

    user = db.relationship("User", foreign_keys=[replied_by], backref="sent_replies")

    def __repr__(self):
        return f"<EmailReply by {self.replied_by}>"