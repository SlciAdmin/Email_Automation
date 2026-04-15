# ═══════════════════════════════════════════════════════════════
# FILE: ai_engine.py - UPDATED WITH NEW CATEGORIES
# ═══════════════════════════════════════════════════════════════

# Department → Email mapping (for routing display)
DEPARTMENT_EMAIL_MAP = {
    "Client Relations": "clientrelation@slci.in",
    "Audit": "audit@slci.in",
    "Legal": "legal@slci.in",
    "Accounts": "accounts@sksharma.in",
}

# Category → Department mapping (NEW categories added → Client Relations by default)
DEPARTMENT_MAPPING = {
    # === NEW PRIORITY/STATUS CATEGORIES ===
    "Reminder": "Client Relations",
    "Important": "Client Relations", 
    "Urgent": "Client Relations",
    "Delay": "Client Relations",
    "Complaint": "Client Relations",
    "No Response": "Client Relations",
    
    # === Existing Client Relations Categories ===
    "Payroll": "Client Relations", "KYC": "Client Relations", "TIC": "Client Relations",
    "New Employee": "Client Relations", "Withdrawal Form": "Client Relations",
    "Exit Employee": "Client Relations", "S&E": "Client Relations", "ESIC Code": "Client Relations",
    "PF Code": "Client Relations", "Factory Licence": "Client Relations", 
    "CLRA Registration": "Client Relations", "CLRA License": "Client Relations",
    "Death Case PF": "Client Relations", "Form 5A": "Client Relations",
    "Joint Declaration": "Client Relations", "Pension": "Client Relations",
    "Notice Information": "Client Relations", "Death Case ESIC": "Client Relations",
    "Transfer of Contribution": "Client Relations", "Arrear PF": "Client Relations",
    "Arrear ESIC": "Client Relations", "Arrear PF ESIC": "Client Relations",
    "Form 13": "Client Relations", "Bonus": "Client Relations",
    "Full & Final": "Client Relations", "Professional Tax": "Client Relations",
    "ESIC Notice": "Client Relations", "PF Notice": "Client Relations",
    "Authority Letter": "Client Relations", "Accident Case ESIC": "Client Relations",
    "Meeting": "Client Relations", "Responsibility Matrix": "Client Relations",
    "Compliance": "Client Relations",
    
    # === Audit Categories ===
    "NBD Audit": "Audit", "Compliance Visit": "Audit", "Audit Report": "Audit",
    "Internal Audit": "Audit", "External Audit": "Audit", "Statutory Audit": "Audit",
    "Tax Audit": "Audit", "Audit Finding": "Audit", "Audit Observation": "Audit",
    "Inspection Report": "Audit", "Due Diligence": "Audit", "Verification": "Audit",
    
    # === Legal Categories ===
    "Appointment Letter": "Legal", "Offer Letter": "Legal", "Policy": "Legal",
    "POSH Training": "Legal", "POSH Compliance": "Legal", "Notice": "Legal",
    "Dispute": "Legal", "Agreement": "Legal", "Contract": "Legal", "Legal Case": "Legal",
    "Court Order": "Legal", "Affidavit": "Legal", "MOU": "Legal", "NDA": "Legal",
    "Litigation": "Legal", "Arbitration": "Legal", "Legal Notice": "Legal",
    "Termination Letter": "Legal",
    
    # === Accounts Categories ===
    "Invoice": "Accounts", "Payment": "Accounts", "Billing": "Accounts",
    "Salary": "Accounts", "Refund": "Accounts", "Transaction": "Accounts",
    "Tax": "Accounts", "Receipt": "Accounts", "Credit Note": "Accounts",
    "Debit Note": "Accounts", "GST": "Accounts", "TDS": "Accounts",
    "Balance Sheet": "Accounts", "Profit & Loss": "Accounts", "Ledger": "Accounts",
    "Bank Statement": "Accounts", "Reimbursement": "Accounts", "Budget": "Accounts",
    "Expense": "Accounts", "Accounting": "Accounts",
    
    # === Default ===
    "General Inquiry": "Client Relations"
}

