# Changelog

## V2.3 (2026-02-13)
- Portal + Core module bundle (drop-in repo)
- Docker: Debian 12 (bookworm) + msodbcsql18 (ODBC Driver 18)
- DB driver auto-selection + database override support (CORE_DB)
- Login + landing page hardened (boot-safe Dash layout)
- bcrypt pinned to avoid Passlib/bcrypt incompatibilities on Render
- Core module chart uses plotly.graph_objects (NO pandas required)

## V2.4 (2026-02-13)
- Fix: Gunicorn entrypoint hardened (export WSGI callable as wsgi:app)
- Refactor: move server creation into app.create_app() factory (avoid import side-effects)

## V2.5 (2026-02-17)
- Fix: Support legacy Gunicorn app URI `app:server` by exporting a WSGI callable in app/__init__.py
- Debug: Add startup log showing WSGI app type/callable
- Safety: Add build-time sanity check to fail early if WSGI app is not callable

## V2.6 (2026-02-17)
- Fix: Resolve Gunicorn `Application object must be callable` by overriding `app.server` export.
- Fix: wsgi.py now imports the Flask instance directly (no create_app import dependency).
- Keeps: build-time WSGI sanity check and ODBC18 + bcrypt pins.

## V2.7 (2026-02-17)
- Add: Fusion EPOS module at `/module/EPOS/` (week KPIs + charts + anomalies + data explorer)
- Add: EPOS module DB override via `EPOS_DB` env var (same server + credentials as portal)
- Add: pandas + openpyxl dependencies to support plotly.express and CSV exports
- UI: Force stable Plotly graph heights to prevent "expanding" graphs on refresh

