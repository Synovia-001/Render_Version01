# SynoviaFusion - Console (Fusion Portal) - Render Version 01

This repo contains a production-friendly starter for:
- **Dash (Plotly)** UI with a **personalised landing page**
- **DB-backed login** (Azure SQL / SQL Server) using **ODBC Driver 17**
- Tables created in **ADM** schema, database **Fusion_Dashboard**
- Docker build suitable for **Render Web Service (Docker)**

## 1) Security (tell-it-like-it-is)
If you pasted real DB credentials into chat or anywhere public, **assume they are compromised**:
- Rotate the password immediately
- Prefer a **least-privilege** SQL login (read for dashboards; separate admin for writes)

This project is designed to use **environment variables** in production (Render),
and an optional local INI file for development.

## 2) Folder layout
- `app/` - Flask + Dash app (login + landing page)
- `sql/` - DDL scripts (ADM schema + tables + seed modules)
- `scripts/` - helper scripts (run DDL, create user, hash password)
- `config/` - example INI config (DO NOT store real secrets in Git)
- `assets/` - Dash static assets (CSS, images)

## 3) Local Setup (Windows)
You said your working folder is:
`D:\Applications\React_Development\Render_Version01\Fusion_Portal`

### Steps
1. Copy this repo contents into that folder (or `git clone` into it)
2. Create a virtual env and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Create config:
   - Copy `config/Fusion_Dashboard.ini.example` to `config/Fusion_Dashboard.ini`
   - Fill values **locally** (don’t commit them)
4. Run DDL:
   ```bash
   python scripts\run_sql.py sql\ddl_all.sql
   ```
5. Create an initial user:
   ```bash
   python scripts\create_user.py --username admin --email admin@synovia.ie --first Admin --last User --role Admin
   ```
6. Start app:
   ```bash
   python wsgi.py
   ```
   Visit: http://127.0.0.1:8050

## 4) Render Deployment (Docker Web Service)
1. Push to GitHub
2. In Render: **New > Web Service**
3. Select repo + choose **Docker**
4. Set env vars (recommended):
   - `DB_SERVER`
   - `DB_DATABASE` = `Fusion_Dashboard`
   - `DB_USER`
   - `DB_PASSWORD`
   - `DB_DRIVER` = `ODBC Driver 17 for SQL Server`
   - `SECRET_KEY` (random long string)
   - `PORT` (Render usually provides this automatically)

Render will build `Dockerfile` and run Gunicorn.

## 5) What you get today
- Login page at `/login`
- Protected landing page at `/` with:
  - Personal welcome banner
  - KPI tiles (stubbed sample KPIs)
  - Module cards based on `ADM.Modules` + `ADM.UserModuleAccess`
- Easy extension points for:
  - real KPI SQL queries
  - AI endpoints/tools later

---
If you want the next increment: wire real KPI queries + add multi-page routing so each module becomes its own app.
