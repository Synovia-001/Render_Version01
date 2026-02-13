# Changelog

## V2.3 (2026-02-13)
- Portal + Core module bundle (drop-in repo)
- Docker: Debian 12 (bookworm) + msodbcsql18 (ODBC Driver 18)
- DB driver auto-selection + database override support (CORE_DB)
- Login + landing page hardened (boot-safe Dash layout)
- bcrypt pinned to avoid Passlib/bcrypt incompatibilities on Render
- Core module chart uses plotly.graph_objects (NO pandas required)
