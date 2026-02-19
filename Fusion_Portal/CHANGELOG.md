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

## V2.8 (2026-02-17)
- New: Fusion EPOS module at /module/EPOS/ (DB: EPOS_DB env var)
- Fix: Graphs no longer expand (responsive off + fixed heights)
- Improve: Anomalies redesigned (KPIs, top movers chart, clean table, ML anomaly score)
- Add: Predictive tab (seasonal ridge forecast for next-week Units/Value)
- Add: Export anomalies CSV button

## V2.9 (2026-02-17)
- Fix: Clean rewrite of config.py to resolve indentation error during Docker build

## V3.0 (2026-02-17)
- Restore: EPOS Stores / Products / Store×Product views
- Add: Platform branding (Fusion top logo, Synovia footer). Duracell Bunny side-brand in EPOS.
- Upgrade: Predictive uses Holt‑Winters (statsmodels) + ridge fallback; adds change-point detection (ruptures)
- Add: Supply-chain libraries (statsmodels, ruptures, networkx)

## V3.3
- EPOS Dash: static skeleton layout + callback renderer to prevent 'Error loading layout' on component-suites requests.
- EPOS Dash: safe_build_layout wrapper logs tracebacks and shows a friendly error panel instead of crashing.
- EPOS Dash: initialize base/cal variables defensively.

## V3.7 (2026-02-19)
- New: Fusion Solas module scaffold at /module/Solas/.
- Config: add SOLAS_DB + SOLAS_SCHEMA env vars.
- SQL: seed script to create module and grant access (sql/seed/seed_solas_module_access.sql).
