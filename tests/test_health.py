"""Smoke tests — runs against the live API with a real Neo4j backend."""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure .env is loaded
from dotenv import load_dotenv
load_dotenv()

from api.main import app

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "node_count" in body


def test_list_statutes():
    r = client.get("/statutes")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_search_cases():
    r = client.get("/cases", params={"limit": 5})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_doctrines():
    r = client.get("/doctrines")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
