# SE Awareness Trainer

Local web app for self-training against social engineering attacks. Offline, no data leaves your machine.

## Modules

| Module | Items | Focus |
|--------|-------|-------|
| **Phishing Simulator** | 7 emails | Click red flags in fake emails, points per indicator |
| **Scenario Quiz** | 15 scenarios | Multiple choice with per-answer explanations |
| **Login Detector** | 4 pages | Spot fake browser login pages (URL, SSL, form) |
| **Email Header Analysis** | 3 headers | Read raw SMTP headers (SPF/DKIM/DMARC, Received chain) |
| **Tactic Library** | 7 tactics | Reference: phishing, pretexting, vishing, baiting, tailgating, BEC, quid pro quo |
| **Weak Points Dashboard** | — | Per-category Chart.js breakdown, weakest/strongest areas |
| **Review Mode** | — | Replay past attempts with all correct answers revealed |
| **CSV Export** | — | Download full score history as spreadsheet |

## Gameplay Features

- **Countdown timer** — 120s/90s/60s per difficulty (beginner/intermediate/advanced)
- **Time bonus** — up to +30 points for fast completion (phishing/login/headers)
- **Hints system** — reveal a targeted tip once per attempt, costs -50% max score
- **Daily Challenge** — date-seeded daily item with +25 bonus points on first completion
- **Streak counter** — consecutive active days tracked from score history
- **Difficulty progression** — intermediate/advanced locked until 2 prior-level completions ≥50%
- **Auto-submit** — timer expiry submits with zero score on scenarios; partial on others

## Content

### Phishing Emails (7)
| # | Category | Difficulty |
|---|----------|------------|
| 1 | IT Support Phishing | beginner |
| 2 | Delivery Phishing | intermediate |
| 3 | BEC (CEO Fraud) | advanced |
| 4 | Subscription Phishing | beginner |
| 5 | Government Phishing | intermediate |
| 6 | Credential Harvesting | intermediate |
| 7 | HR Phishing | advanced |

### Scenarios (15)
| Tactic | Title | Difficulty |
|--------|-------|------------|
| Pretexting | De IT-medewerker | beginner |
| Spear Phishing + Baiting | De LinkedIn-recruiter | beginner |
| USB Baiting | De gevonden USB-stick | beginner |
| Shoulder Surfing | De meekijker in de trein | beginner |
| Tech Support Scam | Microsoft belt je | beginner |
| Vishing + Caller ID Spoofing | De bankmedewerker | intermediate |
| Smishing | Het SMS-bericht van DigiD | intermediate |
| Quid Pro Quo | De helpdesk die je belt | intermediate |
| AI Voice Cloning | De stem van je manager | intermediate |
| Invoice Fraud | De gewijzigde leveranciersrekening | intermediate |
| Tailgating | De bezorger | advanced |
| BEC + Typosquatting | De dringende betaling | advanced |
| OSINT + Account Takeover | De collega die je kent | advanced |
| Insider Threat | De nieuwe collega | advanced |
| Watering Hole | De aanbevolen tool | advanced |

### Login Detector (4)
| Target | Attack type | Difficulty |
|--------|------------|------------|
| Microsoft | Wrong domain + no HTTPS | beginner |
| ING Bank | Subdomain trick | intermediate |
| DigiD | Typosquat (dlgid.nl) | intermediate |
| Google | Homoglyph (goog1e.com) | advanced |

### Email Header Analysis (3)
| Category | Attack type | Difficulty |
|----------|------------|------------|
| SPF Fail | Unauthorized sending IP | beginner |
| Header Spoofing | BEC with typosquat + foreign IP | intermediate |
| DKIM Replay | Stolen valid DKIM signature | advanced |

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5001`

## Stack

- Python / Flask
- SQLite (`data/scores.db`, gitignored)
- Bootstrap 5 + Chart.js + vanilla JS (no build step)
