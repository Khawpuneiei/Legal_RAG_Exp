"""Vercel entrypoint (FastAPI zero-config): exposes the ASGI app."""
from src.app.main import app  # noqa: F401