# Keywords for classification - NEW CATEGORIES ADDED WITH HIGH-PRIORITY KEYWORDS
KEYWORD_MAP = {
    # ════════════════════════════════════════════════════════
    # 🔔 NEW: Priority/Status Categories (Checked FIRST for better matching)
    # ════════════════════════════════════════════════════════
    
    "Reminder": [
        "reminder", "remind", "follow up", "follow-up", "gentle reminder", 
        "just reminding", "as discussed", "pending response", "awaiting reply",
        "please remember", "don't forget", "upcoming deadline", "due date",
        "this is a reminder", "kindly note", "note this", "for your reminder"
    ],
    
    "Important": [
        "important", "priority", "high priority", "critical", "essential",
        "must read", "attention required", "action required", "urgent attention",
        "please note", "important notice", "key point", "significant",
        "matter of importance", "requires immediate attention"
    ],
    
    "Urgent": [
        "urgent", "asap", "as soon as possible", "immediate", "immediately",
        "emergency", "rush", "time sensitive", "deadline today", "within hours",
        "need now", "right now", "instant", "pressing", "critical urgency",
        "urgent request", "urgent matter", "urgent attention needed"
    ],
    
    "Delay": [
        "delay", "delayed", "late", "postponed", "deferred", "behind schedule",
        "not received", "still waiting", "pending since", "overdue", "slipped",
        "timeline extended", "rescheduled", "pushed back", "not yet completed",
        "waiting for", "stuck", "hold up", "bottleneck"
    ],
    
    "Complaint": [
        "complaint", "complain", "issue", "problem", "concern", "dissatisfied",
        "not satisfied", "unhappy", "disappointed", "grievance", "feedback negative",
        "wrong", "error", "mistake", "not working", "failed", "defect",
        "poor service", "bad experience", "escalate", "escalation", "report issue"
    ],
    
    "No Response": [
        "no response", "no reply", "not responding", "ignored", "no answer",
        "haven't heard", "no update", "silent", "no feedback", "no acknowledgment",
        "waiting for response", "no one replied", "no communication", "radio silence",
        "still no reply", "no one responded", "not getting response"
    ],
    
    # ════════════════════════════════════════════════════════
    # 📋 Existing Categories (unchanged - for reference)
    # ════════════════════════════════════════════════════════
    
    "Payroll": ["payroll", "salary processing", "pay slip", "payslip", "wage", 
                "monthly salary", "payroll register", "salary sheet", "ctc"],
    "KYC": ["kyc", "know your customer", "identity proof", "id verification", 
            "aadhaar", "pan card", "passport", "kyc documents"],
    "TIC": ["tic", "tax invoice", "tax invoice certificate"],
    "New Employee": ["new employee", "onboarding", "joining", "new hire"],
    "Withdrawal Form": ["withdrawal", "withdrawal form", "pf withdrawal", "esic withdrawal"],
    "Exit Employee": ["exit", "resignation", "relieving", "full and final"],
    "ESIC Code": ["esic code", "esic registration", "esic number"],
    "PF Code": ["pf code", "pf registration", "pf number", "uan"],
    "Factory Licence": ["factory licence", "factory license", "factory registration"],
    "CLRA Registration": ["clra", "contract labour", "clra registration"],
    "CLRA License": ["clra license", "contractor license"],
    "Death Case PF": ["death case", "pf death", "nominee pf"],
    "Form 5A": ["form 5a", "pf form 5a"],
    "Joint Declaration": ["joint declaration", "jd form", "pf correction"],
    "Pension": ["pension", "eps", "pension scheme"],
    "Notice Information": ["notice", "show cause", "compliance notice"],
    "Death Case ESIC": ["esic death", "death benefit esic"],
    "Transfer of Contribution": ["transfer", "pf transfer", "contribution transfer"],
    "Arrear PF": ["arrear pf", "pf arrears", "backdated pf"],
    "Arrear ESIC": ["arrear esic", "esic arrears"],
    "Arrear PF ESIC": ["arrear", "pf esic arrears"],
    "Form 13": ["form 13", "pf transfer form"],
    "Bonus": ["bonus", "annual bonus", "statutory bonus"],
    "Full & Final": ["full and final", "f&f", "settlement"],
    "Professional Tax": ["professional tax", "pt", "pt registration"],
    "ESIC Notice": ["esic notice", "esic demand"],
    "PF Notice": ["pf notice", "pf demand", "epfo notice"],
    "Authority Letter": ["authority letter", "authorization letter"],
    "Accident Case ESIC": ["accident", "esic accident", "injury claim"],
    "Meeting": ["meeting", "schedule", "appointment"],
    "Responsibility Matrix": ["responsibility", "matrix", "ram"],
    "Compliance": ["compliance", "statutory compliance", "regulatory"],
    
    "NBD Audit": ["nbd", "nbd audit", "non banking"],
    "Compliance Visit": ["compliance visit", "inspection visit"],
    "Audit Report": ["audit report", "audit findings"],
    "Internal Audit": ["internal audit", "ia"],
    "External Audit": ["external audit", "statutory audit"],
    "Statutory Audit": ["statutory audit"],
    "Tax Audit": ["tax audit", "income tax audit"],
    "Audit Finding": ["audit finding", "observation"],
    "Audit Observation": ["observation", "audit point"],
    "Inspection Report": ["inspection", "inspection report"],
    "Due Diligence": ["due diligence", "dd"],
    "Verification": ["verification", "verify", "validate"],
    
    "Appointment Letter": ["appointment", "appointment letter", "offer"],
    "Offer Letter": ["offer letter", "job offer"],
    "Policy": ["policy", "hr policy", "company policy"],
    "POSH Training": ["posh", "sexual harassment", "posh training"],
    "POSH Compliance": ["posh compliance", "ic committee"],
    "Notice": ["legal notice", "notice", "cease and desist"],
    "Dispute": ["dispute", "conflict", "grievance"],
    "Agreement": ["agreement", "service agreement"],
    "Contract": ["contract", "employment contract"],
    "Legal Case": ["legal case", "court case", "litigation"],
    "Court Order": ["court order", "judgment", "decree"],
    "Affidavit": ["affidavit", "sworn statement"],
    "MOU": ["mou", "memorandum"],
    "NDA": ["nda", "non disclosure", "confidentiality"],
    "Litigation": ["litigation", "lawsuit"],
    "Arbitration": ["arbitration", "arbitrator"],
    "Legal Notice": ["legal notice", "lawyer notice"],
    "Termination Letter": ["termination", "dismissal", "termination letter"],
    
    "Invoice": ["invoice", "bill", "tax invoice"],
    "Payment": ["payment", "remittance", "transfer"],
    "Billing": ["billing", "invoice generation"],
    "Salary": ["salary", "payroll", "wages"],
    "Refund": ["refund", "reimbursement", "claim"],
    "Transaction": ["transaction", "bank transaction"],
    "Tax": ["tax", "gst", "tds", "income tax"],
    "Receipt": ["receipt", "payment receipt"],
    "Credit Note": ["credit note", "cn"],
    "Debit Note": ["debit note", "dn"],
    "GST": ["gst", "goods services tax"],
    "TDS": ["tds", "tax deducted"],
    "Balance Sheet": ["balance sheet", "bs"],
    "Profit & Loss": ["profit loss", "p&l", "income statement"],
    "Ledger": ["ledger", "account ledger"],
    "Bank Statement": ["bank statement", "account statement"],
    "Reimbursement": ["reimbursement", "claim reimbursement"],
    "Budget": ["budget", "budgeting"],
    "Expense": ["expense", "expenditure"],
    "Accounting": ["accounting", "accounts", "bookkeeping"],
    
    "General Inquiry": ["general", "query", "info", "help", "support", "question"]
}


