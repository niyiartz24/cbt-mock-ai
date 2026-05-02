"""
WSGI entry point for gunicorn.
Usage: gunicorn wsgi:application
"""
from app import create_app

application = create_app()
