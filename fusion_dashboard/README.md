# Fusion Dashboard (Dash + Render) — v2

## What’s new
- Month dropdown is driven by real data from `LOG.RunDetail`
- Principal dropdown shows full name (joins `REF.Principals`)
- Interface name comes from `CFG.Interface_Movements`
- Adds a business-friendly "Route completion" metric:
  - Expected MovementCodes come from `CFG.Interface_Movements (Active=1)`
  - Actual MovementCodes come from `LOG.RunDetail`

## Local run (Windows)
1) Install requirements:
   `pip install -r requirements.txt`

2) Ensure **ODBC Driver 18 for SQL Server** is installed (or set ODBC_DRIVER in ini/env).

3) Create `D:\Configuration\render.ini` (any section name is fine), e.g.
   ```
   [database]
   DB_SERVER = ...
   DB_NAME = ...
   DB_USER = ...
   DB_PASSWORD = ...
   ```

4) Run:
   `python app.py`

Open http://127.0.0.1:8050

## Render deployment
Render will NOT read `D:\Configuration\render.ini`. Set environment variables in Render:
- DB_SERVER
- DB_NAME
- DB_USER
- DB_PASSWORD
Optional:
- ODBC_DRIVER

Start command (Procfile):
- `gunicorn app:server`