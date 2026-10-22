"""Test the /analyze endpoint and UI serving."""

import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from api.main import app

client = TestClient(app)


def test_analyze_endpoint():
    payload = {"facts": "Someone stole my motorcycle"}
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "sections" in data
    assert "path" in data
    assert isinstance(data["sections"], list)
    assert isinstance(data["path"], list)
    assert len(data["sections"]) > 0
    assert len(data["path"]) > 0

    first_sec = data["sections"][0]
    assert "id" in first_sec
    assert "title" in first_sec
    assert "text" in first_sec


def test_static_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "NARIT Legal Graph" in response.text
    assert "Analyze" in response.text
