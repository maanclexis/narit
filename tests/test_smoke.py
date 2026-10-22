"""Smoke test suite (H16-H18) for the 3 landmark legal fact patterns."""

import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from api.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "facts",
    [
        "Someone stole my motorcycle",
        "A man hit me with a stick and broke my arm",
        "Someone tricked me into giving them money",
    ],
)
def test_smoke_patterns(facts: str):
    response = client.post("/analyze", json={"facts": facts})
    assert response.status_code == 200

    data = response.json()

    # 1. At least 1 section
    assert "sections" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) >= 1

    # 2. At least 1 case (verified in both top-level and section cases)
    cases = data.get("cases") or [
        c for s in data["sections"] for c in s.get("cases", [])
    ]
    assert len(cases) >= 1

    # 3. A non-empty path array
    assert "path" in data
    assert isinstance(data["path"], list)
    assert len(data["path"]) > 0
