"""
WSGI entry point for production deployments (Gunicorn, uWSGI, etc.).
"""

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
