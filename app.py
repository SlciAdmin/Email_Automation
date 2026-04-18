# ═══════════════════════════════════════════════════════════════
# FILE: app.py - SLCI Email Router (FIXED & PRODUCTION-READY)
# ═══════════════════════════════════════════════════════════════

from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, Response, stream_with_context
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Email, EmailReply, DEPARTMENTS
from ai_engine import classify_email, get_department_for_category
from mail_engine import send_department_reply
from imap_fetcher import fetch_emails_periodically
from datetime import datetime, timedelta, timezone, date as date_type
import threading, os, queue, time as time_module, json, csv, io
from dotenv import load_dotenv
from flask import send_file, abort
import io

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "postgresql://postgres:SLCI123@localhost:5432/email_automation")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ✅ TWO queues: one for replies, one for NEW incoming emails
reply_queue = queue.Queue()
new_email_queue = queue.Queue()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_globals():
    """Inject common variables into all templates"""
    return {"now": datetime.now(timezone.utc), "timedelta": timedelta}


# ─────────────────────────────────────────────
# HELPER: Make datetime timezone-aware (UTC)
# ─────────────────────────────────────────────

def _make_aware(dt):
    """
    Ensure a datetime is timezone-aware (UTC).
    If already aware, return as-is.
    If naive, assume UTC.
    """
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return dt


# ─────────────────────────────────────────────
# BACKGROUND TASKS
# ─────────────────────────────────────────────

def _reminder_loop():
    """Background: Track pending emails"""
    print("⏰ Tracker started")
    while True:
        try:
            with app.app_context():
                pending = Email.query.filter(
                    Email.replied == False,
                    Email.status != "resolved"
                ).all()
                if pending:
                    print(f"  📊 {len(pending)} pending email(s) awaiting reply")
        except Exception as e:
            print(f"⚠ Tracker error: {e}")
        time_module.sleep(1800)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email_input = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email_input).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome, {user.email}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email_input = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "user")
        department = request.form.get("department", "Client Relations")

        if password != confirm_password or len(password) < 6:
            flash("Password mismatch or too short", "error")
            return redirect(url_for("signup"))

        if User.query.filter_by(email=email_input).first():
            flash("Email already registered", "error")
            return redirect(url_for("signup"))

        new_user = User(
            email=email_input,
            password=User.hash_password(password),
            role=role,
            department=department
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Account created! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html", departments=DEPARTMENTS)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard - REAL-TIME ready"""
    if current_user.role.lower() == "admin":
        all_emails = Email.query.order_by(Email.created_at.desc()).limit(300).all()
        recent_replies = EmailReply.query.order_by(EmailReply.replied_at.desc()).limit(20).all()

        stats = {
            "total_emails": Email.query.count(),
            "unassigned": Email.query.filter(Email.assigned_role.is_(None)).count(),
            "pending": Email.query.filter(
                Email.replied == False,
                Email.assigned_role.isnot(None),
                Email.status != "resolved"
            ).count(),
            "resolved": Email.query.filter(Email.replied == True).count(),
        }
        return render_template(
            "admin_dashboard.html",
            assigned_emails=all_emails,
            recent_replies=recent_replies,
            stats=stats,
            departments=DEPARTMENTS
        )
    else:
        dept_emails = Email.query.filter(
            db.or_(
                Email.assigned_role == current_user.department,
                Email.assigned_to == current_user.id
            )
        ).order_by(Email.created_at.desc()).all()

        pending_count = sum(
            1 for e in dept_emails
            if not e.replied and getattr(e, 'status', 'unread') != "resolved"
        )
        return render_template(
            "user_dashboard.html",
            assigned_emails=dept_emails,
            pending_count=pending_count
        )


@app.route("/view_email/<int:email_id>")
@login_required
def view_email(email_id):
    """View email and reply"""
    email_obj = db.session.get(Email, email_id)

    if not email_obj or not email_obj.can_user_access(current_user):
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))

    if email_obj.status == "unread":
        email_obj.status = "read"
        db.session.commit()

    replies = EmailReply.query.filter_by(email_id=email_id).order_by(EmailReply.replied_at).all()
    return render_template("view_email.html", email=email_obj, replies=replies)


