from .server import create_server
from .dash_ui import create_dash_app
from .modules.core_dash import create_core_dash_app

server = create_server()

# Portal landing page (Dash app)
dash_app = create_dash_app(server)

# Core module (Dash app)
core_dash_app = create_core_dash_app(server)
