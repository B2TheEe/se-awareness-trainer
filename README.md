# SE Awareness Trainer

Local web app for self-training against social engineering attacks. Offline, no data leaves your machine.

## Features

- **Phishing Simulator** — analyze fake emails, click red flags, earn points per indicator found
- **Scenario Quiz** — realistic SE situations with multiple choice + per-answer explanations
- **Tactic Library** — reference for 7 SE tactics (phishing, pretexting, vishing, baiting, tailgating, BEC, quid pro quo)
- **Score Tracking** — SQLite-backed history with per-difficulty averages

## Content

| Module | Items | Difficulty range |
|--------|-------|-----------------|
| Phishing emails | 3 | beginner → advanced |
| Scenarios | 9 | beginner → advanced |
| Tactics (library) | 7 | — |

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5001`

## Stack

- Python / Flask
- SQLite (scores stored in `data/scores.db`, gitignored)
- Bootstrap 5 + vanilla JS (no build step)

## Tactics covered

| Tactic | Scenario |
|--------|----------|
| Pretexting | De IT-medewerker |
| Spear Phishing + Baiting | De LinkedIn-recruiter |
| Vishing + Caller ID Spoofing | De bankmedewerker |
| Tailgating | De bezorger |
| USB Baiting | De gevonden USB-stick |
| Smishing | Het SMS-bericht van DigiD |
| Quid Pro Quo | De helpdesk die je belt |
| BEC + Typosquatting | De dringende betaling |
| OSINT + Account Takeover | De collega die je kent |
