import os
from dotenv import load_dotenv

# Load local .env for dev; Render sets env vars directly
load_dotenv()

# Import the Flask instance from the package (callable WSGI app)
from app import server as server  # noqa: E402

# WSGI callable for Gunicorn
app = server
application = server

print(f"[WSGI] Loaded Flask app: type={type(app)} callable={callable(app)}", flush=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    server.run(host="0.0.0.0", port=port, debug=True)
