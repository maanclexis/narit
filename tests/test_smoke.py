def _codes(body):
    return [(s["code"], str(s["number"])) for s in body["sections"]]


def test_theft_ipc378(client):
    res = client.post("/analyze", json={"facts": "aditya took gauravs phone"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    codes = _codes(body)
    assert ("IPC", "378") in codes, f"expected IPC 378, got {codes}"


def test_hurt_ipc323_or_325(client):
    res = client.post("/analyze", json={"facts": "A man hit me with a stick and broke my arm"})
    assert res.status_code == 200
    codes = _codes(res.json())
    assert any(c == "IPC" and n in ("323", "325") for c, n in codes), f"got {codes}"


def test_cheating_ipc420(client):
    res = client.post("/analyze", json={"facts": "Someone tricked me into giving them money"})
    assert res.status_code == 200
    codes = _codes(res.json())
    assert ("IPC", "420") in codes, f"got {codes}"


def test_wrong_medicine_ipc276_bns278(client):
    res = client.post("/analyze", json={"facts": "wrong medicine given to shyam"})
    assert res.status_code == 200
    pairs = [(s["code"], str(s["number"]), s.get("bns_number")) for s in res.json()["sections"]]
    assert any(c == "IPC" and n == "276" for c, n, _ in pairs), f"expected IPC 276, got {pairs}"
    assert any(c == "IPC" and n == "276" and str(b) == "278" for c, n, b in pairs), \
        f"expected IPC 276 -> BNS 278, got {pairs}"
