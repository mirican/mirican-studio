"""CAN Studio GUI — lokalna aplikacja webowa (FastAPI + WebSocket)."""

from .server import run  # noqa: F401

__all__ = ["run"]
