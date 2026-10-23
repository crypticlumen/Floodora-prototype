"""Root-level FastAPI entrypoint for Vercel's Python runtime."""

from backend.main import app

__all__ = ["app"]
