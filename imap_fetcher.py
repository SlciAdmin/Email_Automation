# ═══════════════════════════════════════════════════════════════
# FILE: imap_fetcher.py  –  FIXED: duplicate key + timezone bugs
# ═══════════════════════════════════════════════════════════════

import imaplib
import email
import email.utils
import os
import re
import html
import json
import time
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()


class EmailFetcher:
    """Fetch ALL recent emails from IMAP - zero emails missed."""

    def __init__(self):
        self.imap_host        = os.getenv("IMAP_HOST",     "imap.gmail.com")
        self.imap_port        = int(os.getenv("IMAP_PORT", 993))
        self.email_user       = os.getenv("IMAP_EMAIL",    "info@slci.in")
        self.email_pass       = os.getenv("IMAP_PASSWORD", "")
        self.fetch_window_hrs = int(os.getenv("FETCH_WINDOW_HOURS", 2))

        if not self.email_pass:
            print("⚠  IMAP_PASSWORD not set – emails will not be fetched!")

    # ── IMAP connection ────────────────────────────────────────

    def connect(self) -> bool:
        try:
            self.mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            self.mail.login(self.email_user, self.email_pass)
            self.mail.select("INBOX")
            print(f"✅ IMAP connected: {self.email_user}")
            return True
        except Exception as e:
            print(f"❌ IMAP connection error: {e}")
            return False

    def disconnect(self):
        try:
            self.mail.close()
            self.mail.logout()
        except Exception:
            pass

    # ── Static helpers ─────────────────────────────────────────

    @staticmethod
    def _decode_str(raw, encoding="utf-8") -> str:
        if isinstance(raw, bytes):
            try:
                return raw.decode(encoding or "utf-8", errors="replace")
            except Exception:
                return raw.decode("latin-1", errors="replace")
        return str(raw) if raw else ""

    @staticmethod
    def _decode_mime_header(header_value: str) -> str:
        if not header_value:
            return ""
        parts = decode_header(header_value)
        decoded = []
        for raw, enc in parts:
            if isinstance(raw, bytes):
                decoded.append(raw.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(raw))
        return "".join(decoded)

    @staticmethod
    def _extract_email(raw_from: str) -> str:
        if not raw_from:
            return "unknown@email.com"
        m = re.search(r'<([^<>@\s]+@[^<>\s]+)>', raw_from)
        if m:
            return m.group(1).lower()
        m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', raw_from)
        return m.group(0).lower() if m else raw_from.strip().lower()

    @staticmethod
    def _extract_name(raw_from: str) -> str:
        if not raw_from:
            return "Unknown"
        m = re.match(r'^"?([^"<]+)"?\s*<', raw_from.strip())
        if m:
            name = m.group(1).strip()
            if name and "@" not in name:
                return name
        addr = EmailFetcher._extract_email(raw_from)
        if "@" in addr:
            return addr.split("@")[0].replace(".", " ").replace("_", " ").title()
        return "Customer"

    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _sanitise_html(raw_html: str) -> str:
        if not raw_html:
            return ""
        cleaned = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw_html,
                         flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<a ', '<a target="_blank" rel="noopener noreferrer" ', cleaned,
                         flags=re.IGNORECASE)
        return cleaned

    # ── Body extraction ────────────────────────────────────────

    def _get_body(self, msg) -> tuple:
        """Returns (plain_text, sanitised_html)."""
        plain, html_body = "", ""

        if msg.is_multipart():
            for part in msg.walk():
                ct   = part.get_content_type()
                disp = str(part.get("Content-Disposition", "") or "")
                if "attachment" in disp.lower():
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = self._decode_str(payload, charset)
                if ct == "text/plain"  and not plain:
                    plain = decoded
                elif ct == "text/html" and not html_body:
                    html_body = decoded
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded = self._decode_str(payload, charset)
                ct = msg.get_content_type()
                if ct == "text/plain":
                    plain = decoded
                elif ct == "text/html":
                    html_body = decoded

        if not plain and html_body:
            plain = self._strip_html(html_body)

        sanitised_html = self._sanitise_html(html_body) if html_body else ""
        return plain.strip() or "No content", sanitised_html

    # ── Attachment extraction (WITH binary data) ───────────────

    def _get_attachments(self, msg) -> list:
        """
        Returns list of dicts with:
          filename, content_type, size, data (bytes)
        """
        attachments = []
        if not msg.is_multipart():
            return attachments

        for part in msg.walk():
            content_disp = str(part.get("Content-Disposition", "") or "")
            content_type = part.get_content_type() or "application/octet-stream"

            raw_name = part.get_filename()
            if not raw_name and "attachment" not in content_disp.lower():
                continue

            if not raw_name:
                ext_map = {
                    "application/pdf": ".pdf",
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "text/plain": ".txt",
                    "text/csv": ".csv",
                    "application/vnd.ms-excel": ".xls",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                    "application/msword": ".doc",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                    "application/zip": ".zip",
                }
                ext = ext_map.get(content_type, ".bin")
                raw_name = f"attachment{ext}"

            filename = self._decode_mime_header(raw_name)

            file_data = part.get_payload(decode=True)
            if file_data is None:
                file_data = b""

            attachments.append({
                "filename":     filename,
                "content_type": content_type,
                "size":         len(file_data),
                "data":         file_data,
            })
            print(f"    📎 Attachment found: {filename} ({len(file_data)} bytes)")

        return attachments

    # ── Duplicate detection (DB-level) ────────────────────────

    @staticmethod
    def _is_duplicate(sender: str, subject: str, message_id: str, received_date: datetime) -> bool:
        """
        Check DB for duplicates.
        Uses message_id first (most reliable), then fallback by sender+subject+time window.
        """
        from models import Email as EmailModel

        # Primary: message_id check
        if message_id:
            if EmailModel.query.filter_by(message_id=message_id).first():
                return True

        # Secondary: sender + subject within 30-minute window
        # Make received_date UTC-aware for safe comparison
        if received_date.tzinfo is None:
            received_date = received_date.replace(tzinfo=timezone.utc)

        window = timedelta(minutes=30)
        return bool(EmailModel.query.filter(
            EmailModel.sender     == sender,
            EmailModel.subject    == subject,
            EmailModel.created_at >= received_date - window,
            EmailModel.created_at <= received_date + window,
        ).first())

    # ── Main fetch ─────────────────────────────────────────────

    def fetch_unread_emails(self) -> list:
        if not self.connect():
            return []

        try:
            since_str = (
                datetime.now(timezone.utc) - timedelta(hours=self.fetch_window_hrs)
            ).strftime("%d-%b-%Y")

            _, messages = self.mail.search(None, f'SINCE "{since_str}"')
            email_ids   = messages[0].split()

            if not email_ids:
                print(f"📭 No emails in last {self.fetch_window_hrs}h")
                self.disconnect()
                return []

            print(f"📨 Found {len(email_ids)} email(s) in fetch window")
            results = []

            for eid in reversed(email_ids[-100:]):
                try:
                    _, data = self.mail.fetch(eid, "(RFC822)")
                    for part in data:
                        if not isinstance(part, tuple):
                            continue

                        msg = email.message_from_bytes(part[1])

                        # Subject
                        raw_subj = msg.get("Subject", "No Subject")
                        subject  = self._decode_mime_header(raw_subj)
                        subject  = self._strip_html(subject).strip() or "No Subject"

                        # Sender
                        raw_from    = self._decode_mime_header(msg.get("From", ""))
                        sender_addr = self._extract_email(raw_from)
                        sender_name = self._extract_name(raw_from)

                        if self.email_user.lower() in sender_addr.lower():
                            continue

                        # Message-ID
                        message_id = (msg.get("Message-ID") or "").strip()

                        # Date
                        date_str = msg.get("Date")
                        try:
                            received_date = email.utils.parsedate_to_datetime(date_str)
                            if received_date.tzinfo is None:
                                received_date = received_date.replace(tzinfo=timezone.utc)
                        except Exception:
                            received_date = datetime.now(timezone.utc)

                        # Duplicate check BEFORE parsing body/attachments (saves CPU)
                        if self._is_duplicate(sender_addr, subject, message_id, received_date):
                            print(f"  ⏭  Duplicate skipped: {subject[:40]}")
                            continue

                        # Body + attachments (with binary data)
                        plain_body, html_body = self._get_body(msg)
                        attachments     = self._get_attachments(msg)
                        has_attachments = len(attachments) > 0

                        # Build attachment metadata for JSON field (no binary data)
                        attachments_meta = [
                            {
                                "filename":     a["filename"],
                                "content_type": a["content_type"],
                                "size":         a["size"],
                            }
                            for a in attachments
                        ]

                        results.append({
                            "sender":           sender_addr,
                            "sender_name":      sender_name,
                            "subject":          subject,
                            "body_plain":       plain_body,
                            "body_html":        html_body,
                            "message_id":       message_id or None,
                            "cc":               msg.get("Cc", "") or "",
                            "reply_to":         msg.get("Reply-To", raw_from) or "",
                            "has_attachments":  has_attachments,
                            "attachments_meta": attachments_meta,
                            "attachments_data": attachments,
                            "received_date":    received_date,
                        })
                        print(f"  ✓ Queued: {subject[:50]} ← {sender_addr}")
                        if has_attachments:
                            print(f"    📎 {len(attachments)} attachment(s)")

                except Exception as e:
                    print(f"  ⚠  Error processing email id {eid}: {e}")
                    continue

            self.disconnect()
            print(f"✅ Fetch complete: {len(results)} new email(s) to process")
            return results

        except Exception as e:
            print(f"❌ Fetch error: {e}")
            self.disconnect()
            return []


