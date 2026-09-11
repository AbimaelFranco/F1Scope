"""WSGI / local dev entrypoint for F1Scope.

Local run:      python wsgi.py
Flask CLI run:  flask --app wsgi run
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