@app.route("/attachment/<int:attachment_id>/view")
@login_required
def view_attachment(attachment_id):
    """Serve attachment for inline viewing in browser."""
    from models import EmailAttachment
    att = EmailAttachment.query.get_or_404(attachment_id)
    if not att.email.can_user_access(current_user):
        abort(403)
    return send_file(
        io.BytesIO(att.file_data),
        mimetype=att.content_type or "application/octet-stream",
        as_attachment=False,
        download_name=att.filename,
    )


@app.route("/attachment/<int:attachment_id>/download")
@login_required
def download_attachment(attachment_id):
    """Serve attachment as a download."""
    from models import EmailAttachment
    att = EmailAttachment.query.get_or_404(attachment_id)
    if not att.email.can_user_access(current_user):
        abort(403)
    return send_file(
        io.BytesIO(att.file_data),
        mimetype=att.content_type or "application/octet-stream",
        as_attachment=True,
        download_name=att.filename,
    )


@app.route("/api/email/<int:email_id>/attachments")
@login_required
def api_email_attachments(email_id):
    """Return JSON list of attachments for an email."""
    from models import Email as EmailModel, EmailAttachment
    em = EmailModel.query.get_or_404(email_id)
    if not em.can_user_access(current_user):
        abort(403)
    attachments = EmailAttachment.query.filter_by(email_id=email_id).all()
    return jsonify({
        "email_id": email_id,
        "count": len(attachments),
        "attachments": [
            {
                "id":           a.id,
                "filename":     a.filename,
                "content_type": a.content_type,
                "size":         a.file_size,
                "size_display": a.get_size_display(),
                "icon":         a.get_icon(),
                "viewable":     a.is_viewable_in_browser(),
                "view_url":     f"/attachment/{a.id}/view",
                "download_url": f"/attachment/{a.id}/download",
            }
            for a in attachments
        ]
    })


@app.route("/mark_read/<int:email_id>", methods=["POST"])
@login_required
def mark_read(email_id):
    """API: Mark email as read"""
    email_obj = db.session.get(Email, email_id)
    if email_obj and email_obj.can_user_access(current_user):
        email_obj.status = "read"
        db.session.commit()
    return jsonify({"success": True})


@app.route("/reply_email/<int:email_id>", methods=["POST"])
@login_required
def reply_email(email_id):
    """Send reply and mark as resolved"""
    email_obj = db.session.get(Email, email_id)

    if not email_obj or not email_obj.can_user_access(current_user):
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))

    reply_body = request.form.get("reply_body", "").strip()
    if not reply_body:
        flash("Reply cannot be empty", "error")
        return redirect(url_for("view_email", email_id=email_id))

    try:
        success = send_department_reply(
            email_obj.sender,
            email_obj.subject,
            reply_body,
            current_user
        )

        if success:
            email_obj.replied = True
            email_obj.reply_sent_at = datetime.now(timezone.utc)
            email_obj.reply_by = current_user.id
            email_obj.reply_content = reply_body
            email_obj.status = "resolved"

            db.session.add(EmailReply(
                email_id=email_obj.id,
                replied_by=current_user.id,
                reply_content=reply_body,
                department=current_user.department
            ))
            db.session.commit()

            reply_queue.put({
                "type": "reply",
                "department": current_user.department,
                "user_email": current_user.email,
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "reply_preview": reply_body[:100],
                "replied_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "subject": email_obj.subject,
                "email_id": email_obj.id
            })

            flash("✅ Reply sent", "success")
        else:
            flash("❌ Failed to send reply", "error")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error: {str(e)}", "error")

    return redirect(url_for("dashboard"))


