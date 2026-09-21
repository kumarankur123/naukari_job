"""
=============================================================
  Naukri Job Application Bot — v10 SMART SKIP
  Author: Ajaykumar Gupta
  GitHub: github.com/YOUR_USERNAME/naukri-auto-apply-bot

  Run:  python3 naukri_bot.py
  Stop: Ctrl+C (anytime)
=============================================================
  Features:
  - Failed/problem jobs are saved to skip_list.json
  - Skipped jobs are NEVER picked up again
  - Chatbot questions answered automatically
  - Runs forever until Ctrl+C
=============================================================

  Setup:
  1. Copy .env.example to .env
  2. Fill in your Naukri credentials in .env
  3. pip install playwright python-dotenv
  4. playwright install chromium
  5. python3 naukri_bot.py
=============================================================
"""

import sys
import asyncio
import json
import os
import hashlib
import traceback
from datetime import datetime
import re
from playwright.async_api import async_playwright
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load credentials from .env ────────────────────────────
load_dotenv(os.path.join(BASE_DIR, ".env"))

NAUKRI_EMAIL     = os.getenv("NAUKRI_EMAIL", "")
NAUKRI_PASSWORD  = os.getenv("NAUKRI_PASSWORD", "")
EXPERIENCE_YEARS = os.getenv("TOTAL_EXPERIENCE", "1")
NOTICE_PERIOD    = os.getenv("NOTICE_PERIOD", "30")
CURRENT_CTC      = os.getenv("CURRENT_CTC", "")
EXPECTED_CTC     = os.getenv("EXPECTED_CTC", "")
MIN_SALARY_LPA   = float(os.getenv("MIN_SALARY_LPA", "12"))
APPLY_TIMEOUT_SECONDS = int(os.getenv("APPLY_TIMEOUT_SECONDS", "10"))

DEFAULT_KEYWORDS = "AI Engineer, Gen AI Engineer, Generative AI, Data Scientist, Machine Learning Engineer, ML Engineer, LLM Engineer, Data Engineer, Python Developer, Backend Developer, Full Stack Developer, Software Engineer, Software Developer, Data Analyst"
RAW_KEYWORDS     = os.getenv("SEARCH_KEYWORDS", DEFAULT_KEYWORDS)
SEARCH_KEYWORDS  = [k.strip() for k in RAW_KEYWORDS.split(",") if k.strip()]
MAX_PAGES_PER_KEYWORD = int(os.getenv("MAX_PAGES_PER_KEYWORD", "25"))
MAX_APPLIES_PER_KEYWORD = int(os.getenv("MAX_APPLIES_PER_KEYWORD", "50"))

# ── Role Priority & Salary Filter Engine ───────────────────
PRIORITY_ROLE_KEYWORDS = [
    "ai engineer", "gen ai", "generative ai", "data scientist", "machine learning", "ml engineer", "nlp", "llm", "deep learning"
]

def get_role_priority(title):
    """
    Returns priority score: lower number = higher priority.
    AI Engineer / Data Scientist / ML = priority 1 (Applied First!).
    Other engineering/analyst roles = priority 2.
    """
    t = (title or "").lower()
    for kw in PRIORITY_ROLE_KEYWORDS:
        if kw in t:
            return 1
    return 2

def parse_salary(salary_text):
    """
    Parses salary text from Naukri and returns:
    (is_undisclosed: bool, min_lpa: float or None, max_lpa: float or None, original_text: str)
    """
    if not salary_text:
        return True, None, None, ""

    text = salary_text.strip()
    lower = text.lower()

    if any(u in lower for u in ["not disclosed", "undisclosed", "confidential", "unspecified", "best in industry", "competitive"]):
        return True, None, None, text

    is_cr = "cr" in lower or "crore" in lower

    # Clean commas inside numbers (e.g. 12,00,000 -> 1200000)
    cleaned = re.sub(r'(?<=\d),(?=\d)', '', lower)

    # Full rupee amounts like 1200000 - 1800000
    full_range = re.search(r'(\d{5,9})\s*(?:-|to)\s*(\d{5,9})', cleaned)
    if full_range:
        v1 = float(full_range.group(1)) / 100000.0
        v2 = float(full_range.group(2)) / 100000.0
        return False, min(v1, v2), max(v1, v2), text

    # Standard range like 12-18 Lacs or 7.5 - 11.5 LPA
    range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)', cleaned)
    if range_match:
        val1 = float(range_match.group(1))
        val2 = float(range_match.group(2))
        if is_cr:
            val1 *= 100
            val2 *= 100
        return False, min(val1, val2), max(val1, val2), text

    # Single number like 12 LPA or 15 Lacs
    single_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lacs|lac|lakh|lakhs|lpa|cr|crore)', cleaned)
    if single_match:
        val = float(single_match.group(1))
        if is_cr:
            val *= 100
        return False, val, val, text

    return True, None, None, text

def is_salary_acceptable(salary_text, min_threshold_lpa=MIN_SALARY_LPA):
    """
    Returns (acceptable: bool, reason: str, (min_lpa, max_lpa)).
    1. Undisclosed / Not Disclosed / Confidential -> Always ALLOWED.
    2. Disclosed: If maximum salary offered is below min_threshold_lpa (e.g. 6-7, 7-11 LPA) -> REJECT.
    3. Disclosed: If maximum salary offered >= min_threshold_lpa (e.g. 12-18, 15-25 LPA) -> ALLOWED.
    """
    is_undisclosed, min_lpa, max_lpa, orig = parse_salary(salary_text)

    if is_undisclosed:
        return True, "Salary undisclosed (allowed)", (None, None)

    if max_lpa < min_threshold_lpa:
        return False, f"Salary {min_lpa}-{max_lpa} LPA is below minimum {min_threshold_lpa} LPA", (min_lpa, max_lpa)

    return True, f"Salary {min_lpa}-{max_lpa} LPA meets minimum {min_threshold_lpa} LPA", (min_lpa, max_lpa)

# ─────────────────────────────────────────────
BATCH_SIZE       = 5
LOG_FILE         = os.path.join(BASE_DIR, "naukri_applications_log.json")
SKIP_FILE        = os.path.join(BASE_DIR, "skip_list.json")
SCREENSHOT_DIR   = os.path.join(BASE_DIR, "debug_screenshots")
RECOMMENDED_URL  = "https://www.naukri.com/mnjuser/recommendedjobs"
# ─────────────────────────────────────────────


