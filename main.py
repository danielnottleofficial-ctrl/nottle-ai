"""ASGI entrypoint for NOTTLE AI."""

from nottle_ai.app import create_app

app = create_app()
