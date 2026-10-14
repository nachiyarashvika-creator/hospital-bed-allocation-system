# Smart Hospital Bed Management System

A complete college OOPS project built with Python, Flask, SQLite, and plain HTML/CSS/JavaScript. It includes separate hospital accounts. Each new hospital starts with 12 ready beds and no patients; the original demo hospital retains its three fictional sample patients. No database server or frontend build tools are needed.

## Features

- Dashboard with a live ward heatmap: green ready, red occupied, yellow cleaning, blue reserved. Text labels also identify each status.
- Admit patients by condition (general, ICU, ventilator, isolation), gender, and severity (1–5).
- Suggest the best bed without reserving it, or admit immediately. A general patient can use ICU only if no general bed is available. Isolation patients use isolation beds; ventilator patients need a ventilator-equipped ICU bed. Mixed wards accept every gender.
- Emergency reservation: one click after entering patient details reserves the nearest suitable critical-care bed. Confirm admission or cancel from the active-patient page.
- If no critical-care bed is ready, suggest a stable general-care patient in ICU who has a compatible ready general bed. These are suggestions only: no automatic transfer. A doctor must review; for the demo, discharge and re-admission can illustrate an approved move.
- Discharge starts cleaning: occupied → cleaning → ready. Demo timers are 30 seconds for general, 60 for ICU, and 90 for isolation. A bed may go directly from cleaning to occupied when a waiting patient is assigned.
- Priority waiting list: highest severity first, FIFO ties, skipping patients incompatible with a free bed. Automatic assignment runs on API requests; the dashboard polls every 2 seconds. With the browser closed, the next API request catches up from persisted deadlines.
- Persistent local SQLite storage, input validation, escaped frontend text, and transaction-protected allocation.

This is an educational demo with hospital administrator sign-in. It does not include clinical authorization, verified hospital identity, email verification or password recovery and must not store real patient information or guide actual medical care. Distances and stability rules are simplified project rules.

## Folder structure

```text
hospital-bed-allocation-system/
  app.py                 Flask REST API and application factory
  database.py            SQLite schema, migration and hospital seeding
  auth.py                Registration, login, sessions, CSRF and throttling
  manage.py              Local operator account provisioning
  models.py              OOP domain model and allocation rules
  requirements.txt       Python dependencies
  Procfile               Production web command
  render.yaml            Render blueprint, secret generation and health check
  .python-version        Render Python version family
  .gitignore             Excludes local environment and patient database
  README.md              Setup and project explanation
  VIVA.md                10 viva questions and answers
  templates/
    index.html           Dashboard and hospital management pages
    auth.html            Hospital registration and sign-in
  static/
    style.css            Responsive styling and heatmap colors
    app.js               API requests, polling, and page navigation
  tests/
    test_system.py       Automated workflow and OOP tests
    test_auth.py         Authentication, migration and isolation tests
  instance/              Automatically created; ignored by Git
    hospital.db          Automatically created SQLite database
```

## OOP concepts

| Concept | Example | Location |
| --- | --- | --- |
| Classes | Hospital, Ward, Bed, Patient, Doctor, Nurse, BedAllocator | models.py |
| Inheritance | Person → Patient, Doctor, Nurse; Bed → GeneralBed, ICUBed, IsolationBed | models.py |
| Abstraction | ABC and abstractmethod require concrete roles and bed rules | Person and Bed |
| Encapsulation | Private fields, read-only getters, validating name setter | Domain classes |
| Polymorphism | supports(), score(), cleaning_seconds vary by bed type | Bed subclasses and allocator |
| Composition | Hospital contains wards; allocator works with bed objects | Hospital and BedAllocator |

The backend creates Patient objects for validation, uses Doctor for transfer eligibility, Nurse for cleaning readiness, and Hospital/Ward for hospital organization and gender rules. API comments identify key OOP and concurrency decisions.

## Run locally: Windows CMD only

Install Python 3.12 or newer from python.org and select **Add Python to PATH**. Install Git for Windows from git-scm.com if you need GitHub. Open **Command Prompt (CMD)**. Do not use PowerShell commands.

If you downloaded this project as a ZIP, extract it and open its folder. Replace the example path below with your actual folder:

```cmd
cd /d C:\Projects\hospital-bed-allocation-system
py --version
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
```

If `py` is unavailable but `python --version` works, use `python -m venv .venv` instead. Open `http://127.0.0.1:5000` in your browser. The first run creates the database automatically. Click **Register your hospital**, choose a unique hospital code, and create an administrator email/password (at least 12 characters). Then sign in with that hospital code, email and password. A new hospital gets 12 ready beds and no patients. No default login password is provided. Press **Ctrl+C** in CMD to stop. Gunicorn is included for Linux deployment; Windows runs Flask using `python app.py`.

For future runs:

```cmd
cd /d C:\Projects\hospital-bed-allocation-system
.venv\Scripts\activate.bat
python app.py
```

Run the automated tests in a second CMD window:

```cmd
cd /d C:\Projects\hospital-bed-allocation-system
.venv\Scripts\activate.bat
python -m unittest discover -s tests -v
```

Tests use temporary databases; they do not alter your hospital database. For a fresh demo, stop the server first, then delete only the demo database:

```cmd
del instance\hospital.db
python app.py
```

If port 5000 is in use:

```cmd
set PORT=5001
python app.py
```

Open `http://127.0.0.1:5001` instead. Optional: set `DATABASE_PATH` to an absolute writable file path before starting to change the database location.

## Demonstration for your teacher

