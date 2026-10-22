"""Test the /propose and /commit HITL endpoints."""

from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from api.main import app

client = TestClient(app)


def test_propose_endpoint():
    payload = {"text": "In the case of State v. Sharma, the court ruled on murder under section 302."}
    response = client.post("/propose", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready_for_review"
    assert data["proposed_node"]["label"] == "Case"
    assert "State v. Sharma" in data["proposed_node"]["properties"]["citation"]
    assert data["proposed_edge"]["type"] == "INTERPRETS"
    assert data["proposed_edge"]["target_section"]["number"] == "302"
    assert data["proposed_edge"]["target_section"]["code"] in ("IPC", "BNS")


def test_commit_endpoint():
    payload = {
        "proposed_node": {
            "label": "Case",
            "properties": {"citation": "State v. Sharma", "title": "Ruling on Murder"},
        },
        "proposed_edge": {
            "type": "INTERPRETS",
            "target_section": {"code": "IPC", "number": "302"},
        },
        "status": "ready_for_review",
    }
    response = client.post("/commit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Graph updated permanently."
