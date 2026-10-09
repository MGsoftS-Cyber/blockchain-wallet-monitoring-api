import json
import secrets
from app.security import _attempts


def signup(client, email="engineer@example.test"):
    r = client.post("/api/auth/register", json={"email": email, "password": "local-demo-password-123"})
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"], "Idempotency-Key": secrets.token_hex(12)}


def demo(client):
    headers = signup(client)
    d = client.post("/api/v1/demo", headers=headers)
    assert d.status_code == 201, d.text
    headers["Idempotency-Key"] = secrets.token_hex(12)
    data = d.json()
    a = client.post(
        f"/api/v1/wallets/{data['wallet_id']}/analyses", headers=headers, json={"snapshot_id": data["snapshot_id"]}
    )
    assert a.status_code == 201, a.text
    return headers, data, a.json()


def test_complete_workflow_and_reports(client):
    headers, d, a = demo(client)
    assert len(a["results"]["balances"]) == 2
    assert len(a["results"]["transactions"]) == 90
    assert a["results"]["anomaly_model"]["status"] == "available"
    for fmt in ["json", "balances", "transactions", "transfers", "contract_events", "alerts", "model_scores"]:
        r = client.get(f"/api/v1/analyses/{a['id']}/report?format={fmt}")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
    assert client.get("/api/v1/analyses").json()[0]["id"] == a["id"]
    assert client.get("/api/v1/analyses/" + a["id"]).json()["results"] == a["results"]
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_write_needs_csrf_and_auth(client):
    assert client.get("/api/v1/wallets").status_code == 401
    signup(client)
    assert (
        client.post(
            "/api/v1/wallets", headers={"Idempotency-Key": "a"}, json={"label": "Watch", "address": "0x" + "5" * 40}
        ).status_code
        == 403
    )


def test_untrusted_origin(client):
    h = signup(client)
    h["Origin"] = "https://evil.example"
    assert (
        client.post("/api/v1/wallets", headers=h, json={"label": "Watch", "address": "0x" + "5" * 40}).status_code
        == 403
    )


def test_idempotency_and_conflict(client):
    h = signup(client)
    path = "/api/v1/wallets"
    first = client.post(path, headers=h, json={"label": "Watch", "address": "0x" + "5" * 40})
    second = client.post(path, headers=h, json={"label": "Watch", "address": "0x" + "5" * 40})
    assert first.json() == second.json()
    assert client.post(path, headers=h, json={"label": "Other", "address": "0x" + "6" * 40}).status_code == 409
    assert len(client.get(path).json()) == 1


def test_analysis_replay_keeps_snapshot(client):
    h, d, a = demo(client)
    replay = client.post(
        f"/api/v1/wallets/{d['wallet_id']}/analyses",
        headers=h,
        json={"snapshot_id": d["snapshot_id"]},
    )
    assert replay.json() == a
    assert len(client.get("/api/v1/analyses").json()) == 1


def test_owner_isolation(client):
    h, d, a = demo(client)
    client.cookies.clear()
    signup(client, "other@example.test")
    assert client.get("/api/v1/wallets").json() == []
    assert client.get("/api/v1/analyses").json() == []
    assert client.get("/api/v1/analyses/" + a["id"]).status_code == 404
    assert client.get("/api/v1/analyses/" + a["id"] + "/report").status_code == 404
    assert client.get("/api/v1/wallets/" + d["wallet_id"] + "/snapshots").status_code == 404


def test_logout_and_login(client):
    h = signup(client)
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    r = client.post("/api/auth/login", json={"email": "engineer@example.test", "password": "local-demo-password-123"})
    assert r.status_code == 200
    assert client.cookies["wallet_session"]


def test_validation_never_echoes_password(client):
    secret = "private-short"
    r = client.post("/api/auth/register", json={"email": "bad", "password": secret, "unknown": secret})
    assert r.status_code == 422
    assert secret not in json.dumps(r.json())


def test_auth_rate_limit(client):
    _attempts.clear()
    for _ in range(20):
        assert (
            client.post(
                "/api/auth/login", json={"email": "none@example.test", "password": "local-demo-password-123"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "none@example.test", "password": "local-demo-password-123"}
        ).status_code
        == 429
    )


def test_snapshot_dedup_and_failed_commit(client):
    h, d, a = demo(client)
    path = f"/api/v1/wallets/{d['wallet_id']}/snapshots"
    original = client.get(path).json()[0]
    payload = original["snapshot"]
    h["Idempotency-Key"] = "same"
    r = client.post(path, json=payload, headers=h)
    assert r.status_code == 201 and r.json()["id"] == d["snapshot_id"]
    count = len(client.get(path).json())
    payload["blocks"].pop(3)
    h["Idempotency-Key"] = "bad"
    assert client.post(path, json=payload, headers=h).status_code == 422
    assert len(client.get(path).json()) == count