@app.route("/compose_email", methods=["GET", "POST"])
@login_required
def compose_email():
    """Compose new email"""
    if request.method == "POST":
        to_email = request.form.get("to_email", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if not to_email or not subject or not body:
            flash("All fields are required", "error")
            return redirect(url_for("compose_email"))

        try:
            success = send_department_reply(to_email, subject, body, current_user)
            if success:
                email_obj = Email(
                    sender="info@slci.in",
                    sender_name=current_user.email,
                    recipient=to_email,
                    subject=subject,
                    body=body,
                    category="Manual Send",
                    assigned_role=current_user.department,
                    assigned_to=current_user.id,
                    assigned_at=datetime.now(timezone.utc),
                    status="resolved",
                    replied=True,
                    reply_sent_at=datetime.now(timezone.utc),
                    reply_by=current_user.id,
                    reply_content=body
                )
                db.session.add(email_obj)
                db.session.commit()
                flash(f"✅ Email sent to {to_email}", "success")
            else:
                flash("❌ Failed to send", "error")
        except Exception as e:
            flash(f"❌ Error: {str(e)}", "error")
        return redirect(url_for("dashboard"))

    return render_template("compose_email.html")


@app.route("/email_stream")
@login_required
def email_stream():
    """Server-Sent Events for new incoming emails"""
    def generate():
        while True:
            try:
                email_data = new_email_queue.get(timeout=30)
                if current_user.role == "admin" or email_data.get("department") == current_user.department:
                    yield f"data: {json.dumps(email_data)}\n\n"
            except queue.Empty:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
            except GeneratorExit:
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@app.route("/reply_stream")
@login_required
def reply_stream():
    """SSE for real-time reply notifications (admin only)"""
    if current_user.role != "admin":
        return jsonify({"error": "Access denied"}), 403

    def generate():
        while True:
            try:
                reply_data = reply_queue.get(timeout=30)
                yield f"data: {json.dumps(reply_data)}\n\n"
            except queue.Empty:
                yield "data: {}\n\n"
            except GeneratorExit:
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/force_gmail_check", methods=["POST"])
@login_required
def force_gmail_check():
    """Admin: Manually trigger email fetch"""
    if current_user.role != "admin":
        return jsonify({"success": False}), 403

    try:
        from imap_fetcher import EmailFetcher
        fetcher = EmailFetcher()
        new_emails = fetcher.fetch_unread_emails()
        count = 0

        for ed in new_emails:
            # Flexible duplicate check
            existing = None
            if ed.get("message_id"):
                existing = Email.query.filter_by(message_id=ed["message_id"]).first()

            if not existing:
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                existing = Email.query.filter(
                    Email.sender == ed["sender"],
                    Email.subject == ed["subject"],
                    Email.created_at >= one_hour_ago
                ).first()

            if existing:
                continue

            category = classify_email(ed.get("body_plain", ""), ed.get("subject", ""))
            department = get_department_for_category(category)
            if not department or department not in DEPARTMENTS:
                department = "Client Relations"

            em = Email(
                sender=ed["sender"],
                sender_name=ed.get("sender_name", ""),
                recipient="info@slci.in",
                subject=ed["subject"],
                body=ed["body_plain"],
                body_html=ed.get("body_html", ""),
                category=category,
                assigned_role=department,
                status="unread",
                created_at=ed["received_date"],
                message_id=ed.get("message_id"),
                has_attachments=ed.get("has_attachments", False),
                attachments_info=ed.get("attachments", []),
                cc=ed.get("cc", ""),
                reply_to=ed.get("reply_to", "")
            )
            db.session.add(em)
            count += 1

            new_email_queue.put({
                "type": "new_email",
                "id": em.id,
                "subject": em.subject,
                "sender": em.sender,
                "sender_name": em.sender_name,
                "department": department,
                "category": category,
                "created_at": em.created_at.strftime("%Y-%m-%d %H:%M"),
                "preview": em.get_body_preview(80)
            })

        if count:
            db.session.commit()

        return jsonify({"success": True, "new_emails": count})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/check_new_emails")
@login_required
def check_new_emails():
    """API: Check for recent unread emails"""
    one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    count = Email.query.filter(
        Email.created_at > one_min_ago,
        Email.status == "unread"
    ).count()
    return jsonify({"new_emails": count})


@app.route("/export_emails", methods=["GET", "POST"])
@login_required
def export_emails():
    """Export emails to CSV"""
    if current_user.role != "admin":
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        start_date = request.form.get("start_date") or (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = request.form.get("end_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        query = Email.query.filter(
            Email.created_at >= datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
            Email.created_at <= datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        )

        category = request.form.get("category", "all")
        department = request.form.get("department", "all")
        status_filter = request.form.get("status", "all")

        if category != "all":
            query = query.filter(Email.category == category)
        if department != "all":
            query = query.filter(Email.assigned_role == department)

        if status_filter == "pending":
            query = query.filter(
                Email.replied == False,
                Email.status != "resolved"
            )
        elif status_filter == "resolved":
            query = query.filter(Email.replied == True)

        emails = query.order_by(Email.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Subject", "Category", "Department", "Sender", "Status", "Replied By"])

        for em in emails:
            writer.writerow([
                em.created_at.strftime("%Y-%m-%d %H:%M"),
                em.subject,
                em.category,
                em.assigned_role or "Unassigned",
                em.sender,
                "Resolved" if em.replied else "Pending",
                em.assignee.email if em.assignee else ""
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=emails_export_{datetime.now().strftime('%Y%m%d')}.csv"}
        )

    categories = db.session.query(Email.category).distinct().all()
    users = User.query.filter_by(role="user").all()
    return render_template(
        "export_emails.html",
        categories=[c[0] for c in categories if c[0]],
        departments=DEPARTMENTS,
        users=users,
        now=datetime.now(timezone.utc),
        timedelta=timedelta
    )


# ─────────────────────────────────────────────
# CATEGORY ANALYTICS APIs
# ─────────────────────────────────────────────

def _parse_filter_dates(filter_type, from_str='', to_str=''):
    """Return (start_dt, end_dt) as UTC-aware datetimes based on filter type."""
    now = datetime.now(timezone.utc)
    if filter_type == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
    elif filter_type == 'week':
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
    elif filter_type == 'month':
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
    elif filter_type == 'custom' and from_str and to_str:
        try:
            start = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end   = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) \
                      .replace(hour=23, minute=59, second=59)
        except ValueError:
            start = now - timedelta(days=30)
            end   = now
    else:
        start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        end   = now
    return start, end


@app.route("/api/category_stats")
@login_required
def api_category_stats():
    if current_user.role != "admin":
        return jsonify({"error": "Access denied"}), 403

    filter_type = request.args.get("filter", "month")
    from_str    = request.args.get("from",   "")
    to_str      = request.args.get("to",     "")

    start, end = _parse_filter_dates(filter_type, from_str, to_str)

    from models import Email as EmailModel
    rows = (
        db.session.query(
            EmailModel.category,
            EmailModel.assigned_role,
            EmailModel.replied,
        )
        .filter(EmailModel.created_at >= start, EmailModel.created_at <= end)
        .all()
    )

    cat_map = {}
    for category, dept, replied in rows:
        cat = category or "General Inquiry"
        if cat not in cat_map:
            cat_map[cat] = {"category": cat, "department": dept or "", "total": 0, "replied": 0, "pending": 0}
        cat_map[cat]["total"]   += 1
        if replied:
            cat_map[cat]["replied"] += 1
        else:
            cat_map[cat]["pending"] += 1

    categories = sorted(cat_map.values(), key=lambda x: x["total"], reverse=True)

    total   = sum(c["total"]   for c in categories)
    replied = sum(c["replied"] for c in categories)
    pending = sum(c["pending"] for c in categories)

    return jsonify({
        "total":      total,
        "replied":    replied,
        "pending":    pending,
        "categories": categories,
    })


@app.route("/api/category_detail")
@login_required
def api_category_detail():
    if current_user.role != "admin":
        return jsonify({"error": "Access denied"}), 403

    category    = request.args.get("category", "")
    filter_type = request.args.get("filter", "month")
    from_str    = request.args.get("from",   "")
    to_str      = request.args.get("to",     "")

    if not category:
        return jsonify({"error": "category param required"}), 400

    start, end = _parse_filter_dates(filter_type, from_str, to_str)

    from models import Email as EmailModel
    emails = (
        EmailModel.query
        .filter(
            EmailModel.category    == category,
            EmailModel.created_at >= start,
            EmailModel.created_at <= end,
        )
        .order_by(EmailModel.created_at.desc())
        .limit(200)
        .all()
    )

    total   = len(emails)
    replied = sum(1 for e in emails if e.replied)
    pending = total - replied

    email_list = [
        {
            "id":      e.id,
            "subject": e.subject or "No Subject",
            "sender":  e.sender  or "",
            "date":    e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "",
            "replied": bool(e.replied),
            "dept":    e.assigned_role or "Unrouted",
        }
        for e in emails
    ]

    return jsonify({
        "category": category,
        "total":    total,
        "replied":  replied,
        "pending":  pending,
        "emails":   email_list,
    })


@app.route("/api/email_stats")
@login_required
def api_email_stats():
    """Quick stats for export page header."""
    if current_user.role != "admin":
        return jsonify({"error": "Access denied"}), 403

    days = int(request.args.get("days", 30))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    from models import Email as EmailModel
    total      = EmailModel.query.filter(EmailModel.created_at >= since).count()
    unassigned = EmailModel.query.filter(EmailModel.created_at >= since, EmailModel.assigned_role.is_(None)).count()
    resolved   = EmailModel.query.filter(EmailModel.created_at >= since, EmailModel.replied == True).count()

    return jsonify({"total": total, "unassigned": unassigned, "resolved": resolved})


# ─────────────────────────────────────────────
# FMS ROUTES
# ─────────────────────────────────────────────

@app.route("/fms")
@login_required
def fms_dashboard():
    if current_user.role != "admin":
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))
    return render_template("fms.html")


@app.route("/api/fms_data")
@login_required
def api_fms_data():
    """
    FMS data API — FIXED:
      1. Timezone-aware datetime subtraction (offset-naive vs offset-aware bug fixed)
      2. Proper company name extraction
      3. All emails within last 90 days grouped by company+category
    """
    if current_user.role != "admin":
        return jsonify({"error": "Access denied"}), 403

    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc - timedelta(days=90)

    emails = (
        Email.query
        .filter(Email.created_at >= cutoff)
        .order_by(Email.created_at.desc())
        .all()
    )

    # ── Company name extraction ──────────────────────────────────
    def extract_company(em):
        """
        Best-effort company name from sender_name / sender email.
        Priority:
          1. sender_name if it looks like a company (no @ sign, non-trivial)
          2. Domain from sender email, cleaned up
        """
        name = (em.sender_name or "").strip()

        # If sender_name looks valid (not just an email address)
        if name and "@" not in name and len(name) > 2:
            for pfx in ["Mr. ", "Mrs. ", "Ms. ", "Dr. ", "Er. "]:
                if name.startswith(pfx):
                    name = name[len(pfx):]
            return name.strip() or "Unknown"

        # Fall back to domain-based company name
        sender = em.sender or ""
        if "@" in sender:
            domain = sender.split("@")[-1]
            domain = (domain
                      .replace(".com", "").replace(".in", "")
                      .replace(".net", "").replace(".org", "")
                      .replace(".co", ""))
            company = domain.replace(".", " ").replace("-", " ").replace("_", " ").title().strip()
            return company if company else "Unknown"

        return "Unknown"

    # ── Group: (company_name, category) → email list ────────────
    company_map = {}

    for em in emails:
        company = extract_company(em)
        cat     = em.category or "General Inquiry"
        dept    = em.assigned_role or "Client Relations"
        key     = (company, cat)

        if key not in company_map:
            company_map[key] = {
                "name":   company,
                "cat":    cat,
                "dept":   dept,
                "emails": []
            }

        # ── FIX: Make created_at timezone-aware before subtraction ──
        created_at = em.created_at
        if created_at is not None:
            if created_at.tzinfo is None:
                # naive datetime stored in DB — assume UTC
                created_at = created_at.replace(tzinfo=timezone.utc)
            days_old = (now_utc - created_at).days
        else:
            days_old = 0

        # Status: replied → 'replied', else >3 days without reply → 'overdue', else 'pending'
        if em.replied:
            status = "replied"
        elif days_old >= 3:
            status = "overdue"
        else:
            status = "pending"

        # Format replied_at safely
        replied_at_str = None
        if em.reply_sent_at:
            rsa = em.reply_sent_at
            if rsa.tzinfo is None:
                rsa = rsa.replace(tzinfo=timezone.utc)
            replied_at_str = rsa.strftime("%Y-%m-%d %H:%M")

        # Timestamp for JS sorting
        date_ts = int(created_at.timestamp() * 1000) if created_at else 0

        company_map[key]["emails"].append({
            "id":         em.id,
            "subject":    em.subject or "No Subject",
            "sender":     em.sender or "",
            "date":       created_at.strftime("%Y-%m-%d %H:%M") if created_at else "",
            "date_ts":    date_ts,
            "replied":    bool(em.replied),
            "replied_at": replied_at_str,
            "status":     status,
            "days_old":   days_old,
        })

    result = list(company_map.values())

    # ── Aggregate stats ──────────────────────────────────────────
    total_emails  = sum(len(c["emails"]) for c in result)
    total_replied = sum(sum(1 for e in c["emails"] if e["replied"])              for c in result)
    total_pending = sum(sum(1 for e in c["emails"] if e["status"] == "pending")  for c in result)
    total_overdue = sum(sum(1 for e in c["emails"] if e["status"] == "overdue")  for c in result)

    return jsonify({
        "companies": result,
        "stats": {
            "total_emails":    total_emails,
            "replied":         total_replied,
            "pending":         total_pending,
            "overdue":         total_overdue,
            "total_companies": len(result),
        }
    })


@app.route("/get_reply_history/<int:email_id>")
@login_required
def get_reply_history(email_id):
    """API: Check if there are new replies for an email (used by view_email polling)"""
    email_obj = db.session.get(Email, email_id)
    if not email_obj or not email_obj.can_user_access(current_user):
        return jsonify({"success": False})
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────
def _create_default_users():
    """Create default admin/department users"""
    defaults = [
        ("info@slci.in",              "INFO@123",     "admin", "Admin"),
        ("clientrelation@slci.in",    "CR@123",       "user",  "Client Relations"),
        ("audit@slci.in",             "AUDIT@123",    "user",  "Audit"),
        ("legal@slci.in",             "LEGAL@123",    "user",  "Legal"),
        ("accounts@sksharma.in",      "ACCOUNTS@123", "user",  "Accounts"),
    ]
    for email_addr, password, role, dept in defaults:
        if not User.query.filter_by(email=email_addr).first():
            db.session.add(User(
                email=email_addr,
                password=User.hash_password(password),
                role=role,
                department=dept
            ))
            print(f"  ✓ Created: {role} - {email_addr}")
    db.session.commit()

def _init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        _create_default_users()

# Initialize DB on startup
_init_db()

def _start_background_threads():
    """Start background tasks ONLY in production"""
    # Only start in production (not in debug mode)
    if not app.debug:
        import ai_engine, mail_engine
        threading.Thread(
            target=fetch_emails_periodically,
            args=(app, db, Email, User, ai_engine, mail_engine),
            daemon=True,
            name="email_fetcher"
        ).start()
        threading.Thread(
            target=_reminder_loop,
            daemon=True,
            name="tracker"
        ).start()
        print("✅ Background threads started (Production Mode)")

# Start background threads
_start_background_threads()

# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port, threaded=True)