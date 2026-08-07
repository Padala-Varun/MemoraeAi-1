"""Shared pytest fixtures. Ensure Settings can load without a full .env."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Fallbacks so pure-logic tests work without a local .env file.
_DEFAULTS = {
    "MONGODB_URI": "mongodb://localhost:27017",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "test",
    "NEO4J_DATABASE": "neo4j",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_API_KEY": "test",
}

for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)
