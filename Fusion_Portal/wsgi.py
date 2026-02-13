import os
from dotenv import load_dotenv

# Load local .env for dev; Render sets env vars directly
load_dotenv()

from app import server  # noqa: E402

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    server.run(host="0.0.0.0", port=port, debug=True)
