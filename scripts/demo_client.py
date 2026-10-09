"""Offline real-HTTP demonstration: public-data snapshot and explained review."""

import argparse
import json
import secrets
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8011")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
with httpx.Client(base_url=args.url, trust_env=False, timeout=60) as client:
    assert client.get("/api/health").status_code == 200
    account = client.post(
        "/api/auth/register",
        json={"email": f"demo-{secrets.token_hex(6)}@example.test", "password": secrets.token_urlsafe(24)},
    )
    account.raise_for_status()
    client.headers["X-CSRF-Token"] = account.json()["csrf_token"]
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    d = client.post("/api/v1/demo")
    d.raise_for_status()
    demo = d.json()
    path = f"/api/v1/wallets/{demo['wallet_id']}"
    snapshot = client.get(path + "/snapshots").json()[0]
    (root / "examples/snapshot.json").write_text(json.dumps(snapshot["snapshot"], indent=2))
    preview = client.post("/api/v1/imports/preview", json={"snapshot_json": json.dumps(snapshot["snapshot"])})
    preview.raise_for_status()
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    saved = client.post(path + "/snapshots", json=preview.json()["snapshot"])
    saved.raise_for_status()
    assert saved.json()["id"] == demo["snapshot_id"]
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    analysis = client.post(
        path + "/analyses",
        json=dict(
            snapshot_id=demo["snapshot_id"],
            burst_count=15,
            burst_window_seconds=120,
            large_transfer_thresholds=[
                {"asset_id": "native", "amount_base_units": "200000000000000000"},
                {"asset_id": snapshot["snapshot"]["contracts"][0]["address"], "amount_base_units": "100000000"},
            ],
        ),
    )
    analysis.raise_for_status()
    report = analysis.json()
    assert len(report["results"]["transactions"]) == 90
    assert report["results"]["anomaly_model"]["status"] == "available"
    assert report["results"]["native_reconciliation"]["status"] == "matches_observed_top_level_flows"
    (root / "examples/demo-report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    for fmt in ["json", "balances", "transactions", "transfers", "contract_events", "alerts", "model_scores"]:
        r = client.get(f"/api/v1/analyses/{report['id']}/report", params={"format": fmt})
        r.raise_for_status()
        if fmt != "json":
            (root / f"examples/{fmt}.csv").write_text(r.text)
    schema = client.get("/openapi.json")
    schema.raise_for_status()
    (root / "docs/openapi.json").write_text(json.dumps(schema.json(), indent=2))
    assert client.get("/docs").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204 and client.get("/api/auth/session").status_code == 401
    r = report["results"]
    print("HTTP smoke passed: account, demo, JSON preview/deduplication, analysis, seven exports, Swagger and logout.")
    print(
        len(r["transactions"]),
        "transactions;",
        len(r["transfers"]),
        "transfers;",
        len(r["contract_events"]),
        "contract logs;",
        len(r["alerts"]),
        "explained alerts; ML available.",
    )