# ═══════════════════════════════════════════════
#  SKIP LIST — persists across runs
# ═══════════════════════════════════════════════
def load_skip_list():
    """Load previously skipped job IDs from file and auto-include all previously applied jobs."""
    skip_set = set()
    try:
        if os.path.exists(SKIP_FILE):
            with open(SKIP_FILE, encoding="utf-8", errors="ignore") as f:
                skip_set = set(json.load(f))
    except Exception:
        skip_set = set()

    # Auto-seed with jobs already applied to from log file
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
                logs = json.load(f)
                for entry in logs:
                    t = entry.get("job_title")
                    c = entry.get("company")
                    if t and c:
                        skip_set.add(make_job_id(t, c))
    except Exception:
        pass

    return skip_set

def save_skip_list(skip_set):
    """Save skipped job IDs to file."""
    try:
        with open(SKIP_FILE, "w", encoding="utf-8") as f:
            json.dump(list(skip_set), f, indent=2)
    except Exception:
        pass

def make_job_id(title, company):
    """Create a unique ID for a job based on title + company."""
    raw = f"{title.lower().strip()}_{company.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def add_to_skip(skip_set, title, company, reason="failed"):
    """Add a job to the skip list and save immediately."""
    job_id = make_job_id(title, company)
    skip_set.add(job_id)
    save_skip_list(skip_set)
    print(f"  ⛔ Skipped forever: {title} @ {company} ({reason})")
    return skip_set

def is_skipped(skip_set, title, company):
    """Check if a job should be skipped."""
    return make_job_id(title, company) in skip_set


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def ensure_dir():
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)

async def ss(page, name):
    ensure_dir()
    try:
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}.png"))
    except Exception:
        pass

def log_job(title, company, status):
    entry = {
        "date"     : datetime.now().strftime("%Y-%m-%d %H:%M"),
        "job_title": title,
        "company"  : company,
        "status"   : status
    }
    try:
        with open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        data = []
    data.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_today_count():
    try:
        with open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
            logs = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        return len([x for x in logs if x["date"].startswith(today) and x["status"] == "applied"])
    except Exception:
        return 0

async def close_popups(page):
    for sel in [
        "button[aria-label='close']", "[class*='closeBtn']",
        "button.crossIcon", ".modal-close",
    ]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    except Exception:
        pass


# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
#  CHATBOT AUTO-ANSWER ENGINE (100% POSITIVE & AFFIRMATIVE)
# ─────────────────────────────────────────────
async def handle_chatbot(page, max_seconds=APPLY_TIMEOUT_SECONDS):
    """
    Handles Naukri's screening chatbot drawer / modal.
    Automatically detects questions, radio options, checkboxes, and text/contenteditable fields,
    answers everything positively (matching user profile: experience, notice period, CTC, skills, etc.),
    and clicks Save / Submit to advance until the application is fully submitted.
    If question flow exceeds max_seconds or cannot be answered, aborts cleanly and returns 'timeout'.
    """
    # Quick check for drawer animation (check every 250ms, max 1.5s)
    drawer_found = False
    for _ in range(6):
        await page.wait_for_timeout(250)
        has_drawer = await page.evaluate("""() => {
            const d = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]');
            return d && d.offsetWidth > 100 && d.offsetHeight > 100;
        }""")
        if has_drawer:
            drawer_found = True
            break

    if not drawer_found:
        return False

    print(f"  💬 Screening Chatbot detected — auto-answering questions (⏱️ {max_seconds}s timer)...")
    start_time = asyncio.get_event_loop().time()

    for attempt in range(15):
        # ── 0. Strict Timeout Check ──
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= max_seconds:
            print(f"    ⏱️ Chatbot questions timed out (> {max_seconds}s limit) — aborting question popup")
            try:
                await page.evaluate("""() => {
                    const cross = document.querySelector('.chatbot_Drawer .crossIcon, [class*="chatbot"] [class*="close"], button[aria-label="close"]');
                    if (cross) cross.click();
                }""")
            except Exception:
                pass
            return "timeout"

        await page.wait_for_timeout(350)

        # ── 1. Check if application is already completed or drawer closed ──
        status = await page.evaluate("""() => {
            const drawer = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]');
            if (!drawer || drawer.offsetWidth === 0 || drawer.offsetHeight === 0) {
                return { isApplied: true, isDrawerOpen: false };
            }

            const drawerText = (drawer.innerText || '').toLowerCase();
            const isApplied = drawerText.includes('application submitted') || 
                              drawerText.includes('successfully applied') || 
                              drawerText.includes('application has been sent') ||
                              drawerText.includes('application sent') ||
                              drawerText.includes('applied successfully');

            return { isApplied, isDrawerOpen: true };
        }""")

        if status["isApplied"] or not status["isDrawerOpen"]:
            print(f"    ✓ Chatbot completed! Application submitted successfully.")
            await page.wait_for_timeout(500)
            return True

        # ── 2. Inspect active question and interactive elements ──
        step_data = await page.evaluate(r"""() => {
            const drawer = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]') || document.body;

            // Extract last bot message / question text (skip greeting)
            const qEls = drawer.querySelectorAll('.botMsg span, .botMsg div, .botMsg');
            let lastQ = '';
            for (let el of qEls) {
                const t = (el.innerText || '').trim();
                if (t && t.length > 5 && !t.toLowerCase().includes('thank you for showing interest')) {
                    lastQ = t;
                }
            }

            // Radio options / labels
            const labels = Array.from(drawer.querySelectorAll('.ssrc__label, label, input.ssrc__radio, .ssrc__radio-btn-container, [role="radio"], li, [class*="option"]')).map(l => ({
                text: (l.innerText || l.value || l.id || '').replace(/\s+/g, ' ').trim(),
                id: l.getAttribute('for') || l.id || '',
                tag: l.tagName
            })).filter(l => l.text && l.text.length < 50 && !['save', 'submit', 'next', 'send', 'close', 'x'].includes(l.text.toLowerCase()));

            // Text input or contenteditable area
            const textInputEl = drawer.querySelector('div.textArea[contenteditable="true"], div[contenteditable="true"], [data-placeholder*="Type message"], input[type="text"], input[type="number"], textarea');
            const hasTextInput = !!textInputEl && textInputEl.offsetWidth > 0;
            const isContentEditable = textInputEl ? !!textInputEl.isContentEditable : false;

            return {
                lastQ,
                labels,
                hasTextInput,
                isContentEditable
            };
        }""")

        q_text = step_data.get("lastQ", "").lower()
        labels = step_data.get("labels", [])
        has_text_input = step_data.get("hasTextInput", False)
        answered = False

        # ── 3. Handle Radio Options / Multiple Choice Questions ──
        if labels:
            chosen_text = None

            # A. Notice Period
            if any(w in q_text for w in ["notice", "joining", "serving", "period", "days"]):
                np_clean = str(NOTICE_PERIOD).strip().lower()
                if "15" in np_clean:
                    prio = ["15 days or less", "15 days", "less than 15", "immediate", "serving notice period", "1 month"]
                elif "30" in np_clean or "1 month" in np_clean:
                    prio = ["1 month", "30 days", "15 days or less", "serving notice period", "immediate", "2 months"]
                else:
                    prio = ["immediate", "serving notice period", "15 days or less", "1 month"]

                for p in prio:
                    for l in labels:
                        if p in l["text"].lower():
                            chosen_text = l["text"]
                            break
                    if chosen_text:
                        break

            # B. Experience Questions
            elif any(w in q_text for w in ["experience", "years", "exp", "how long", "how many"]):
                exp_prio = [
                    f"{EXPERIENCE_YEARS} years", f"{EXPERIENCE_YEARS} year", f"{EXPERIENCE_YEARS}+",
                    f"{EXPERIENCE_YEARS}-{int(EXPERIENCE_YEARS)+1} years", "2-3 years", "1-2 years", "1-3 years",
                    str(EXPERIENCE_YEARS)
                ]
                for p in exp_prio:
                    for l in labels:
                        if p.lower() in l["text"].lower():
                            chosen_text = l["text"]
                            break
                    if chosen_text:
                        break

            # C. CTC / Salary Questions
            elif any(w in q_text for w in ["current ctc", "fixed ctc", "current salary", "present ctc"]):
                ctc_prio = [f"{CURRENT_CTC} lpa", f"{CURRENT_CTC} lakhs", f"{CURRENT_CTC}", "10-12", "10-15"]
                for p in ctc_prio:
                    for l in labels:
                        if p.lower() in l["text"].lower():
                            chosen_text = l["text"]
                            break
                    if chosen_text:
                        break

            elif any(w in q_text for w in ["expected", "expectation", "expected ctc", "expected salary"]):
                ctc_prio = [f"{EXPECTED_CTC} lpa", f"{EXPECTED_CTC} lakhs", f"{EXPECTED_CTC}", "12-15", "15-18"]
                for p in ctc_prio:
                    for l in labels:
                        if p.lower() in l["text"].lower():
                            chosen_text = l["text"]
                            break
                    if chosen_text:
                        break

            # D. Relocation / Office / Hybrid / Shift / Travel / Night shift / Rotational (ALWAYS POSITIVE YES)
            elif any(w in q_text for w in ["relocate", "relocation", "residing", "willing", "comfortable", "shift", "night", "rotational", "travel", "work from office", "wfo", "hybrid", "laptop", "internet", "agree", "ready", "bangalore", "bengaluru", "delhi", "noida", "gurgaon", "gurugram", "hyderabad", "pune", "mumbai"]):
                for l in labels:
                    if any(pos in l["text"].lower() for pos in ["yes", "agree", "comfortable", "willing", "open", "flexible", "ready", "available"]):
                        chosen_text = l["text"]
                        break

            # E. English / Communication Skills
            elif any(w in q_text for w in ["english", "communication", "language", "proficiency", "fluency"]):
                for l in labels:
                    if any(pos in l["text"].lower() for pos in ["fluent", "proficient", "advanced", "good", "expert"]):
                        chosen_text = l["text"]
                        break

            # F. Education / Degree / Qualification
            elif any(w in q_text for w in ["qualification", "degree", "education", "graduation"]):
                for l in labels:
                    if any(pos in l["text"].lower() for pos in ["b.tech", "b.e", "bachelor", "graduate", "mca", "bca", "full time"]):
                        chosen_text = l["text"]
                        break

            # G. Check for explicit "Yes" in options
            if not chosen_text:
                for l in labels:
                    t = l["text"].lower()
                    if t == "yes" or t.startswith("yes") or "agree" in t or "willing" in t:
                        chosen_text = l["text"]
                        break

            # H. General Safe Positive Fallback: NEVER select "No", "Reject", "Skip", "None"
            if not chosen_text:
                for l in labels:
                    t = l["text"].lower()
                    if not any(neg in t for neg in ["no", "not", "none", "skip", "reject", "disagree", "can't", "cannot"]):
                        chosen_text = l["text"]
                        break

            if not chosen_text:
                chosen_text = labels[0]["text"]

            # Click option: Target visible label via Playwright
            clicked = False
            try:
                loc = page.locator(
                    f".chatbot_Drawer label[for='{chosen_text}'], "
                    f".chatbot_Drawer label:has-text('{chosen_text}'), "
                    f".chatbot_Drawer .ssrc__label:has-text('{chosen_text}'), "
                    f".chatbot_Drawer .ssrc__radio-btn-container:has-text('{chosen_text}')"
                ).first
                await loc.click(force=True)
                clicked = True
            except Exception:
                pass

            await page.wait_for_timeout(300)

            # DOM double enforcement: set checked = true & trigger change event
            await page.evaluate(r"""(targetText) => {
                const drawer = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]') || document.body;
                const items = Array.from(drawer.querySelectorAll('label, .ssrc__label, .ssrc__radio-btn-container'));
                for (let el of items) {
                    const t = (el.innerText || el.getAttribute('for') || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    if (t === targetText.toLowerCase() || t.startsWith(targetText.toLowerCase())) {
                        el.click();
                        const input = el.querySelector('input[type="radio"]') || 
                                      (el.getAttribute('for') ? drawer.querySelector('#' + el.getAttribute('for')) : null) ||
                                      el.parentElement?.querySelector('input[type="radio"]');
                        if (input) {
                            input.checked = true;
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return true;
                    }
                }
                return false;
            }""", chosen_text)

            print(f"    ✓ Selected option: '{chosen_text}' (step {attempt+1})")
            answered = True
            await page.wait_for_timeout(500)

        # ── 4. Handle Text / Contenteditable Input Questions ──
        elif has_text_input:
            # Positive Answer Engine for text questions
            if any(w in q_text for w in ["notice", "days", "joining", "serving"]):
                ans = str(NOTICE_PERIOD)  # "30"
            elif any(w in q_text for w in ["current ctc", "current salary", "fixed ctc", "present ctc"]):
                ans = str(CURRENT_CTC) if CURRENT_CTC else "11"
            elif any(w in q_text for w in ["expected", "expectation", "expected ctc", "expected salary"]):
                ans = str(EXPECTED_CTC) if EXPECTED_CTC else "15"
            elif any(w in q_text for w in ["experience", "years", "exp", "how long", "how many"]):
                ans = str(EXPERIENCE_YEARS)  # "2"
            elif any(w in q_text for w in ["english", "communication", "language"]):
                ans = "Fluent"
            elif any(w in q_text for w in ["qualification", "degree", "education"]):
                ans = "B.Tech"
            elif any(w in q_text for w in ["relocate", "residing", "willing", "comfortable", "shift", "travel", "work from office", "wfo", "hybrid", "laptop", "internet", "agree"]):
                ans = "Yes"
            else:
                # If question asks about tool, technology or count
                if any(w in q_text for w in ["count", "number", "how many", "rate", "years"]):
                    ans = str(EXPERIENCE_YEARS)
                else:
                    ans = "Yes"  # Always affirmative positive response!

            # Focus and type with Playwright keyboard
            txt_el = await page.query_selector(".chatbot_Drawer div.textArea[contenteditable='true'], .chatbot_Drawer input[type='text'], .chatbot_Drawer textarea")
            if txt_el and await txt_el.is_visible():
                try:
                    await txt_el.click()
                    await page.wait_for_timeout(200)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await page.keyboard.type(ans, delay=50)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(300)
                except Exception:
                    pass

            # Fallback evaluate to set value
            await page.evaluate("""(textToFill) => {
                const el = document.querySelector('.chatbot_Drawer div.textArea[contenteditable="true"], .chatbot_Drawer input[type="text"], .chatbot_Drawer textarea');
                if (el) {
                    if (el.isContentEditable || el.tagName === 'DIV') {
                        el.focus();
                        el.innerText = textToFill;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        el.focus();
                        el.value = textToFill;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            }""", ans)

            display_q = q_text[:35].replace('\n', ' ') if q_text else "Screening Question"
            print(f"    ✓ Filled answer: '{ans}' for '{display_q}' (step {attempt+1})")
            answered = True
            await page.wait_for_timeout(600)

        # ── 5. Click Save / Submit to send the answer ──
        save_clicked = False
        try:
            save_btn = await page.query_selector(".chatbot_Drawer .send:not(.disabled) .sendMsg, .chatbot_Drawer .sendMsg, .chatbot_Drawer button:has-text('Save'), .chatbot_Drawer button:has-text('Submit'), .chatbot_Drawer button:has-text('Next')")
            if save_btn and await save_btn.is_visible():
                await save_btn.click()
                save_clicked = True
        except Exception:
            pass

        if not save_clicked:
            save_clicked = await page.evaluate("""() => {
                const drawer = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]');
                if (!drawer) return false;
                const saveEls = Array.from(drawer.querySelectorAll('.sendMsg, .send, [id*="sendMsg"], .sendMsgbtn_container, button')).filter(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    return (t === 'save' || t === 'submit' || t === 'next' || t === 'send' || t === 'apply') && el.offsetWidth > 0;
                });
                if (saveEls.length > 0) {
                    saveEls[saveEls.length - 1].click();
                    return true;
                }
                return false;
            }""")

        if not save_clicked:
            await page.keyboard.press("Enter")

        await page.wait_for_timeout(500)

        # If nothing could be answered after multiple attempts, abort and return timeout
        if attempt >= 5 and not answered:
            print("    ⚠️ Could not auto-answer screening questions — aborting chatbot")
            try:
                await page.evaluate("""() => {
                    const cross = document.querySelector('.chatbot_Drawer .crossIcon, [class*="chatbot"] [class*="close"], button[aria-label="close"]');
                    if (cross) cross.click();
                }""")
            except Exception:
                pass
            return "timeout"

    return "timeout"