1. Register two hospitals. Show that each sees only its own data. Use Hospital setup to add a ward and bed. Show the OOP classes in models.py.
2. Admit a female general patient and show the selected general bed.
3. Reserve a ventilator emergency bed; show its blue tile, then confirm admission to make it red.
4. Discharge that patient: the tile becomes yellow with a 60-second countdown.
5. Fill compatible beds by admitting more patients. Admit one low-severity and one high-severity patient to the waiting list.
6. Discharge a patient, wait for cleaning, and show that the highest-severity compatible waiting patient gets the bed automatically.

## Initialize Git, commit, and push: Windows CMD

Create a new **empty** repository on github.com using your browser. Do not select README, license, or .gitignore when creating it. These browser steps cannot be performed with ordinary CMD commands alone without a separate GitHub API tool. Replace YOUR_USERNAME and YOUR_NEW_REPOSITORY in the commands.

```cmd
cd /d C:\Projects\hospital-bed-allocation-system
git init
git config user.name "Your Name"
git config user.email "your-email@example.com"
git add .
git commit -m "Build smart hospital bed management OOP project"
git branch -M main
git remote -v
```

For a fresh ZIP folder with no origin:

```cmd
git remote add origin https://github.com/YOUR_USERNAME/YOUR_NEW_REPOSITORY.git
git push -u origin main
```

If `git remote -v` already shows an origin and you want to push to your new repository:

```cmd
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_NEW_REPOSITORY.git
git push -u origin main
```

Git for Windows normally opens a browser sign-in. Use GitHub's supported sign-in flow; never put a password or token into a committed file. The ignored .venv and instance database are not uploaded.

For later updates:

```cmd
git add .
git commit -m "Describe your changes"
git push
```

## Deploy on Render: free demo web service

Push the project first. Render service creation and GitHub connection require the Render website; all terminal commands above are CMD-compatible. Plan availability and limits can change—select Free if it is available in your account.

1. Sign in at render.com, select **New → Web Service**, connect GitHub, and select your repository.
2. Choose Python as the runtime, main as the branch, and leave Root Directory empty.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`
5. Select the Free instance type and deploy. Open the HTTPS URL Render provides when deployment finishes.

The Render start command is a **Linux server command**, not a command to type into Windows CMD. `$PORT` is supplied by Render. Procfile contains the same command, but set the start command explicitly in the Render dashboard. .python-version selects Python 3.12. No external API keys are needed to run the app. For manual Render service creation, add an environment variable named SESSION_SECRET using a long randomly generated secret, and set the health-check path to /health. The render.yaml Blueprint generates SESSION_SECRET automatically. On local runs a private ignored session-key file is created alongside the database.

**Free-host limitation:** SQLite on a free Render service is stored on an ephemeral filesystem. Records can reset on restarts or redeploys; this is suitable only for a disposable college demo. Free services may sleep when idle and take time to wake. Durable data would require a persistent disk where supported or an external database. Your local SQLite database remains persistent.

## REST API

Patient and setup API requests require a signed-in session. Write requests send JSON with `Content-Type: application/json` and the current `X-CSRF-Token` header. The frontend supplies both automatically. Hospital identity always comes from the session, never a client-provided hospital ID. Sign-in, registration and sign-out use protected HTML forms.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /health | Public readiness check without patient data |
| GET | /api/state | State, cleaning completion, waiting-list processing |
| POST | /api/suggest | Best bed, without creating a patient |
| POST | /api/admit | Admit or queue a patient |
| POST | /api/emergency | Reserve nearest ICU/ventilator bed or queue |
| POST | /api/patients/ID/confirm | Confirm a reserved admission |
| POST | /api/patients/ID/discharge | Discharge, cancel reservation, or remove waiting patient |

Example admission body: `{"name":"Demo Patient","gender":"female","condition":"general","severity":3}`. Server validation rejects invalid fields with HTTP 400. Emergency only accepts ICU or ventilator conditions. Severity can be 1–5; the emergency form submits 5.

See [VIVA.md](VIVA.md) for ten short viva answers.


## Hospital login and realistic workspace

- Register at /register with a hospital name, unique code, city, administrator email and password. Use /login for future visits. Sign out from the sidebar.
- Each hospital has private wards, beds, patients, waiting-list processing and recent activity. Cross-hospital patient actions and ward references are rejected.
- Passwords are stored as Werkzeug scrypt hashes, not plain text. Signed cookies are HttpOnly and SameSite=Lax, with an eight-hour lifetime; cookies are also Secure on Render. CSRF tokens protect all write operations. Failed logins are throttled per account (5) and IP (30) per 15-minute window.
- Hospital setup allows creating wards and beds. Bed labels must be unique inside a hospital. Ventilators are available only on ICU beds. Seeded bed layouts and staff names remain demonstration templates.
- Recent activity records admissions, emergency reservations, confirmations, discharges, queue assignment and setup changes with administrator email and timestamp.
- Existing databases migrate automatically without deleting patients. A pre-migration backup is created alongside the original database, and old data belongs to the reserved `smart-hospital` hospital. Public registration cannot claim this hospital.

To access the existing sample hospital, create an administrator locally (Windows CMD, with your virtual environment active):

```cmd
python manage.py create-admin --hospital smart-hospital --email admin@example.com
```

The command prompts twice for a password; your typing is hidden. Then sign in with hospital code `smart-hospital`, your chosen email and password. New hospitals use the normal registration page. To provision another administrator for an existing hospital, use the same operator command with its code. This is a local trusted-operator command, not a public API. There is currently no forgotten-password workflow.

Before real hospital use, this project still needs verified organization onboarding, individual staff accounts and roles, clinically validated rules, configurable cleaning protocols, immutable audit retention, password recovery, security review, and durable database hosting/backups. Do not enter real patient information. Free Render storage can reset hospital accounts as well as patient data.
