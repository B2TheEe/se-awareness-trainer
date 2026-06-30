# Security Policy

## Purpose

SE Awareness Trainer is an educational tool for self-training against social engineering attacks. It runs locally; no user data is transmitted externally.

## Scope

This project is intentionally a local development server (`flask run`, debug mode). It is **not** designed for production deployment or multi-user exposure. Do not expose it to the internet or an untrusted network.

Known accepted risks in local-only mode:
- Flask debug mode enabled (intentional for local use)
- No authentication (single-user, local only)
- SQLite without encryption (training scores are not sensitive)

## Reporting a Vulnerability

If you find a security issue in this project:

1. **Do not open a public GitHub issue** for sensitive findings.
2. Report via GitHub private vulnerability disclosure or email the repository owner directly.
3. Include: description, reproduction steps, potential impact.

Response target: within 7 days.

## Out of Scope

- Issues that only apply when intentionally deployed publicly without hardening
- Flask/Werkzeug upstream vulnerabilities (report to those projects)
- Missing rate limiting, CSRF tokens, or auth — this is a local training tool, not a web service

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| Bootstrap 5 (CDN) | UI |
| Chart.js (CDN) | Dashboard charts |
| Bootstrap Icons (CDN) | Icons |

Keep Flask updated: `pip install --upgrade flask`
