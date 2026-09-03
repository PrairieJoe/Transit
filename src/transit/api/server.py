"""Runnable ASGI entrypoint for local development."""

from transit.api.app import create_app
from transit.db import Database


app = create_app(Database("data/transit.sqlite3"))

