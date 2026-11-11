# RiskAssess

**Know your risk posture before your auditor does.** An AI-guided compliance interview that turns a SOC 2 or ISO 27001 assessment into a scored risk register, treatment plan and audit-ready report — in under an hour instead of days.

**Live demo:** [riskassess-i6fa.onrender.com](https://riskassess-i6fa.onrender.com/)

> Hosted on Render's free tier, so the first load can take up to a minute while the app wakes up.

![RiskAssess landing page](docs/screenshot.png)

---

## The problem

Compliance assessments are usually run through long spreadsheets and back-and-forth emails between an auditor and the client team. Questions are generic, answers are inconsistent, and turning them into a scored risk register is manual work that takes days.

## The solution

AI Risk Auditor interviews the client like a real auditor would. It works through each control one at a time, asks up to three targeted follow-up questions based on the answers, and then produces a scored risk record for that control. At the end, the results are saved and exported as a risk register ready for review.

Built by a Product Manager at a B2B cybersecurity company, from first-hand experience of how slow this process is for customers.

---

## Features

- **Two assessment modes**
  - **Risk assessment** — 30 controls each for SOC 2 (Trust Services Criteria) and ISO 27001
  - **Gap assessment** — 89 ISO 27001 clause and Annex A questions to find where an organisation falls short of certification
- **Adaptive follow-ups** — Claude asks up to 3 follow-up questions per control before scoring it
- **Calibrated recommendations** — tooling suggestions adjust to the organisation's headcount and the chosen framework
- **Structured risk scoring** — every control produces likelihood, impact, residual risk, treatment action, and CIA impact
- **User accounts** — email/password sign-up and login via Supabase Auth
- **Saved assessments** — completed results are stored per user in Postgres (Supabase)
- **Automatic delivery** — exported risk registers are emailed to the assessor via Resend
- **Formal Excel report** — `report_generator.py` turns a results CSV into a five-sheet workbook (summary dashboard, risk register, 5×5 heat map, risk by category, open actions)

---

## How it works

```
Sign up / log in
      │
      ▼
Choose mode (risk or gap) + framework + organisation details
      │
      ▼
For each control:  Claude asks question → user answers → up to 3 follow-ups → scored risk record
      │
      ▼
Export → saved to Supabase → CSV emailed to assessor → optional Excel report
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Gunicorn |
| AI | Claude Haiku 4.5 via the Anthropic SDK |
| Auth & database | Supabase (Auth + Postgres) |
| Email | Resend |
| Reporting | openpyxl (Excel), Python `csv` |
| Frontend | Vanilla JavaScript, HTML, CSS |
| Deployment | Docker, with configs for Render and Railway |

---

## Running locally

**Requirements:** Python 3.11+, an Anthropic API key, a Supabase project, and a Resend API key.

```bash
git clone https://github.com/AFahad1/AI-Risk-Auditor.git
cd AI-Risk-Auditor
pip install -r requirements.txt

cp .env.example .env
# Fill in ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY, SECRET_KEY,
# RESEND_API_KEY and OWNER_EMAIL

python app.py
# Open http://localhost:5000
```

Generate an Excel report from an exported CSV:

```bash
python report_generator.py path/to/results.csv --org "Acme Inc" --framework "ISO 27001"
```

## Deploying

The repo includes a `Dockerfile`, `render.yaml` and `railway.toml`. Set the environment variables from `.env.example` in your host's dashboard. The app exposes `/health` for health checks.

---

## Project structure

```
├── app.py                 # Flask routes, Claude prompts, export logic
├── auth.py                # Supabase sign-up / login / logout
├── questions.py           # Control and gap-assessment question banks
├── report_generator.py    # Standalone CSV → Excel report builder
├── static/                # Frontend JS and CSS
├── templates/             # index, login, register pages
├── Dockerfile, render.yaml, railway.toml, Procfile
└── .env.example
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/questions/<framework>` | Risk-assessment controls |
| GET | `/api/gap-questions/<framework>` | Gap-assessment questions |
| POST | `/api/chat` · `/api/gap-chat` | Send an answer, get Claude's next question or finding |
| POST | `/api/export` · `/api/gap-export` | Save results and send the register |

---

## Product decisions

- **One control at a time.** Long questionnaires get abandoned; a focused conversation keeps answers specific.
- **Capped follow-ups (3).** Enough depth to score a control properly, without the assessment dragging on.
- **Haiku over a larger model.** An assessment is 30–89 turns long, so speed and cost per turn matter more than peak reasoning.
- **Human review stays in the loop.** Findings are a first draft for a qualified assessor, not a final audit opinion.

## Limitations

- AI-generated findings must be reviewed by a qualified professional before use in a real audit.
- Depends on the Anthropic API; there is no offline mode.

---

## Author

**Fahad Ahmed** — Product Manager in cybersecurity SaaS, building AI products end to end. [LinkedIn](https://www.linkedin.com/in/YOUR-HANDLE)
