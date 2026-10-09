import copy
import json
from decimal import Decimal, localcontext
import pytest
from pydantic import ValidationError
from web3 import Web3
from app.schemas import SnapshotInput, WalletInput, AnalysisInput
from app.imports import normalize, preview
from app.demo import sample, WALLET, PEER, TOKEN, hash_number
from app.events import decode, units, TRANSFER_TOPIC
from app.engine import evaluate
from app.anomalies import detect


def review(p=None, **updates):
    p = p or sample()[0]
    args = AnalysisInput(
        snapshot_id="test",
        large_transfer_thresholds=[
            {"asset_id": "native", "amount_base_units": "200000000000000000"},
            {"asset_id": TOKEN, "amount_base_units": "100000000"},
        ],
    ).model_dump(mode="json")
    args.update(updates)
    return evaluate(dict(**args, snapshot=p))


def test_transfer_signature_and_exact_units():
    assert TRANSFER_TOPIC == "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    assert units("1234567890123456789", 18) == "1.234567890123456789"
    assert units("1", 36) == "0." + "0" * 35 + "1"
    with localcontext() as ctx:
        ctx.prec = 100
        assert Decimal(units(str(2**256 - 1), 18)) * Decimal(10**18) == Decimal(2**256 - 1)
    assert units("1234500", 6) == "1.2345"


def test_demo_balances_and_reconciliation():
    r = review()
    assert len(r["transactions"]) == 90 and len(r["transfers"]) == 159
    assert len(r["contract_events"]) == 71
    assert r["native_reconciliation"]["status"] == "matches_observed_top_level_flows"
    assert r["token_reconciliation"][0]["status"] == "matches_observed_transfer_logs"
    assert r["anomaly_model"]["status"] == "available"
    assert r["balances"][0]["balance_base_units"] == r["native_reconciliation"]["closing_native_wei"]
    json.dumps(r, allow_nan=False)


def test_failed_value_excluded_but_sender_fee_charged():
    p = sample()[0]
    failed = p["transactions"][80]
    txs, transfers, events = decode(p)
    assert failed["status"] == 0
    assert not any(t["transaction_hash"] == failed["hash"] and t["asset_id"] == "native" for t in transfers)
    decoded = next(t for t in txs if t["hash"] == failed["hash"])
    assert int(decoded["fee_paid_wei"]) == failed["gas_used"] * int(failed["effective_gas_price_wei"])
    assert any(a["code"] == "FAILED_TRANSACTION" for a in review(p)["alerts"])


def test_incoming_sender_fees_not_charged_to_wallet():
    txs = decode(sample()[0])[0]
    assert all(t["fee_paid_wei"] == "0" for t in txs if t["from_address"] != WALLET)


def test_blob_fee_included_exactly():
    p = sample()[0]
    t = p["transactions"][0]
    t["blob_gas_used"] = 131072
    t["blob_gas_price_wei"] = "2"
    assert int(decode(p)[0][0]["fee_paid_wei"]) == t["gas_used"] * int(t["effective_gas_price_wei"]) + 262144


def test_self_transfers_do_not_create_net_native_flow():
    p = sample()[0]
    t = p["transactions"][0]
    t["to_address"] = WALLET
    r = review(p)
    movement = next(x for x in r["transfers"] if x["event_id"] == t["hash"] + ":native")
    assert movement["direction"] == "self"
    assert int(next(x for x in r["asset_flows"] if x["asset_id"] == "native")["self_base_units"]) == int(t["value_wei"])


def test_nft_shaped_log_remains_raw():
    p = sample()[0]
    log = copy.deepcopy(p["logs"][0])
    log["log_index"] = 9
    log["topics"].append(hash_number(555))
    log["data"] = "0x"
    p["logs"].append(log)
    txs, t, e = decode(p)
    assert e[-1]["event_type"] == "raw_contract_log"
    assert not any(x["event_id"] == log["transaction_hash"] + ":9" for x in t)


def test_malformed_indexed_address_not_decoded():
    p = sample()[0]
    p["logs"][0]["topics"][1] = "0x" + "f" * 64
    events = decode(p)[2]
    assert events[0]["event_type"] == "raw_contract_log"


def test_generic_events_remain_available_and_zero_transfer_preserved():
    p = sample()[0]
    p["logs"][0]["data"] = "0x" + "0" * 64
    txs, t, e = decode(p)
    assert any(x["amount_base_units"] == "0" for x in t)
    assert any(x["event_type"] == "raw_contract_log" for x in e)


