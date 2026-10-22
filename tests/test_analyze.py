"""Test the /analyze endpoint and UI serving."""

import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from api.main import app
from api.analyze import fallback_extract, extract_keywords

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
    assert "code" in first_sec
    assert "number" in first_sec


def test_fallback_extract():
    assert fallback_extract("Someone stole my phone and snatched my motorcycle") == ["theft"]
    assert fallback_extract("Accused hit the victim with a stick and broke arm") == ["hurt"]
    assert fallback_extract("Scam artist tricked and cheated money") == ["cheating"]
    assert "theft" in fallback_extract("motorcycle theft and hurt with stick")
    assert "hurt" in fallback_extract("motorcycle theft and hurt with stick")


def test_gemini_extraction_mock(monkeypatch):
    import api.analyze as analyze_mod
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")

    class MockModel:
        def __init__(self, name):
            self.model_name = name
        def generate_content(self, prompt):
            class Response:
                text = "theft, possession"
            return Response()

    import google.generativeai as genai
    monkeypatch.setattr(genai, "GenerativeModel", lambda name: MockModel(name))
    monkeypatch.setattr(genai, "configure", lambda *a, **k: None)

    kws = analyze_mod.extract_keywords("Someone stole my motorcycle")
    assert kws == ["theft", "possession"]


def test_static_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "NARIT Legal Graph" in response.text
    assert "Analyze" in response.text
