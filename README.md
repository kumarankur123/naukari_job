# 🤖 Naukri Auto Apply Bot

An intelligent, fully automated job application bot for [Naukri.com](https://www.naukri.com) powered by **Python** and **Playwright**. It searches for target job titles, filters out low-paying roles, auto-answers recruiter screening questionnaires, logs all applied jobs, and prevents duplicate applications across runs using persistent skip tracking.

---

## 📑 Table of Contents

- [Features](#-features)
- [Project Architecture & Files](#-project-architecture--files)
- [Prerequisites](#-prerequisites)
- [Setup & Installation](#-setup--installation)
- [Configuring `.env` (Environment Variables)](#-configuring-env-environment-variables)
- [Customizing Search Keywords](#-customizing-search-keywords)
- [How to Run the Bot](#-how-to-run-the-bot)
- [How to Stop the Bot](#-how-to-stop-the-bot)
- [Checking Application Stats & Logs](#-checking-application-stats--logs)
- [How the Smart Logic Works](#-how-the-smart-logic-works)
- [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## ✨ Features

- 🔑 **Automatic Login:** Securely logs in to your Naukri account with automated credential entry.
- 🎯 **Targeted Keyword Search:** Searches across custom job titles (e.g. *AI Engineer*, *Data Scientist*, *Backend Developer*).
- 🧠 **Priority Role Engine:** Automatically prioritizes AI, Machine Learning, and Data Science roles first before general roles.
- 💰 **Salary Filter (LPA):** Skips jobs below your minimum salary threshold (e.g., minimum 12 LPA). Keeps confidential / undisclosed salary jobs so you don't miss out on high-paying stealth roles.
- 💬 **Recruiter Chatbot Auto-Fill:** Automatically detects and answers common screening questions (Notice Period, Current CTC, Expected CTC, Total Experience, Yes/No questions).
- ⚡ **Anti-Hang Timeout:** Automatically skips problematic jobs that get stuck loading questions after a customizable timeout (default 10s).
- 🛑 **Permanent Skip List:** Stores applied and rejected job IDs in `skip_list.json` so you never waste time or apply twice to the same posting.
- 📊 **Detailed Stats & Logging:** Every applied job is saved with timestamp, company name, salary, and job title to `naukri_applications_log.json`.

---

## 📁 Project Architecture & Files

```text
apply_job/
├── .env                          # Your private configuration & credentials (DO NOT COMMIT)
├── .env.example                  # Template showing all available settings
├── job_bot.py                    # Main automation script (Playwright engine)
├── naukri_bot.py                 # Convenience wrapper pointing to job_bot.py
├── check_jobs.py                 # Analytics & statistics visualizer
├── stats.py                      # Convenience wrapper pointing to check_jobs.py
├── run_bot.bat                   # 1-Click batch launcher for Windows
├── check_stats.bat               # 1-Click statistics viewer for Windows
├── requirements.txt              # Required Python packages
├── naukri_applications_log.json  # Auto-generated log of all successful applications
├── skip_list.json                # Auto-generated database of skipped / already-applied jobs
└── debug_screenshots/            # Automated error/debug captures taken during runtime
```

---

## 💻 Prerequisites

1. **Operating System:** Windows 10/11, macOS, or Linux.
2. **Python:** Version **3.9 or higher** ([Download from python.org](https://www.python.org/downloads/)).
   Verify your version:
   ```powershell
   python --version
   ```
3. **Naukri Account:** An active account with an updated profile and uploaded resume.

---

## 🚀 Setup & Installation

### Step 1: Open the Project Directory

Open PowerShell or Command Prompt in the `apply_job` folder:

```powershell
cd C:\Users\ank79\OneDrive\Desktop\job_j\apply_job
```

### Step 2: Create a Virtual Environment (Recommended)

```powershell
python -m venv .venv
```

### Step 3: Activate the Virtual Environment

- **PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  *(If PowerShell gives an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*

- **Command Prompt (CMD):**
  ```cmd
  .\.venv\Scripts\activate.bat
  ```

### Step 4: Install Dependencies

```powershell
pip install -r requirements.txt
```

### Step 5: Install Playwright Browsers

Playwright requires Chromium binaries to automate the browser:

```powershell
playwright install chromium
```

---

## ⚙️ Configuring `.env` (Environment Variables)

Create your `.env` configuration file by copying the template:

```powershell
copy .env.example .env
```

Open `.env` in any text editor (VS Code, Notepad, etc.) and configure the parameters:

```env
# =============================================================
#  Naukri Auto Apply Bot Credentials & Details
# =============================================================

# 1. Your Naukri Account Credentials
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_naukri_password

# 2. Minimum Salary Filter (in LPA)
# Disclosed jobs paying less than this maximum are skipped.
# Undisclosed / confidential salaries are always allowed.
MIN_SALARY_LPA=12

# 3. Target Search Keywords (comma-separated)
SEARCH_KEYWORDS=AI Engineer, Data Scientist, Gen AI Engineer, Machine Learning Engineer, ML Engineer, Data Engineer, Python Developer, Backend Developer, Full Stack Developer, Software Engineer, Software Developer, Data Analyst

# 4. Profile Details (Used to auto-answer recruiter chatbot questions)
TOTAL_EXPERIENCE=2        # Total years of experience (numeric, e.g. 1, 2, 5)
NOTICE_PERIOD=30          # Notice period in days (e.g. 15, 30, 60, 90)
CURRENT_CTC=11            # Current CTC in LPA (numeric, e.g. 11 for 11 LPA)
EXPECTED_CTC=15           # Expected CTC in LPA (numeric, e.g. 15 for 15 LPA)

# 5. Search & Execution Limits
MAX_APPLIES_PER_KEYWORD=50     # Max applications to submit per keyword before moving to next
APPLY_TIMEOUT_SECONDS=10       # Max seconds to wait for question form before skipping a job
```

### Explanation of Environment Variables:

| Variable | Type | Description |
| :--- | :--- | :--- |
| `NAUKRI_EMAIL` | String | Email address used to log into Naukri.com. |
| `NAUKRI_PASSWORD` | String | Password for your Naukri account. |
| `MIN_SALARY_LPA` | Number | Threshold in LPA (Lacs Per Annum). E.g. `12` rejects jobs disclosing `6-8 LPA` or `8-11 LPA`, but allows `12-18 LPA` or "Not Disclosed". |
| `SEARCH_KEYWORDS` | String | Comma-separated list of keywords to search and apply for on Naukri. |
| `TOTAL_EXPERIENCE`| Integer | Number of years of experience to enter into screening form questions. |
| `NOTICE_PERIOD` | Integer | Number of days (e.g. `15`, `30`, `60`, `90`) entered for notice period questions. |
| `CURRENT_CTC` | Number | Current compensation in Lakhs per annum entered in recruiter questionnaires. |
| `EXPECTED_CTC` | Number | Expected compensation in Lakhs per annum entered in recruiter questionnaires. |
| `MAX_APPLIES_PER_KEYWORD` | Integer | Limits applications per keyword to keep search results fresh. |
| `APPLY_TIMEOUT_SECONDS` | Integer | Timeout limit in seconds to prevent the bot from hanging on broken job dialogs. |

---

## 🔍 Customizing Search Keywords

The bot reads `SEARCH_KEYWORDS` from `.env`, cleans each keyword, and runs automated searches sequentially.

### How to customize:
Edit line 13 in `.env`:
```env
SEARCH_KEYWORDS=keyword 1, keyword 2, keyword 3
```

### Tailored Keyword Configurations:

#### 1. AI, ML & Generative AI Profiles:
```env
SEARCH_KEYWORDS=AI Engineer, Gen AI Engineer, Generative AI, LLM Engineer, Data Scientist, Machine Learning Engineer, ML Engineer, NLP Engineer, Deep Learning Engineer
```

#### 2. Python & Backend Developer:
```env
SEARCH_KEYWORDS=Python Developer, Backend Developer, Django Developer, FastAPI Developer, Python Backend Engineer, Software Engineer Backend
```

#### 3. Full Stack & Software Engineering:
```env
SEARCH_KEYWORDS=Full Stack Developer, Full Stack Engineer, Software Engineer, Software Developer, SDE 2, SDE 1, Node.js Developer
```

#### 4. Data Engineering & Analytics:
```env
SEARCH_KEYWORDS=Data Engineer, Data Analyst, Big Data Engineer, PySpark Developer, Analytics Engineer, ETL Developer
```

> **Priority Engine Note:** The bot automatically identifies AI/ML/Data Science roles and applies to them before standard software developer roles when scanning search results.

---

## ▶️ How to Run the Bot

### Method 1: Windows 1-Click Runner (Easiest)
Simply double-click the **`run_bot.bat`** file located in `apply_job/`.
It activates `.venv` automatically and launches `job_bot.py`.

### Method 2: Command Line (PowerShell / CMD)
```powershell
# Navigate to directory
cd C:\Users\ank79\OneDrive\Desktop\job_j\apply_job

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run the bot
python job_bot.py
```
*(You can also run `python naukri_bot.py` which executes `job_bot.py` via alias).*

### What happens after starting:
1. Playwright opens a browser window.
2. Navigates to `naukri.com` and logs into your account.
3. If an **OTP** or captcha appears during your first login, the terminal will wait for you to complete it once.
4. Searches through your configured `SEARCH_KEYWORDS` one by one.
5. Scans job cards, analyzes salaries, and skips below-threshold postings.
6. Clicks **Apply**, handles screening questionnaires, and logs successful submissions.

---

## ⏹️ How to Stop the Bot

### Method 1: Graceful Keyboard Interrupt
Click on the running command terminal window and press:
```
Ctrl + C
```
The bot handles the signal cleanly:
- Closes the active browser instance.
- Flushes and saves `skip_list.json`.
- Safely writes all pending application records to `naukri_applications_log.json`.

### Method 2: Process Termination (If Unresponsive)
If the terminal window is frozen or running in the background:

- **Via CMD/PowerShell:**
  ```powershell
  taskkill /F /IM python.exe /T
  ```

- **Via `stop_bot.bat`:**
  If you have the `stop_bot.bat` script in the root directory, double-click it to terminate all running Python and browser automation processes.

---

## 📊 Checking Application Stats & Logs

To check how many jobs you have applied to today and overall:

### Method 1: Windows 1-Click Stats Checker
Double-click **`check_stats.bat`**.

### Method 2: Via Terminal
```powershell
python check_jobs.py
```

### Sample Output:
```text
╔══════════════════════════════════════════════════╗
║   NAUKRI APPLICATION STATS                       ║
╚══════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total applications (all time) : 348
  Applied today (2026-09-24)    : 52
  Jobs skipped (skip list)      : 114

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  APPLICATIONS BY DATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  2026-09-24  ██████████████████████████████ 52
  2026-09-23  ████████████████████████████████████████ 68

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TOP 15 COMPANIES APPLIED TO (ALL TIME)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    4x  Accenture
    3x  TCS
    3x  Persistent Systems
    2x  LTIMindtree
```

### Direct Verification on Naukri:
Verify applied jobs anytime directly in your browser:
👉 [https://www.naukri.com/mnjuser/appliedjobs](https://www.naukri.com/mnjuser/appliedjobs)

---

## 🧠 How the Smart Logic Works

### 1. Salary Parser & Filter
- **Undisclosed / Confidential:** Always approved. Many top tier companies don't disclose compensation upfront.
- **Disclosed Ranges (e.g. 10 - 15 LPA):** The bot parses the upper bound (`15 LPA`). If `15 >= MIN_SALARY_LPA`, it proceeds; if the upper bound is less than `MIN_SALARY_LPA`, it skips the job.

### 2. Recruiter Screening Chatbot Auto-Response
Recruiters frequently ask pre-application screening questions. The bot matches regex keywords:
- **Notice Period / Availability:** Filled with `NOTICE_PERIOD`.
- **Current CTC / Fixed Salary:** Filled with `CURRENT_CTC`.
- **Expected CTC / Expectation:** Filled with `EXPECTED_CTC`.
- **Experience / Total Experience:** Filled with `TOTAL_EXPERIENCE`.
- **Yes/No Radio Buttons:** Selected affirmatively (Yes) by default to pass initial screening filters.

### 3. Persistent Skip Memory
Every job is assigned an MD5 hash derived from `job_title + company`. When a job is successfully applied or skipped due to errors, its hash is recorded in `skip_list.json`. Subsequent runs immediately skip these jobs without clicking or loading their pages.

---

## 🛠️ Troubleshooting & FAQs

### Q1: The browser asks for an OTP on login.
**Solution:** On your first run, Naukri may send an OTP to your phone or email. Enter the OTP in the browser window opened by the bot. Once logged in, session cookies keep you authenticated.

### Q2: How do I reset the bot to re-apply or re-check skipped jobs?
**Solution:** Delete or clear `skip_list.json`. The bot will treat all listings as brand new.

### Q3: "playwright is not recognized as an internal or external command"
**Solution:** Ensure your virtual environment is activated (`.\.venv\Scripts\Activate.ps1`) before running `playwright install chromium`.

### Q4: Can I run this in headless mode (without opening a visible browser window)?
**Solution:** Open `job_bot.py` and ensure `headless=True` in the `browser.launch()` call. (Default is visible so you can monitor progress and handle any security checks).

### Q5: Will this get my Naukri account banned?
**Solution:** The bot includes human-like delays, batch throttling, and pagination limits (`MAX_APPLIES_PER_KEYWORD`). To maintain good standing, avoid setting `MAX_APPLIES_PER_KEYWORD` to extreme numbers and stick to realistic values (30–50 applications per keyword).