# ─────────────────────────────────────────────
#  GET JOB CARDS
# ─────────────────────────────────────────────
async def get_job_cards(page):
    return await page.evaluate("""
        () => {
            const allCards = Array.from(document.querySelectorAll('article.jobTuple, .cust-job-tuple'));
            // Keep only top-level cards (eliminate nested child matches)
            const cards = allCards.filter(card => !card.parentElement.closest('article.jobTuple, .cust-job-tuple'));

            return cards.map(card => {
                const box = card.getBoundingClientRect();
                const cb  = card.querySelector('i.naukicon-ot-checkbox, .tuple-check-box i, input[type="checkbox"]');
                const cardText = (card.innerText || '').toLowerCase();
                const isCompanySite = cardText.includes('company site') || cardText.includes('apply on company');

                let title = 'Unknown';
                const titleEl = card.querySelector('.title, a.title, [class*="title"] a');
                if (titleEl) {
                    title = (titleEl.innerText || '').split('\\n')[0].trim().substring(0, 70);
                }

                let company = 'Unknown';
                const compEl = card.querySelector('a.subTitle, [class*="subTitle"]');
                if (compEl) {
                    const t = (compEl.innerText || '').trim();
                    if (!t.match(/^\\d+\\s+(Review|Rating)/i)) company = t.substring(0, 70);
                }
                if (company === 'Unknown') {
                    for (let a of card.querySelectorAll('a')) {
                        const t = (a.innerText || '').trim();
                        if (t && t !== title && !t.match(/^\\d+\\s+(Review|Rating)/i) && t.length > 1) {
                            company = t.substring(0, 70);
                            break;
                        }
                    }
                }

                let cbX = null, cbY = null;
                if (cb) {
                    const r = cb.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        cbX = r.left + r.width / 2;
                        cbY = r.top  + r.height / 2;
                    }
                }

                let salary = '';
                const salEl = card.querySelector('.sal, [class*="sal"], [class*="salary"], i.naukicon-rupee, .ni-job-tuple-icon-sal');
                if (salEl) {
                    const p = salEl.closest('li, span, div');
                    salary = p ? (p.innerText || '').trim() : (salEl.innerText || '').trim();
                }
                if (!salary) {
                    for (let l of (card.innerText || '').split('\\n')) {
                        if (l.includes('Lacs') || l.includes('PA') || l.includes('Not Disclosed') || l.includes('Cr') || l.includes('₹') || l.includes('lpa')) {
                            salary = l.trim();
                            break;
                        }
                    }
                }

                return {
                    title, company, cbX, cbY,
                    visible: box.top > 50 && box.top < 850 && box.height > 0,
                    hasCb: !!cb && cbX !== null,
                    isCompanySite: isCompanySite,
                    salary: salary
                };
            }).filter(c => c.visible && c.title !== 'Unknown');
        }
    """)


