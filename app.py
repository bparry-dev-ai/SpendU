"""SpendU entry point.

Server (Docker):  gunicorn runs `app:app` — see the Dockerfile.
Local:            python app.py   → http://localhost:5000
CLI:              flask create-user | flask backup | flask list-backups

The real code lives in the spendu/ package.
"""
import os

from spendu import create_app

app = create_app()

if __name__ == "__main__":
    # Debug mode (auto-reload + error pages) only when you ask for it locally.
    # Never enable it on the server: its error pages let visitors run code.
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
