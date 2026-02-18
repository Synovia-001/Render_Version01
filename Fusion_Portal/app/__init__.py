"""Application package.

We expose a single public factory: :func:`create_app`.

Avoid creating a global Flask object here.

Why? Because we also have a submodule named ``app.server``.
If we create a global variable called ``server`` at package import time,
Python's import machinery can later overwrite ``app.server`` with the submodule
object, leading to confusing (and intermittent) "Application object must be
callable" errors when Gunicorn loads the app.

Using an explicit factory keeps startup deterministic.
"""

from __future__ import annotations

from .server import create_server
from .dash_ui import create_dash_app
from .modules.core_dash import create_core_dash_app
from .modules.epos_dash import create_epos_dash_app


def create_app():
    """Create and configure the Flask server and attach Dash apps."""

    server = create_server()

    # Root landing/dashboard
    create_dash_app(server)

    # Modules
    create_core_dash_app(server)
    create_epos_dash_app(server)

    return server
