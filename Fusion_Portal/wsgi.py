"""WSGI entrypoint for Gunicorn.

This project embeds multiple Dash apps inside a single Flask server.

⚠️ Naming pitfall:
The package also contains a submodule named `app.server`.
If you do `from app import server`, Python can give you the *module* `app.server`
(not the Flask instance) depending on import order, which makes Gunicorn crash
with:

    Application object must be callable

So we always load the Flask instance via an explicit app-factory and expose it
as a module-level variable named `app`.
"""

from app import create_app

app = create_app()

print(f"[WSGI] Loaded Flask app: type={type(app)} callable={callable(app)}", flush=True)