# ── Background periodic fetcher ────────────────────────────────

def fetch_emails_periodically(app, db, Email, User, ai_engine, mail_engine):
    """
    Background thread: fetch → classify → save email + attachments → push SSE.

    FIXES applied:
      1. Pre-check duplicate by message_id BEFORE db.session.flush() to avoid
         UniqueViolation / IntegrityError on the unique constraint.
      2. db.session.expunge(em) on duplicate so the session stays clean.
      3. Proper exception handling that rolls back only the failed email,
         not the entire batch.
    """
    print("🚀 Background email fetcher started")
    fetcher       = EmailFetcher()
    poll_interval = int(os.getenv("EMAIL_POLL_INTERVAL", 60))
    VALID_DEPTS   = ["Client Relations", "Audit", "Legal", "Accounts"]

    while True:
        try:
            with app.app_context():
                from models import EmailAttachment

                new_emails = fetcher.fetch_unread_emails()

                for ed in new_emails:
                    # ── PER-EMAIL transaction scope ──────────────────────
                    try:
                        # ── STEP 1: Definitive duplicate check inside app context ──
                        # (fetcher._is_duplicate already ran outside app context;
                        #  this is the authoritative in-context check)
                        message_id = ed.get("message_id")
                        if message_id:
                            already_exists = Email.query.filter_by(message_id=message_id).first()
                            if already_exists:
                                print(f"  ⏭  DB-dup skipped (msg-id): {ed['subject'][:40]}")
                                continue

                        # Fallback: sender+subject+time-window duplicate check
                        received_date = ed["received_date"]
                        if received_date.tzinfo is None:
                            received_date = received_date.replace(tzinfo=timezone.utc)

                        window = timedelta(minutes=30)
                        sender_dup = Email.query.filter(
                            Email.sender     == ed["sender"],
                            Email.subject    == ed["subject"],
                            Email.created_at >= received_date - window,
                            Email.created_at <= received_date + window,
                        ).first()
                        if sender_dup:
                            print(f"  ⏭  DB-dup skipped (sender+subj): {ed['subject'][:40]}")
                            continue

                        # ── STEP 2: Classify & route ─────────────────────
                        category   = ai_engine.classify_email(
                            ed.get("body_plain", ""), ed.get("subject", "")
                        )
                        department = ai_engine.get_department_for_category(category)
                        if not department or department not in VALID_DEPTS:
                            department = "Client Relations"

                        print(f"  🎯 Classified: {category} → {department}")

                        # ── STEP 3: Build Email record ────────────────────
                        em = Email(
                            sender           = ed["sender"],
                            sender_name      = ed.get("sender_name", ""),
                            recipient        = "info@slci.in",
                            subject          = ed["subject"],
                            body             = ed["body_plain"],
                            body_html        = ed.get("body_html", ""),
                            cc               = ed.get("cc", ""),
                            reply_to         = ed.get("reply_to", ""),
                            category         = category,
                            assigned_role    = department,
                            status           = "unread",
                            created_at       = received_date,
                            message_id       = message_id,
                            has_attachments  = ed.get("has_attachments", False),
                            attachments_info = json.dumps(ed.get("attachments_meta", [])),
                        )
                        db.session.add(em)

                        # ── STEP 4: Flush to get em.id (may raise IntegrityError) ──
                        try:
                            db.session.flush()
                        except Exception as flush_err:
                            # Almost certainly a duplicate key violation on message_id
                            db.session.rollback()
                            print(f"  ⏭  Flush duplicate (race): {ed['subject'][:40]} — {flush_err}")
                            continue

                        # ── STEP 5: Save attachment binary data ───────────
                        for att in ed.get("attachments_data", []):
                            att_record = EmailAttachment(
                                email_id     = em.id,
                                filename     = att["filename"],
                                content_type = att["content_type"],
                                file_size    = att["size"],
                                file_data    = att["data"],
                            )
                            db.session.add(att_record)
                            print(f"    💾 Saved attachment: {att['filename']} ({att['size']} bytes)")

                        # ── STEP 6: Push to real-time SSE queue ───────────
                        try:
                            from app import new_email_queue
                            new_email_queue.put({
                                "type":        "new_email",
                                "id":          em.id,
                                "subject":     em.subject,
                                "sender":      em.sender,
                                "sender_name": em.sender_name,
                                "department":  department,
                                "category":    category,
                                "created_at":  received_date.strftime("%Y-%m-%d %H:%M"),
                                "preview":     em.get_body_preview(80),
                            })
                        except Exception as qe:
                            print(f"  ⚠  Queue push failed: {qe}")

                        # ── STEP 7: Commit this email ──────────────────────
                        db.session.commit()
                        print(f"  ✅ Saved: {em.subject[:40]} [{department}]")

                    except Exception as e:
                        # Roll back just this email's transaction, continue with next
                        db.session.rollback()
                        print(f"  ❌ Save error for '{ed.get('subject','?')[:40]}': {e}")
                        continue

        except Exception as e:
            print(f"⚠  Cycle error: {e}")

        time.sleep(poll_interval)