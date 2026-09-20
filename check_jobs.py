"""
=============================================================
  Naukri Application Stats Checker
  Built for: Ajaykumar Gupta
  Run: python3 check_jobs.py
=============================================================
"""

import sys
import json
import os
from datetime import datetime
from collections import Counter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE  = os.path.join(BASE_DIR, "naukri_applications_log.json")
SKIP_FILE = os.path.join(BASE_DIR, "skip_list.json")

def load_logs():
    if not os.path.exists(LOG_FILE):
        print(f"\n  ✗ Log file not found: {LOG_FILE}")
        print("  Make sure you run this script from the same folder as your bot.\n")
        return []
    with open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
        return json.load(f)

def load_skips():
    if not os.path.exists(SKIP_FILE):
        return []
    with open(SKIP_FILE, encoding="utf-8", errors="ignore") as f:
        return json.load(f)

def print_divider():
    print("━" * 52)

def run():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║   NAUKRI APPLICATION STATS — Ajaykumar Gupta     ║")
    print("╚══════════════════════════════════════════════════╝\n")

    logs  = load_logs()
    skips = load_skips()

    if not logs:
        return

    applied = [x for x in logs if x["status"] == "applied"]
    today   = datetime.now().strftime("%Y-%m-%d")
    today_applied = [x for x in applied if x["date"].startswith(today)]

    # ── OVERVIEW ──────────────────────────────────────
    print_divider()
    print("  OVERVIEW")
    print_divider()
    print(f"  Total applications (all time) : {len(applied)}")
    print(f"  Applied today ({today})  : {len(today_applied)}")
    print(f"  Jobs skipped (skip list)      : {len(skips)}")
    print()

    # ── BY DATE ───────────────────────────────────────
    print_divider()
    print("  APPLICATIONS BY DATE")
    print_divider()
    date_counts = Counter(x["date"][:10] for x in applied)
    for date, count in sorted(date_counts.items(), reverse=True)[:10]:
        bar = "█" * min(count, 40)
        print(f"  {date}  {bar} {count}")
    print()

    # ── TODAY'S JOBS ──────────────────────────────────
    if today_applied:
        print_divider()
        print(f"  TODAY'S APPLIED JOBS ({len(today_applied)} total)")
        print_divider()
        for i, job in enumerate(today_applied, 1):
            title   = job.get("job_title", "Unknown")
            company = job.get("company", "Unknown")
            time    = job["date"][11:] if len(job["date"]) > 10 else ""
            print(f"  {i:>3}. {title[:35]:<35} @ {company[:25]:<25} {time}")
        print()

    # ── TOP COMPANIES ─────────────────────────────────
    print_divider()
    print("  TOP 15 COMPANIES APPLIED TO (ALL TIME)")
    print_divider()
    companies = [x.get("company", "Unknown") for x in applied if x.get("company") not in ("Unknown", "")]
    company_counts = Counter(companies).most_common(15)
    for company, count in company_counts:
        print(f"  {count:>3}x  {company}")
    print()

    # ── HOURLY BREAKDOWN (TODAY) ──────────────────────
    if today_applied:
        print_divider()
        print("  TODAY'S HOURLY ACTIVITY")
        print_divider()
        hour_counts = Counter(x["date"][11:13] for x in today_applied if len(x["date"]) > 13)
        for hour, count in sorted(hour_counts.items()):
            bar = "█" * count
            print(f"  {hour}:00  {bar} ({count} jobs)")
        print()

    # ── VERIFICATION TIPS ─────────────────────────────
    print_divider()
    print("  HOW TO VERIFY ON NAUKRI")
    print_divider()
    print("  1. Go to: https://www.naukri.com/mnjuser/appliedjobs")
    print("  2. Check 'Applied Jobs' section — all bot applications appear here")
    print("  3. The 'Applies (X)' count on recommended page shows total")
    print("  4. Compare that number with the count above")
    print()
    print_divider()
    print(f"  Log file : {os.path.abspath(LOG_FILE)}")
    print(f"  Skip file: {os.path.abspath(SKIP_FILE)}")
    print_divider()
    print()


if __name__ == "__main__":
    run()
    input("  Press ENTER to close...")