# ─────────────────────────────────────────────
#  SEARCH MODE & SINGLE JOB APPLIER
# ─────────────────────────────────────────────
def make_keyword_slug(keyword):
    slug = keyword.lower().strip()
    slug = "".join(c if c.isalnum() or c in (" ", "-") else " " for c in slug)
    return "-".join(slug.split())

async def apply_single_job(context, job_url, title, company):
    """
    Opens an individual job page in a new tab and applies directly using Naukri's in-platform apply.
    Returns: 'applied', 'already-applied', 'external-company-site', 'daily-limit-reached', or 'no-apply-button'
    """
    job_page = await context.new_page()
    try:
        await job_page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
        await job_page.wait_for_timeout(2000)
        await close_popups(job_page)

        # Check if already applied
        for sel in [
            "button:has-text('Already Applied')",
            "[class*='already-applied']",
            ":text('Already Applied')",
            ":text('You have already applied')",
        ]:
            try:
                el = await job_page.query_selector(sel)
                if el and await el.is_visible():
                    return "already-applied"
            except Exception:
                pass

        # Check if external company site redirect
        for sel in [
            "button:has-text('Apply on company site')",
            "a:has-text('Apply on company site')",
            ":text('Apply on company site')",
        ]:
            try:
                el = await job_page.query_selector(sel)
                if el and await el.is_visible():
                    return "external-company-site"
            except Exception:
                pass

        # Check salary on job page (skip if disclosed and below MIN_SALARY_LPA)
        job_sal_text = await job_page.evaluate("""() => {
            const salEl = document.querySelector('[class*="salary"], [class*="sal"], i.naukicon-rupee, [class*="styles_jdn__salary"], [class*="topbar"]');
            if (salEl) {
                const p = salEl.closest('li, span, div');
                return p ? (p.innerText || '').trim() : (salEl.innerText || '').trim();
            }
            for (let l of (document.body.innerText || '').split('\\n')) {
                if ((l.includes('Lacs') || l.includes('PA') || l.includes('Not Disclosed') || l.includes('Cr')) && (l.includes('₹') || l.includes('P.A.'))) {
                    return l.trim();
                }
            }
            return '';
        }""")

        acceptable, reason, _ = is_salary_acceptable(job_sal_text, MIN_SALARY_LPA)
        if not acceptable:
            print(f"      ⏭️ Skipped: {reason}")
            return "low-salary"

        # Find the Apply button on the job page
        apply_btn = None
        for sel in [
            "button#apply-button",
            "button.apply-button",
            "[class*='apply-button']",
            "button:has-text('Apply')",
            "[class*='apply-btn']",
        ]:
            try:
                el = await job_page.query_selector(sel)
                if el and await el.is_visible():
                    txt = (await el.inner_text()).lower()
                    if "company site" not in txt and "already" not in txt:
                        apply_btn = el
                        break
            except Exception:
                pass

        if not apply_btn:
            return "no-apply-button"

        # Apply + Screening Question handling with strict timeout
        async def _do_apply_and_answers():
            btn_text = (await apply_btn.inner_text()).strip()
            print(f"      → Clicking '{btn_text}' (⏱️ {APPLY_TIMEOUT_SECONDS}s timer started)")
            await apply_btn.click()
            await job_page.wait_for_timeout(1000)

            # Check if daily application limit or processing error popup/toast appeared
            alert_result = await job_page.evaluate(r"""() => {
                const alerts = Array.from(document.querySelectorAll('[class*="toast"], [class*="alert"], [class*="modal"], [class*="error-container"], [class*="popup"], [class*="notify"]'));
                for (let a of alerts) {
                    const t = (a.innerText || '').toLowerCase();
                    if ((t.includes('daily') && (t.includes('limit') || t.includes('quota'))) || t.includes('maximum applications allowed')) {
                        return "daily-limit-reached";
                    }
                    if (t.includes('error while processing') || t.includes('error processing') || t.includes('try again later') || t.includes('something went wrong')) {
                        return "processing-error";
                    }
                }
                return null;
            }""")

            if alert_result in ("daily-limit-reached", "processing-error"):
                return alert_result

            # Handle screening chatbot if it appears
            chat_status = await handle_chatbot(job_page, max_seconds=APPLY_TIMEOUT_SECONDS)
            if chat_status == "timeout":
                return "timeout"

            # Check if drawer or question popup is still stuck open and unsubmitted
            is_stuck = await job_page.evaluate("""() => {
                const drawer = document.querySelector('.chatbot_Drawer, [class*="chatbot_Drawer"]');
                if (drawer && drawer.offsetWidth > 100 && drawer.offsetHeight > 100) {
                    const txt = (drawer.innerText || '').toLowerCase();
                    if (!txt.includes('submitted') && !txt.includes('applied') && !txt.includes('sent')) {
                        return true;
                    }
                }
                return false;
            }""")
            if is_stuck:
                return "timeout"

            await job_page.wait_for_timeout(500)
            await close_popups(job_page)
            return "applied"

        try:
            apply_res = await asyncio.wait_for(_do_apply_and_answers(), timeout=float(APPLY_TIMEOUT_SECONDS))
            return apply_res
        except asyncio.TimeoutError:
            print(f"      ⏱️ {APPLY_TIMEOUT_SECONDS}s Timeout: Question popup 10 sec me complete nahi hua — auto-skipping!")
            try:
                await close_popups(job_page)
            except Exception:
                pass
            return "timeout"

    except Exception as e:
        print(f"      ❌ Error applying to {title}: {e}")
        return "error"
    finally:
        try:
            await job_page.close()
        except Exception:
            pass