def test_native_gap_and_unknown_opening():
    p = sample()[0]
    p["closing_native_wei"] = str(int(p["closing_native_wei"]) + 1)
    r = review(p)
    assert r["native_reconciliation"]["gap_wei"] == "1"
    assert any(a["code"] == "NATIVE_BALANCE_GAP" for a in r["alerts"])
    p["opening_native_wei"] = None
    assert review(p)["native_reconciliation"]["status"] == "opening_unavailable"


def test_token_gap_and_unavailable_balance_are_not_zero():
    p = sample()[0]
    p["contracts"][0]["closing_balance"] = str(int(p["contracts"][0]["closing_balance"]) + 7)
    assert review(p)["token_reconciliation"][0]["gap_base_units"] == "7"
    p["contracts"][0]["closing_balance"] = None
    r = review(p)
    assert r["balances"][1]["balance"] is None
    assert r["token_reconciliation"][0]["status"] == "balance_unavailable"


def test_threshold_and_fee_rules_have_evidence():
    r = review()
    codes = {a["code"] for a in r["alerts"]}
    assert {"LARGE_TRANSFER", "HIGH_TRANSACTION_FEE", "FAILED_TRANSACTION", "NEW_OUTGOING_RECIPIENT"} <= codes
    assert all(a["evidence"] for a in r["alerts"])


def test_model_baseline_and_future_prefix_invariance():
    transfers = decode(sample()[0])[1]
    first = detect(transfers[:100], True)
    longer = detect(transfers, True)
    assert first["status"] == "available"
    byid = {x["event_id"]: x for x in longer["scores"]}
    assert all(x == byid[x["event_id"]] for x in first["scores"])
    for asset in longer["assets"]:
        if asset["status"] == "available":
            assert len(asset["training_event_ids"]) == 30 and asset["training_end"] <= asset["scoring_start"]


def test_model_never_mixes_asset_scales():
    transfers = decode(sample()[0])[1]
    model = detect(transfers, True)
    assert len(model["assets"]) == 2
    for asset in model["assets"]:
        if asset["status"] == "available":
            assert all(
                next(t for t in transfers if t["event_id"] == k)["asset_id"] == asset["asset_id"]
                for k in asset["training_event_ids"]
            )


def test_model_disabled_and_short_history():
    t = decode(sample()[0])[1]
    assert detect(t, False)["status"] == "disabled"
    assert detect(t[:10], True)["status"] == "insufficient_history"


@pytest.mark.parametrize("bad", ["short", "0x" + "g" * 40, "0x" + "aB" * 20])
def test_bad_address(bad):
    with pytest.raises(ValidationError):
        WalletInput(label="test", address=bad)


def test_checksum_normalization():
    a = Web3.to_checksum_address("0x" + "ab" * 20)
    assert WalletInput(label="test", address=a).address == a.lower()


@pytest.mark.parametrize("value", [1, "-1", str(2**256), "NaN"])
def test_uint256_contract(value):
    p = sample()[0]
    p["closing_native_wei"] = value
    with pytest.raises(ValidationError):
        SnapshotInput(**p)


@pytest.mark.parametrize(
    "kind",
    [
        "block_gap",
        "bad_parent",
        "bad_hash",
        "duplicate_tx",
        "duplicate_log",
        "removed",
        "wrong_contract",
        "failed_event",
        "foreign_tx",
        "conflicting_log_tx",
    ],
)
def test_snapshot_integrity(kind):
    p = sample()[0]
    if kind == "block_gap":
        p["blocks"].pop(20)
    elif kind == "bad_parent":
        p["blocks"][1]["parent_hash"] = hash_number(99999)
    elif kind == "bad_hash":
        p["transactions"][0]["block_hash"] = hash_number(99999)
    elif kind == "duplicate_tx":
        p["transactions"].append(copy.deepcopy(p["transactions"][0]))
    elif kind == "duplicate_log":
        p["logs"].append(copy.deepcopy(p["logs"][0]))
    elif kind == "removed":
        p["logs"][0]["removed"] = True
    elif kind == "wrong_contract":
        p["logs"][0]["address"] = PEER
    elif kind == "failed_event":
        p["transactions"][0]["status"] = 0
    elif kind == "foreign_tx":
        p["transactions"][0]["from_address"] = PEER
        p["transactions"][0]["to_address"] = PEER
    elif kind == "conflicting_log_tx":
        p["logs"][0]["transaction_hash"] = hash_number(88888)
    with pytest.raises(ValueError):
        normalize(SnapshotInput(**p))


def test_preview_roundtrip_and_bad_json():
    p, q = sample()
    out = preview(json.dumps(p))
    assert out["snapshot"] == p
    assert out["quality"]["source_verified"] is False
    with pytest.raises(ValueError):
        preview("bad")
