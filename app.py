# app.py — Entry point for Render's default gunicorn command
# Render runs 'gunicorn app:app' by default, this bridges that.
from main import flask_app as app  # noqa

if __name__ == "__main__":
    app.run()
