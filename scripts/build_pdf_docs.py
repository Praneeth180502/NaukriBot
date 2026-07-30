"""
Robust PDF Generator using PyMuPDF (fitz).
Uses standard built-in fonts ("helv", "courier") with direct page.insert_text() rendering.
"""
from pathlib import Path
import fitz

def hex_color(hex_str: str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def wrap_text(text: str, max_chars: int = 80) -> list[str]:
    """Wrap string into lines of max_chars length."""
    words = text.split()
    lines = []
    curr = []
    curr_len = 0
    for w in words:
        if curr_len + len(w) + 1 > max_chars:
            lines.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
        else:
            curr.append(w)
            curr_len += len(w) + 1
    if curr:
        lines.append(" ".join(curr))
    return lines

def create_pdf():
    pdf_path = Path("docs/Naukribot_Architecture_and_Workflow.pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()

    pw, ph = 595, 842  # A4 size
    margin = 40

    # Colors
    C_PRIMARY   = hex_color("#1A365D")  # Deep Navy
    C_SECONDARY = hex_color("#2B6CB0")  # Steel Blue
    C_TEXT      = hex_color("#1A202C")  # Dark Text
    C_MUTED     = hex_color("#4A5568")  # Slate Gray
    C_BG        = hex_color("#F7FAFC")  # Light Gray
    C_BORDER    = hex_color("#CBD5E0")  # Border Gray
    C_SUCCESS   = hex_color("#2F855A")  # Green
    C_WHITE     = (1.0, 1.0, 1.0)

    TOTAL_PAGES = 5

    def add_header_footer(page, page_num):
        # Header line
        shape = page.new_shape()
        shape.draw_line(fitz.Point(margin, 35), fitz.Point(pw - margin, 35))
        shape.finish(color=C_BORDER, width=0.75)
        shape.commit()

        page.insert_text(fitz.Point(margin, 28), "Naukribot - Complete System Architecture & Workflow", fontsize=8.5, fontname="helv", color=C_MUTED)

        # Footer line
        shape_f = page.new_shape()
        shape_f.draw_line(fitz.Point(margin, ph - 35), fitz.Point(pw - margin, ph - 35))
        shape_f.finish(color=C_BORDER, width=0.75)
        shape_f.commit()

        page.insert_text(fitz.Point(margin, ph - 22), "Naukri.com Automated Job Hunter Agent (v2.0)", fontsize=8.5, fontname="helv", color=C_MUTED)
        page.insert_text(fitz.Point(pw - margin - 60, ph - 22), f"Page {page_num} of {TOTAL_PAGES}", fontsize=8.5, fontname="helv", color=C_MUTED)

    def draw_box(page, rect, fill_color=C_BG, border_color=C_BORDER, width=0.75):
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=border_color, fill=fill_color, width=width)
        shape.commit()

    def draw_arrow(page, x, y, length=10):
        shape = page.new_shape()
        shape.draw_line(fitz.Point(x, y), fitz.Point(x, y + length))
        shape.draw_line(fitz.Point(x - 3, y + length - 3), fitz.Point(x, y + length))
        shape.draw_line(fitz.Point(x + 3, y + length - 3), fitz.Point(x, y + length))
        shape.finish(color=C_SECONDARY, width=1)
        shape.commit()

    # =========================================================================
    # PAGE 1: TITLE & SYSTEM ARCHITECTURE DIAGRAM
    # =========================================================================
    p1 = doc.new_page(width=pw, height=ph)

    # Title Box
    t_rect = fitz.Rect(margin, 45, pw - margin, 115)
    draw_box(p1, t_rect, fill_color=hex_color("#EBF8FF"), border_color=C_SECONDARY, width=1.5)

    p1.insert_text(fitz.Point(margin + 15, 72), "Naukribot - System Architecture & Workflow", fontsize=15, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 15, 95), "Production-Grade Autonomous Job Discovery, AI Vector Matching & Auto-Apply System", fontsize=9.5, fontname="helv", color=C_SECONDARY)

    # Section 1 Header
    p1.insert_text(fitz.Point(margin, 138), "1. High-Level System Architecture Diagram", fontsize=12, fontname="helv", color=C_PRIMARY)

    # Box A: Interfaces
    b_if = fitz.Rect(margin + 10, 150, margin + 240, 215)
    draw_box(p1, b_if, fill_color=hex_color("#FEFCBF"), border_color=hex_color("#D69E2E"))
    p1.insert_text(fitz.Point(margin + 18, 168), "User & Notification Interfaces", fontsize=9.5, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 18, 185), "- Telegram Bot Client (Real-time Alerts)", fontsize=8.5, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 18, 200), "- FastAPI Web Dashboard (Uvicorn REST UI)", fontsize=8.5, fontname="helv", color=C_TEXT)

    # Box B: Entrypoint
    b_ep = fitz.Rect(margin + 265, 150, pw - margin - 10, 215)
    draw_box(p1, b_ep, fill_color=hex_color("#E9D8FD"), border_color=hex_color("#805AD5"))
    p1.insert_text(fitz.Point(margin + 273, 168), "Entrypoint & Scheduler", fontsize=9.5, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 273, 185), "- main.py Application Entry (Typer CLI)", fontsize=8.5, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 273, 200), "- APScheduler (Cron Discovery Cycles)", fontsize=8.5, fontname="helv", color=C_TEXT)

    draw_arrow(p1, margin + 125, 215, 15)
    draw_arrow(p1, pw - margin - 125, 215, 15)

    # Box C: Core Agent
    b_ag = fitz.Rect(margin + 10, 230, pw - margin - 10, 285)
    draw_box(p1, b_ag, fill_color=hex_color("#BEE3F8"), border_color=C_SECONDARY, width=1.5)
    p1.insert_text(fitz.Point(margin + 20, 248), "Core Agent Orchestrator: JobHunterAgent (app/agents/job_hunter_agent.py)", fontsize=10, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 20, 268), "Orchestrates cycle execution: Scrape -> Parse Resume -> AI Vector Score -> Auto-Apply -> Save DB -> Alerts", fontsize=8.5, fontname="helv", color=C_TEXT)

    draw_arrow(p1, margin + 85, 285, 15)
    draw_arrow(p1, margin + 255, 285, 15)
    draw_arrow(p1, pw - margin - 85, 285, 15)

    # Box D: Scraper
    b_sc = fitz.Rect(margin + 5, 300, margin + 175, 400)
    draw_box(p1, b_sc, fill_color=hex_color("#C6F6D5"), border_color=C_SUCCESS)
    p1.insert_text(fitz.Point(margin + 12, 318), "Scraper & Stealth Engine", fontsize=9, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 12, 335), "- Playwright Chrome Engine", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 12, 350), "- playwright-stealth Polyfills", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 12, 365), "- _STEALTH_JS Fingerprinting", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 12, 380), "- Cookie Session Cache", fontsize=8, fontname="helv", color=C_TEXT)

    # Box E: AI Engine
    b_ai = fitz.Rect(margin + 185, 300, pw - margin - 185, 400)
    draw_box(p1, b_ai, fill_color=hex_color("#FED7D7"), border_color=hex_color("#E53E3E"))
    p1.insert_text(fitz.Point(margin + 192, 318), "AI & NLP Core", fontsize=9, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(margin + 192, 335), "- PyMuPDF & SpaCy NLP", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 192, 350), "- sentence-transformers", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 192, 365), "- FAISS 384-dim Vector DB", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(margin + 192, 380), "- Feedback Learning Engine", fontsize=8, fontname="helv", color=C_TEXT)

    # Box F: Persistence
    b_db = fitz.Rect(pw - margin - 175, 300, pw - margin - 5, 400)
    draw_box(p1, b_db, fill_color=hex_color("#FEEBC8"), border_color=hex_color("#DD6B20"))
    p1.insert_text(fitz.Point(pw - margin - 168, 318), "Persistence Layer", fontsize=9, fontname="helv", color=C_PRIMARY)
    p1.insert_text(fitz.Point(pw - margin - 168, 335), "- SQLite Database", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(pw - margin - 168, 350), "- SQLAlchemy 2.0 ORM", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(pw - margin - 168, 365), "- Dataclass ORM Snapshots", fontsize=8, fontname="helv", color=C_TEXT)
    p1.insert_text(fitz.Point(pw - margin - 168, 380), "- Job & Application Tables", fontsize=8, fontname="helv", color=C_TEXT)

    # Section 2: Stack Table
    p1.insert_text(fitz.Point(margin, 425), "2. Core Technology Stack", fontsize=12, fontname="helv", color=C_PRIMARY)

    stack = [
        ("Web Automation", "Playwright (Python Async API), playwright-stealth, BeautifulSoup4"),
        ("AI Vector Embeddings", "sentence-transformers/all-MiniLM-L6-v2 (384-dim), FAISS vector store"),
        ("NLP & Resume Parsing", "PyMuPDF (fitz), spaCy (en_core_web_sm), Skill Taxonomy Matcher"),
        ("Backend & API Server", "FastAPI, Uvicorn (ASGI), Pydantic v2, Pydantic-Settings"),
        ("Database & ORM", "SQLite 3, SQLAlchemy 2.0 (ORM Session-safe Dataclasses)"),
        ("Scheduler & Bot", "APScheduler (Background Cron), python-telegram-bot (v21 async)")
    ]

    ty = 435
    for layer, tech in stack:
        draw_box(p1, fitz.Rect(margin, ty, margin + 135, ty + 20), fill_color=hex_color("#E2E8F0"), border_color=C_BORDER)
        draw_box(p1, fitz.Rect(margin + 140, ty, pw - margin, ty + 20), fill_color=C_BG, border_color=C_BORDER)

        p1.insert_text(fitz.Point(margin + 8, ty + 14), layer, fontsize=8.5, fontname="helv", color=C_PRIMARY)
        p1.insert_text(fitz.Point(margin + 148, ty + 14), tech, fontsize=8.5, fontname="helv", color=C_TEXT)
        ty += 23

    # Section 3: Operational Features
    p1.insert_text(fitz.Point(margin, 588), "3. Operational Features Summary", fontsize=12, fontname="helv", color=C_PRIMARY)

    feats = [
        ("Chrome Stealth Scraping", "Uses real installed Chrome with JS polyfills overriding navigator.webdriver, permissions, and browser flags to pass Naukri anti-bot checks."),
        ("Session Cookie Cache", "Saves login cookies to data/cache/naukri_session.json. Automatically restores sessions without repeating manual logins."),
        ("Semantic Vector Match", "Embeds candidate resume and job descriptions into a 384-dimensional FAISS index for high-precision semantic matching."),
        ("Chatbot Questionnaire Solver", "Intercepts post-apply recruiter screening popups during auto-apply and answers questions based on profile tags."),
        ("Telegram Bot & Dashboard", "Sends instant notifications with apply buttons to Telegram and exposes real-time analytics on http://localhost:8000.")
    ]

    fy = 605
    for title, desc in feats:
        p1.insert_text(fitz.Point(margin + 5, fy), f"- {title}:", fontsize=9, fontname="helv", color=C_PRIMARY)
        lines = wrap_text(desc, max_chars=80)
        ly = fy
        for line in lines:
            p1.insert_text(fitz.Point(margin + 160, ly), line, fontsize=8.2, fontname="helv", color=C_TEXT)
            ly += 12
        fy += max(28, len(lines) * 12 + 6)

    add_header_footer(p1, 1)

    # =========================================================================
    # PAGE 2: VISUAL WORKFLOW FLOWCHART (25 STEPS)
    # =========================================================================
    p2 = doc.new_page(width=pw, height=ph)

    p2.insert_text(fitz.Point(margin, 55), "4. System Execution Workflow (25-Step Visual Flowchart)", fontsize=13, fontname="helv", color=C_PRIMARY)

    wf_data = [
        ("PHASE 1: System Bootstrap & Initialization", hex_color("#EBF8FF"), hex_color("#3182CE"), [
            "1. Launch application via main.py (CLI / Background)",
            "2. Initialize SQLite tables via SQLAlchemy ORM (init_db())",
            "3. Parse candidate resume text & extract skills (PyMuPDF / SpaCy)",
            "4. Pre-load FAISS vector embedding model (SentenceTransformers)",
            "5. Start background APScheduler, Telegram bot & FastAPI server"
        ]),
        ("PHASE 2: Playwright Stealth Search & Discovery", hex_color("#E6FFFA"), hex_color("#319795"), [
            "6. Trigger discovery cycle every N minutes via APScheduler",
            "7. Launch Playwright browser using real Chrome channel",
            "8. Inject stealth JS scripts to override webdriver & browser flags",
            "9. Restore authenticated session cookies from data/cache",
            "10. Execute search matrix (Target Roles x Preferred Locations)",
            "11. Extract raw job card metadata from search result pages"
        ]),
        ("PHASE 3: Filtering & Database Persistence", hex_color("#FEFCBF"), hex_color("#D69E2E"), [
            "12. Check external job ID against SQLite database (Deduplication)",
            "13. Apply hard experience & location bounds filtering",
            "14. Save valid new jobs to database as session-safe JobData objects"
        ]),
        ("PHASE 4: AI Matching & Ranking Engine", hex_color("#FED7D7"), hex_color("#E53E3E"), [
            "15. Generate FAISS vector embedding for scraped job text",
            "16. Compute cosine similarity between job & resume embeddings",
            "17. Calculate skill fit, experience fit & posting freshness scores",
            "18. Apply historical user feedback boost (Learning Engine)",
            "19. Store final match score (0 - 100%) in SQLite database"
        ]),
        ("PHASE 5: Auto-Apply & Real-Time Alerts", hex_color("#C6F6D5"), hex_color("#2F855A"), [
            "20. Filter roles meeting match threshold (Score >= Threshold / Entry)",
            "21. Navigate to job application URL via Playwright",
            "22. Verify direct 1-Click apply eligibility",
            "23. Click Apply & solve recruiter chatbot forms (ChatbotHandler)",
            "24. Update application status to 'Applied' in SQLite DB",
            "25. Dispatch instant Telegram notification & refresh Web Dashboard"
        ])
    ]

    wfy = 70
    for p_title, bg_c, b_c, steps in wf_data:
        box_h = 24 + len(steps) * 15
        draw_box(p2, fitz.Rect(margin, wfy, pw - margin, wfy + box_h), fill_color=bg_c, border_color=b_c, width=1)

        p2.insert_text(fitz.Point(margin + 12, wfy + 16), p_title, fontsize=9.5, fontname="helv", color=C_PRIMARY)

        sy = wfy + 32
        for st in steps:
            p2.insert_text(fitz.Point(margin + 20, sy), f"- {st}", fontsize=8.2, fontname="helv", color=C_TEXT)
            sy += 14

        wfy += box_h + 8
        if wfy < 750 and p_title != wf_data[-1][0]:
            draw_arrow(p2, pw / 2, wfy - 6, 5)

    add_header_footer(p2, 2)

    # =========================================================================
    # PAGE 3: UNCOVERING HIDDEN JOBS & SCRAPER STEALTH SPECIFICATIONS
    # =========================================================================
    p3 = doc.new_page(width=pw, height=ph)

    p3.insert_text(fitz.Point(margin, 55), "5. Strategies for Uncovering Hidden Jobs on Naukri", fontsize=13, fontname="helv", color=C_PRIMARY)

    p3.insert_text(
        fitz.Point(margin, 75),
        "Naukri.com search caps results at Page 50 (1,000 jobs). Roles past page 50 or in candidate feeds become hidden.",
        fontsize=8.5, fontname="helv", color=C_TEXT
    )

    strategies = [
        ("1. 24-Hour Freshness Filtering (freshness=1)", "Over 80% of applicants apply within 48 hours. Appending freshness=1 to search URLs isolates jobs posted in the last 24h, bypassing page 50 pagination cutoffs."),
        ("2. Exact Boolean Query Parameters (qp)", "Standard UI search uses loose keyword matching. Using explicit URL parameters (qp=\"Machine Learning\" AND (\"PyTorch\" OR \"TensorFlow\") NOT \"Intern\") exposes precise unlisted job postings."),
        ("3. Authenticated Recommendation Feed Scraping", "Naukri maintains an unindexed matching feed at /mnjuser/recommendedjobs. Naukribot scrapes this feed post-login to access personalized job recommendations."),
        ("4. Daily Profile Activity Refresh", "Recruiters filter candidate searches by 'Active in last 7 days'. Re-uploading your resume daily touches your lastUpdatedTimestamp, bringing unlisted recruiter outbound invites."),
        ("5. Google X-Ray Search Queries (Google Dorks)", "Recruiter landing pages are indexed by Google before appearing in search. Queries like site:naukri.com/job-listings \"Machine Learning Engineer\" uncover hidden direct URLs.")
    ]

    sy3 = 90
    for title, text in strategies:
        draw_box(p3, fitz.Rect(margin, sy3, pw - margin, sy3 + 52), fill_color=C_BG, border_color=C_BORDER)

        p3.insert_text(fitz.Point(margin + 10, sy3 + 16), title, fontsize=9.5, fontname="helv", color=C_PRIMARY)
        lines = wrap_text(text, max_chars=95)
        ly = sy3 + 30
        for l in lines:
            p3.insert_text(fitz.Point(margin + 10, ly), l, fontsize=8.2, fontname="helv", color=C_TEXT)
            ly += 11
        sy3 += 58

    # Section 6: Stealth Code
    p3.insert_text(fitz.Point(margin, sy3 + 15), "6. Scraper Stealth & Anti-Bot Evasion Specifications", fontsize=12, fontname="helv", color=C_PRIMARY)

    draw_box(p3, fitz.Rect(margin, sy3 + 25, pw - margin, 785), fill_color=hex_color("#FAFAFA"), border_color=C_BORDER)

    stealth_lines = [
        "// _STEALTH_JS Script Injected into Every Playwright Page Context:",
        "1. navigator.webdriver Override  : Object.defineProperty(navigator, 'webdriver', { get: () => undefined });",
        "2. Chrome Runtime Masking        : window.chrome = { runtime: {} };",
        "3. Plugin Array Spoofing         : Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });",
        "4. Language & Platform Spoofing  : Languages: ['en-US', 'en'], Platform: 'Win32'",
        "5. Permission Interception      : Intercepts navigator.permissions.query for notifications",
        "",
        "Chromium Launch Arguments:",
        "- --disable-blink-features=AutomationControlled",
        "- --no-sandbox   - --disable-infobars   - --start-maximized"
    ]

    c_y = sy3 + 42
    for cl in stealth_lines:
        p3.insert_text(fitz.Point(margin + 12, c_y), cl, fontsize=8, fontname="courier", color=C_TEXT)
        c_y += 13

    add_header_footer(p3, 3)

    # =========================================================================
    # PAGE 4: AI FORMULA & DATABASE SCHEMA
    # =========================================================================
    p4 = doc.new_page(width=pw, height=ph)

    p4.insert_text(fitz.Point(margin, 55), "7. AI Matching & Ranking Formula", fontsize=13, fontname="helv", color=C_PRIMARY)

    draw_box(p4, fitz.Rect(margin, 65, pw - margin, 185), fill_color=hex_color("#EBF8FF"), border_color=C_SECONDARY)

    p4.insert_text(fitz.Point(margin + 12, 82), "Final Match Score Formula (0 - 100%):", fontsize=9.5, fontname="helv", color=C_PRIMARY)
    p4.insert_text(fitz.Point(margin + 12, 100), "Score = (Vector Similarity * 0.40) + (Skill Fit * 0.20) + (Exp Match * 0.15) + (Loc Match * 0.15) + (Boost * 0.10)", fontsize=8, fontname="courier", color=C_SECONDARY)

    formula_items = [
        ("Vector Similarity (40%)", "Cosine distance between resume embedding and job description embedding via FAISS."),
        ("Skill Fit (20%)", "Direct overlap count between candidate skill taxonomy and required job skill tags."),
        ("Experience & Location (30%)", "Range overlap between job requirements and candidate profile constraints."),
        ("Learning Boost (10%)", "Adjustment score learned by LearningEngine based on historical apply/ignore user actions.")
    ]

    fy4 = 118
    for title, desc in formula_items:
        p4.insert_text(fitz.Point(margin + 12, fy4), f"- {title}: {desc}", fontsize=8.2, fontname="helv", color=C_TEXT)
        fy4 += 14

    # Section 8: Database Schema
    p4.insert_text(fitz.Point(margin, 205), "8. SQLite Database Schema & Data Model", fontsize=12, fontname="helv", color=C_PRIMARY)

    schemas = [
        ("Job Table (jobs)", [
            ("id", "INTEGER (Primary Key)"),
            ("external_id", "VARCHAR (Unique Naukri Job ID)"),
            ("title / company", "VARCHAR (Job Title & Hiring Company)"),
            ("location / salary", "VARCHAR (Job Location & Compensation)"),
            ("experience_min / max", "FLOAT (Min and Max Experience Years)"),
            ("required_skills", "TEXT (JSON Array of Skill Tags)"),
            ("apply_url", "VARCHAR (Direct Apply or Detail Link)"),
            ("final_score", "FLOAT (Calculated AI Match Score 0-100)"),
            ("status", "VARCHAR ('new', 'applied', 'rejected', 'saved')")
        ]),
        ("JobApplication Table (job_applications)", [
            ("id", "INTEGER (Primary Key)"),
            ("job_id", "INTEGER (Foreign Key -> jobs.id)"),
            ("applied_at", "DATETIME (Application Submission Timestamp)"),
            ("match_score", "FLOAT (Score at Time of Application)"),
            ("status", "VARCHAR ('applied', 'failed', 'pending')"),
            ("notes", "TEXT (Auto-apply Execution Log / Notes)")
        ]),
        ("CandidateProfile Table (candidate_profiles)", [
            ("id", "INTEGER (Primary Key)"),
            ("name / email / phone", "VARCHAR (Candidate Contact Info)"),
            ("headline / summary", "TEXT (Resume Headline & Profile Summary)"),
            ("total_experience_years", "FLOAT (Calculated Experience Years)"),
            ("resume_text", "TEXT (Extracted Plain Resume Text)")
        ])
    ]

    sy4 = 222
    for tbl_name, fields in schemas:
        p4.insert_text(fitz.Point(margin, sy4), tbl_name, fontsize=9.5, fontname="helv", color=C_PRIMARY)
        sy4 += 14

        for fname, ftype in fields:
            draw_box(p4, fitz.Rect(margin + 10, sy4, margin + 160, sy4 + 14), fill_color=C_BG, border_color=C_BORDER)
            draw_box(p4, fitz.Rect(margin + 165, sy4, pw - margin, sy4 + 14), fill_color=C_WHITE, border_color=C_BORDER)

            p4.insert_text(fitz.Point(margin + 15, sy4 + 10), fname, fontsize=8, fontname="courier", color=C_PRIMARY)
            p4.insert_text(fitz.Point(margin + 172, sy4 + 10), ftype, fontsize=8, fontname="helv", color=C_TEXT)
            sy4 += 15
        sy4 += 8

    add_header_footer(p4, 4)

    # =========================================================================
    # PAGE 5: CONFIGURATION & TELEGRAM COMMANDS
    # =========================================================================
    p5 = doc.new_page(width=pw, height=ph)

    p5.insert_text(fitz.Point(margin, 55), "9. Configuration & Deployment Setup", fontsize=13, fontname="helv", color=C_PRIMARY)

    cfg_lines = [
        "Configuration Settings (config/config.yaml):",
        "",
        "search:",
        "  target_roles: ['Machine Learning Engineer', 'Full Stack Developer']",
        "  locations: ['Remote', 'Hyderabad', 'Pune']",
        "  experience_min: 0",
        "  experience_max: 3",
        "",
        "naukri:",
        "  email: 'your_email@example.com'",
        "  password: 'your_password'",
        "  headless: false               # Set true for background docker runs",
        "  max_jobs_per_cycle: 20",
        "",
        "ranking:",
        "  alert_threshold: 65.0         # Score threshold for auto-apply & alerts"
    ]

    draw_box(p5, fitz.Rect(margin, 65, pw - margin, 240), fill_color=C_BG, border_color=C_BORDER)

    cy5 = 80
    for l in cfg_lines:
        p5.insert_text(fitz.Point(margin + 12, cy5), l, fontsize=8, fontname="courier", color=C_TEXT)
        cy5 += 11

    p5.insert_text(fitz.Point(margin, 255), "10. Telegram Bot Interactive Commands", fontsize=12, fontname="helv", color=C_PRIMARY)

    cmds = [
        ("/jobs", "Fetch latest high-match job listings scraped by the bot."),
        ("/topjobs", "Retrieve top 20 ranked jobs sorted by AI score."),
        ("/newjobs", "Display jobs discovered within the last 1 hour."),
        ("/stats", "Show application statistics, auto-apply counts, and success rates."),
        ("/companies", "List top hiring companies extracted from active listings."),
        ("/skillgaps", "View skill gap analysis identifying missing skills across scraped jobs.")
    ]

    cy = 270
    for cmd, desc in cmds:
        draw_box(p5, fitz.Rect(margin, cy, margin + 110, cy + 20), fill_color=hex_color("#EBF8FF"), border_color=C_SECONDARY)
        draw_box(p5, fitz.Rect(margin + 115, cy, pw - margin, cy + 20), fill_color=C_BG, border_color=C_BORDER)

        p5.insert_text(fitz.Point(margin + 8, cy + 14), cmd, fontsize=8.5, fontname="courier", color=C_PRIMARY)
        p5.insert_text(fitz.Point(margin + 122, cy + 14), desc, fontsize=8.2, fontname="helv", color=C_TEXT)
        cy += 24

    draw_box(p5, fitz.Rect(margin, 430, pw - margin, 495), fill_color=hex_color("#C6F6D5"), border_color=C_SUCCESS, width=1)
    p5.insert_text(fitz.Point(margin + 12, 448), "System Status: Production Ready", fontsize=9.5, fontname="helv", color=C_PRIMARY)
    p5.insert_text(fitz.Point(margin + 12, 463), "Run Command: python main.py", fontsize=8.5, fontname="helv", color=C_TEXT)
    p5.insert_text(fitz.Point(margin + 12, 476), "Web Dashboard: http://localhost:8000   |   Database: data/naukribot.db", fontsize=8.5, fontname="helv", color=C_TEXT)

    add_header_footer(p5, 5)

    doc.save(str(pdf_path))
    doc.close()
    print(f"100% Valid, Beautiful PDF generated at: {pdf_path.resolve()}")

if __name__ == "__main__":
    create_pdf()
