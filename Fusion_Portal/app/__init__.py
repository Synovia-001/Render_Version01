"""SynoviaFusion Portal package (WSGI exports).

Why this file exists:
- Gunicorn entrypoints like `app:server` can break if `app.server` resolves to the
  *module* `app/server.py` (modules aren't callable).
- Importing from `.server` causes Python to attach the submodule as `app.server`.
- We explicitly override `server` to be a Flask instance (callable), so both:
    - gunicorn wsgi:app
    - gunicorn app:server
  work reliably.

Exports:
  - create_app() factory
  - server: Flask instance (callable WSGI app)
  - app / application: aliases to server
"""

from __future__ import annotations

from .server import create_server
from .dash_ui import create_dash_app
from .modules.core_dash import create_core_dash_app

def create_app():
    server = create_server()
    create_dash_app(server)      # `/`
    create_core_dash_app(server) # `/module/Core/`
    return server

# Create a single global Flask instance for WSGI servers.
server = create_app()

# Common aliases
app = server
application = server
