# SynoviaFusion — Console Portal (Render) + Core Module (Version 02)

This package is a **drop-in** repo you can copy into:
`D:\Applications\React_Development\Render_Version01\Fusion_Portal`

It includes:
- Flask + Dash portal (landing page) at `/`
- Login at `/login`
- Core module at `/module/Core/` (live DB-backed explorer + KPIs)
- Azure SQL connectivity via **ODBC Driver 18** (msodbcsql18 in Docker)
- Portal DB (users/modules/access): **Fusion_Dashboard**
- Core DB (module data): set via env var **CORE_DB** (same server + user + password)

## Render environment variables (recommended)
### Shared DB credentials (same for all databases)
- `DB_SERVER` = `futureworks-sdi-db.database.windows.net`
- `DB_USER` = `...`
- `DB_PASSWORD` = `...`
- `DB_DRIVER` = `ODBC Driver 18 for SQL Server`
- `DB_ENCRYPT` = `yes`
- `DB_TRUST_SERVER_CERTIFICATE` = `no`

### Portal database (ADM schema tables live here)
- `DB_DATABASE` = `Fusion_Dashboard`

### Module database (Core module reads from here)
- `CORE_DB` = `<your Core database name>`
  - (Alias supported) `Core_DB` also works

### Flask session security
- `SECRET_KEY` = long random string

## Local dev
1. `python -m venv .venv`
2. `.venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. Create `config/Fusion_Dashboard.ini` (optional, local only)
5. Run `python wsgi.py`

## DB DDL
- Run:
  ```bat
  python scripts\run_sql.py sql\ddl_all.sql
  ```

## Notes on bcrypt / passlib
We pin bcrypt to a compatible version to avoid Passlib failing at runtime.