async def run_search_mode(context, skip_list, total_applied):
    """
    Searches Naukri for configured keywords and applies across search result pages.
    """
    print("\n" + "═" * 52)
    print("  🔍 SEARCH MODE: Scanning thousands of jobs on Naukri")
    print(f"  Target Keywords: {', '.join(SEARCH_KEYWORDS)}")
    print("═" * 52)

    search_page = await context.new_page()
    consecutive_processing_errors = 0

    try:
        for keyword in SEARCH_KEYWORDS:
            slug = make_keyword_slug(keyword)
            print(f"\n🔎 Target Role: '{keyword}' (Experience: {EXPERIENCE_YEARS} yrs | Target: {MAX_APPLIES_PER_KEYWORD} jobs)")
            keyword_applied = 0

            for page_num in range(1, MAX_PAGES_PER_KEYWORD + 1):
                if keyword_applied >= MAX_APPLIES_PER_KEYWORD:
                    print(f"  🎯 Reached target of {MAX_APPLIES_PER_KEYWORD} applies for '{keyword}'! Moving to next role...")
                    break

                url = f"https://www.naukri.com/{slug}-jobs?experience={EXPERIENCE_YEARS}&pageNo={page_num}"
                print(f"\n  📄 Page {page_num}/{MAX_PAGES_PER_KEYWORD} — {url}")

                try:
                    await search_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await search_page.wait_for_timeout(3000)
                    await close_popups(search_page)
                except Exception as e:
                    print(f"    ⚠️ Page load warning: {e}")
                    continue

                # Collect all job cards on this search page
                jobs = await search_page.evaluate("""() => {
                    const rawList = Array.from(document.querySelectorAll(
                        'article.jobTuple, div.srp-jobtuple-wrapper, div.cust-job-tuple'
                    ));
                    const list = rawList.filter(card => !card.parentElement.closest('article.jobTuple, div.srp-jobtuple-wrapper, div.cust-job-tuple'));
                    const results = [];
                    for (let card of list) {
                        const titleEl = card.querySelector('a.title, [class*="title"] a, [class*="title"]');
                        const compEl = card.querySelector('a.subTitle, [class*="subTitle"], a.comp-name');
                        let linkEl = card.querySelector('a[href*="job-listings"]');
                        if (!linkEl && titleEl && titleEl.tagName === 'A') linkEl = titleEl;

                        const title = titleEl ? (titleEl.innerText || '').trim().split('\\n')[0].substring(0, 70) : '';
                        const company = compEl ? (compEl.innerText || '').trim().split('\\n')[0].substring(0, 70) : '';
                        const url = linkEl ? linkEl.href : '';
                        const text = (card.innerText || '').toLowerCase();
                        const isCompanySite = text.includes('company site') || text.includes('apply on company');

                        let salary = '';
                        const salEl = card.querySelector('.sal, [class*="sal"], [class*="salary"], i.naukicon-rupee, .ni-job-tuple-icon-sal');
                        if (salEl) {
                            const parent = salEl.closest('li, span, div');
                            salary = parent ? (parent.innerText || '').trim() : (salEl.innerText || '').trim();
                        }
                        if (!salary) {
                            for (let l of (card.innerText || '').split('\\n')) {
                                if (l.includes('Lacs') || l.includes('PA') || l.includes('Not Disclosed') || l.includes('Cr') || l.includes('₹') || l.includes('lpa')) {
                                    salary = l.trim();
                                    break;
                                }
                            }
                        }

                        if (title && url) {
                            results.push({ title, company, url, isCompanySite, salary });
                        }
                    }
                    return results;
                }""")

                if not jobs:
                    print(f"    No jobs found on page {page_num}. Moving to next keyword.")
                    break

                # Sort so AI Engineer / Data Scientist roles are processed first
                jobs.sort(key=lambda j: get_role_priority(j['title']))

                print(f"    Found {len(jobs)} jobs on page {page_num}")

                for job in jobs:
                    if keyword_applied >= MAX_APPLIES_PER_KEYWORD:
                        print(f"  🎯 Reached target of {MAX_APPLIES_PER_KEYWORD} applies for '{keyword}'!")
                        break

                    try:
                        title   = job['title']
                        company = job['company']
                        url     = job['url']
                        salary  = job.get('salary', '')

                        if is_skipped(skip_list, title, company):
                            continue

                        if job.get('isCompanySite'):
                            skip_list = add_to_skip(skip_list, title, company, "external-company-site")
                            continue

                        # Filter out jobs with salary explicitly below MIN_SALARY_LPA (allow undisclosed)
                        acceptable, reason, _ = is_salary_acceptable(salary, MIN_SALARY_LPA)
                        if not acceptable:
                            print(f"  ⏭️ Skipped: {title} @ {company} ({reason})")
                            skip_list = add_to_skip(skip_list, title, company, "low-salary")
                            continue

                        print(f"  👉 Checking: {title} @ {company}")
                        try:
                            res = await asyncio.wait_for(apply_single_job(context, url, title, company), timeout=25.0)
                        except asyncio.TimeoutError:
                            print(f"    ⏱️ Overall timeout on {title} (>25s) — skipping forever.")
                            res = "timeout"

                        if res == "applied":
                            log_job(title, company, "applied")
                            skip_list = add_to_skip(skip_list, title, company, "already-applied")
                            total_applied += 1
                            keyword_applied += 1
                            consecutive_processing_errors = 0
                            today_total = get_today_count()
                            print(f"    ✅ Applied! (Role count: {keyword_applied}/{MAX_APPLIES_PER_KEYWORD} | Today: {today_total})\n")
                            await asyncio.sleep(2)
                        elif res == "daily-limit-reached":
                            print("\n🛑 DAILY LIMIT REACHED: Naukri.com daily apply limit reached for today.")
                            return total_applied, True
                        elif res == "processing-error":
                            consecutive_processing_errors += 1
                            skip_list = add_to_skip(skip_list, title, company, "processing-error")
                            print(f"    ⚠️ Naukri error: 'There was an error while processing your request' ({consecutive_processing_errors}/3)")
                            if consecutive_processing_errors >= 3:
                                today_total = get_today_count()
                                print("\n" + "═" * 56)
                                print("🛑 NAUKRI APPLICATION LIMIT / COOLDOWN REACHED")
                                print(f"  Aaj aapke account se total {today_total} jobs already apply ho chuki hain!")
                                print("  Naukri.com ki daily limit (100-200 jobs) poori ho chuki hai.")
                                print("  Naukri server error: 'There was an error while processing your request'")
                                print("  Bot safely stop ho raha hai taaki account safe rahe.")
                                print("═" * 56 + "\n")
                                return total_applied, True
                        elif res == "low-salary":
                            skip_list = add_to_skip(skip_list, title, company, "low-salary")
                        elif res == "timeout":
                            print(f"    ⏱️ {APPLY_TIMEOUT_SECONDS}s Timeout: Question popup me atak gaya tha — auto-skipping.")
                            skip_list = add_to_skip(skip_list, title, company, "questionnaire-timeout")
                            print(f"    ⛔ Job ko permanently skip list me daal diya taaki dubara kabhi na aaye.\n")
                        else:
                            skip_list = add_to_skip(skip_list, title, company, res)
                            print(f"    ⛔ Skipped {title} forever ({res})\n")
                    except Exception as single_job_err:
                        print(f"    ⚠️ Warning on {job.get('title')}: {single_job_err}")
                        skip_list = add_to_skip(skip_list, job.get('title', 'Unknown'), job.get('company', 'Unknown'), "error")
                        continue

    except Exception as search_err:
        print(f"\n  ⚠️ Search mode warning: {search_err}")
    finally:
        try:
            await search_page.close()
        except Exception:
            pass

    return total_applied, False


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════
async def run():
    print("\n╔══════════════════════════════════════════╗")
    print("║   NAUKRI BOT v10 — SMART SKIP            ║")
    print("║   github.com/YOUR_USERNAME/naukri-bot    ║")
    print("║   Press Ctrl+C to stop anytime           ║")
    print("╚══════════════════════════════════════════╝\n")

    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        print("  ❌ ERROR: NAUKRI_EMAIL and NAUKRI_PASSWORD not set.")
        print("  Create a .env file from .env.example and fill in your credentials.\n")
        return

    skip_list = load_skip_list()
    print(f"  📋 Loaded {len(skip_list)} previously skipped jobs")
    print(f"  💰 Minimum Salary Filter: >= {MIN_SALARY_LPA} LPA (or Undisclosed)")
    print(f"  🎯 Priority Roles: AI Engineer, Data Scientist, Gen AI, ML (Applied First!)")
    print(f"  ⏱️ Apply & Question Timer: {APPLY_TIMEOUT_SECONDS}s (stuck question popups auto-skipped forever)\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, slow_mo=350,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            permissions=[],
        )
        await context.grant_permissions([], origin="https://www.naukri.com")
        page = await context.new_page()

        try:
            # ── LOGIN ──────────────────────────────────
            print("━" * 46)
            print("  Logging in...")
            print("━" * 46)
            await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await close_popups(page)
            await page.fill("#usernameField", NAUKRI_EMAIL)
            await page.wait_for_timeout(400)
            await page.fill("#passwordField", NAUKRI_PASSWORD)
            await page.wait_for_timeout(400)
            await page.click("button[type='submit']")
            await page.wait_for_timeout(5000)
            await close_popups(page)
            print("  ✓ Logged in!\n")

            total_applied = 0

            # ── 1. SEARCH MODE: Target AI Engineer & Gen AI roles first (up to 50 per role) ──
            print("═" * 56)
            print("  🚀 STARTING SEARCH MODE: Target AI & Gen AI Roles First")
            print(f"  Target: up to {MAX_APPLIES_PER_KEYWORD} jobs per role")
            print(f"  Keywords: {', '.join(SEARCH_KEYWORDS)}")
            print("═" * 56)
            total_applied, limit_hit = await run_search_mode(context, skip_list, total_applied)
            if limit_hit:
                print("\n🛑 Daily application limit reached. Good luck! 🎯")
                return

            # ── 2. RECOMMENDED JOBS FEED (after search mode) ──
            print("\n" + "═" * 56)
            print("  📋 CHECKING RECOMMENDED JOBS FEED")
            print("═" * 56)
            await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            await close_popups(page)
            print("  ✓ Ready! Checking recommended jobs... (Ctrl+C to stop)\n")

            batch_num     = 1
            scroll_count  = 0
            empty_rounds  = 0

            while True:
                try:
                    if RECOMMENDED_URL not in page.url:
                        await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        await close_popups(page)

                    await page.evaluate(f"window.scrollTo(0, {scroll_count * 500})")
                    await page.wait_for_timeout(1500)

                    all_cards = await get_job_cards(page)

                    cards = []
                    skipped_this_batch = 0
                    for card in all_cards:
                        if is_skipped(skip_list, card['title'], card['company']):
                            skipped_this_batch += 1
                        elif not card.get('hasCb') or card.get('isCompanySite') or card.get('cbX') is None:
                            # Auto-skip jobs that require external company site registration / have no multi-apply checkbox
                            skip_list = add_to_skip(skip_list, card['title'], card['company'], "external-company-site")
                            skipped_this_batch += 1
                        else:
                            # Salary filter: skip if disclosed and below MIN_SALARY_LPA (allow undisclosed)
                            acceptable, reason, _ = is_salary_acceptable(card.get('salary', ''), MIN_SALARY_LPA)
                            if not acceptable:
                                print(f"  ⏭️ Skipped: {card['title']} @ {card['company']} ({reason})")
                                skip_list = add_to_skip(skip_list, card['title'], card['company'], "low-salary")
                                skipped_this_batch += 1
                                continue
                            cards.append(card)

                    # Prioritize AI Engineer, Data Scientist, Gen AI, ML Engineer roles first!
                    cards.sort(key=lambda c: get_role_priority(c['title']))

                    if skipped_this_batch > 0:
                        print(f"  ⏭  Skipped {skipped_this_batch} previously failed/external/low-salary jobs")

                    print(f"  Batch {batch_num}: {len(cards)} new jobs (scroll {scroll_count})")

                    if not cards:
                        empty_rounds += 1
                        if empty_rounds >= 2:
                            print("\n  ✓ Recommended jobs feed has no new jobs.")
                            print("  🚀 Switching to SEARCH MODE to apply to all available jobs across Naukri...")
                            total_applied, limit_hit = await run_search_mode(context, skip_list, total_applied)
                            if limit_hit:
                                print("\n🛑 Stopping: Daily application limit reached.")
                                break
                            print("\n  ✓ Search round finished! Checking recommended feed again in 60s...")
                            await page.wait_for_timeout(60000)
                            scroll_count = 0
                            empty_rounds = 0
                            await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                            await page.wait_for_timeout(4000)
                            continue
                        scroll_count += 1
                        continue

                    empty_rounds = 0
                    to_apply     = cards[:BATCH_SIZE]
                    selected     = []

                    for item in to_apply:
                        try:
                            await page.mouse.click(item['cbX'], item['cbY'])
                            await page.wait_for_timeout(350)
                            selected.append(item)
                            icon = "☑" if item['hasCb'] else "☐"
                            print(f"    {icon}  {item['title']} @ {item['company']}")
                        except Exception:
                            skip_list = add_to_skip(skip_list, item['title'], item['company'], "click-timeout")

                    if not selected:
                        scroll_count += 1
                        batch_num += 1
                        continue

                    # Scroll back to top so the static Apply header button is visible in viewport
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(600)

                    apply_clicked = False
                    for sel in [
                        "button.multi-apply-button",
                        "[class*='multi-apply']",
                        "button:has-text('Apply')",
                        "button[class*='apply']",
                    ]:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() > 0 and await loc.is_visible():
                                txt = (await loc.inner_text()).strip()
                                # Never click 'Apply on company site' as it requires external portal registration
                                if "company site" in txt.lower():
                                    continue
                                print(f"\n  → Clicking '{txt}'")
                                await loc.scroll_into_view_if_needed()
                                await loc.click(force=True)
                                await page.wait_for_timeout(2000)
                                apply_clicked = True
                                break
                        except Exception:
                            continue

                    # Close any extra tabs opened
                    if len(context.pages) > 1:
                        for extra_page in context.pages[1:]:
                            try:
                                await extra_page.close()
                            except Exception:
                                pass

                    # If page navigated away from recommended jobs, return immediately
                    if RECOMMENDED_URL not in page.url:
                        await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        await close_popups(page)

                    if not apply_clicked:
                        print("  ⚠️  Apply button not found — skipping this batch")
                        for item in selected:
                            skip_list = add_to_skip(skip_list, item['title'], item['company'], "no-apply-button")
                        scroll_count += 1
                        batch_num += 1
                        continue

                    await page.wait_for_timeout(1500)

                    # Check for Naukri error toast / already applied toast
                    error_detected = await page.evaluate(r"""() => {
                        const toasts = Array.from(document.querySelectorAll('[class*="toast"], [class*="alert"], [class*="error"], [class*="popup"], [class*="notify"]'));
                        for (let t of toasts) {
                            const txt = (t.innerText || '').toLowerCase();
                            if (txt.includes('error processing') || txt.includes('already applied') || txt.includes('oops') || txt.includes('not accepted') || txt.includes('unable to process')) {
                                return true;
                            }
                        }
                        return false;
                    }""")

                    if error_detected:
                        print("  ⚠️  Naukri application error/already applied detected — skipping this job")
                        for item in selected:
                            skip_list = add_to_skip(skip_list, item['title'], item['company'], "naukri-application-error")
                        await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        scroll_count += 1
                        batch_num += 1
                        continue

                    try:
                        chat_res = await handle_chatbot(page, max_seconds=APPLY_TIMEOUT_SECONDS)
                        if chat_res == "timeout":
                            print(f"  ⏱️ {APPLY_TIMEOUT_SECONDS}s Timeout: Question popup in recommended batch took too long — skipping this batch")
                            for item in selected:
                                skip_list = add_to_skip(skip_list, item['title'], item['company'], "questionnaire-timeout")
                            await close_popups(page)
                            scroll_count += 1
                            batch_num += 1
                            continue
                    except Exception as chat_err:
                        print(f"  ⚠️ Chatbot warning: {chat_err}")
                    await page.wait_for_timeout(500)
                    await close_popups(page)

                    success = False
                    try:
                        success_el = await page.query_selector(
                            "text=application was successful, text=successfully applied, [class*='success']"
                        )
                        if success_el and await success_el.is_visible():
                            success = True
                    except Exception:
                        pass

                    if success or apply_clicked:
                        for item in selected:
                            log_job(item['title'], item['company'], "applied")
                            skip_list = add_to_skip(skip_list, item['title'], item['company'], "already-applied")
                        total_applied += len(selected)
                        today_total    = get_today_count()
                        print(f"  ✅ Batch {batch_num} done! Session: {total_applied} | Today: {today_total}\n")
                        scroll_count   = 0  # Reset scroll so freshly shifted jobs at the top are processed next
                    else:
                        print("  ⚠️  Uncertain result — skipping this batch to be safe")
                        for item in selected:
                            skip_list = add_to_skip(skip_list, item['title'], item['company'], "uncertain-result")
                        scroll_count += 1

                    # Check if genuine daily application limit popup/toast appeared
                    try:
                        is_daily_limit = await page.evaluate("""() => {
                            const alerts = Array.from(document.querySelectorAll('[class*="toast"], [class*="alert"], [class*="modal"], [class*="error-container"], [class*="popup"]'));
                            for (let a of alerts) {
                                const t = (a.innerText || '').toLowerCase();
                                if ((t.includes('daily') && (t.includes('limit') || t.includes('quota'))) || t.includes('maximum applications allowed')) {
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        if is_daily_limit:
                            print("\n🛑 DAILY LIMIT REACHED: Naukri.com has reached your account's daily application limit.")
                            print("Naukri will reset your daily quota tomorrow. Bot will exit cleanly now.")
                            break
                    except Exception:
                        pass

                    batch_num += 1

                    await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2500)
                    await close_popups(page)

                except Exception as batch_err:
                    print(f"\n  ⚠️ Recoverable batch warning: {batch_err}. Continuing to next batch...")
                    scroll_count += 1
                    batch_num += 1
                    try:
                        await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        await close_popups(page)
                    except Exception:
                        pass
                    continue

        except KeyboardInterrupt:
            print("\n\n  ⏹  Stopped by user (Ctrl+C)")

        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            print(traceback.format_exc())
            await ss(page, "ERROR")

        finally:
            print("\n" + "━" * 46)
            print("  FINAL SUMMARY")
            print("━" * 46)
            try:
                with open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
                    logs = json.load(f)
                today   = datetime.now().strftime("%Y-%m-%d")
                applied = [x for x in logs if x["date"].startswith(today) and x["status"] == "applied"]
                print(f"\n  ✓ Applied today  : {len(applied)} jobs")
                print(f"  ⛔ Skip list size : {len(skip_list)} jobs (saved to {SKIP_FILE})")
                print(f"\n  Companies applied to today:")
                seen = []
                for j in applied:
                    if j['company'] not in seen and j['company'] != 'Unknown':
                        seen.append(j['company'])
                for c in seen[:25]:
                    print(f"    • {c}")
                if len(seen) > 25:
                    print(f"    ... and {len(seen)-25} more")
            except Exception:
                print(f"  Session total: {total_applied}")

            print(f"\n  📋 Log  : {LOG_FILE}")
            print(f"  ⛔ Skip : {SKIP_FILE}")
            try:
                await browser.close()
            except Exception:
                pass
            print("\n  Bot stopped. Good luck! 🎯\n")


if __name__ == "__main__":
    asyncio.run(run())