def classify_email(body: str = "", subject: str = "") -> str:
    """
    Classify email into category based on keywords.
    NEW: Priority categories checked FIRST with higher weight for better matching.
    """
    if not body and not subject:
        return "General Inquiry"
    
    # Combine subject (weighted 3x) + body for matching
    text = f"{subject} {subject} {subject} {body}".lower()
    
    # Priority categories list - check these FIRST with higher scoring
    priority_categories = ["Urgent", "Important", "Reminder", "Complaint", "Delay", "No Response"]
    
    best_category = "General Inquiry"
    best_score = 0
    
    # === STEP 1: Check Priority Categories First (Higher Weight) ===
    for category in priority_categories:
        if category not in KEYWORD_MAP:
            continue
        keywords = KEYWORD_MAP[category]
        score = 0
        for kw in keywords:
            if kw in text:
                score += 5  # Higher weight for priority categories
            elif kw.split()[0] in text:
                score += 2
        if score > best_score:
            best_score = score
            best_category = category
    
    # === STEP 2: Check Other Categories (Normal Weight) ===
    for category, keywords in KEYWORD_MAP.items():
        if category in priority_categories:
            continue  # Already checked above
        score = 0
        for kw in keywords:
            if kw in text:
                score += 3
            elif kw.split()[0] in text:
                score += 1
        if score > best_score:
            best_score = score
            best_category = category
    
    return best_category


def get_department_for_category(category: str) -> str:
    """Map category to department name"""
    return DEPARTMENT_MAPPING.get(category, "Client Relations")


def get_department_users(department: str, User) -> list:
    """Get all users in a department (excluding admins)"""
    try:
        return User.query.filter_by(department=department, role="user").all()
    except Exception:
        return []