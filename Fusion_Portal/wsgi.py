import os
from dotenv import load_dotenv

# Load local .env for dev; Render sets env vars directly
load_dotenv()

from app import create_app  # noqa: E402

# Flask WSGI callable (Flask instance)
server = create_app()

# Common aliases for WSGI servers
app = server
application = server

# Helpful startup log (no secrets)
print(f"[WSGI] Loaded Flask app: type={type(app)} callable={callable(app)}", flush=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    server.run(host="0.0.0.0", port=port, debug=True)
