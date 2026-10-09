"""Structural block/event integrity, not cryptographic chain verification."""

import json
from pydantic import ValidationError
from .schemas import SnapshotInput


def normalize(data):
    p = data.model_dump(mode="json")
    p["blocks"] = sorted(p["blocks"], key=lambda b: b["number"])
    blocks = p["blocks"]
    headers = {x["number"]: x for x in blocks}
    if len(headers) != len(blocks):
        raise ValueError("Duplicate block number.")
    if len({b["hash"] for b in blocks}) != len(blocks):
        raise ValueError("Duplicate block hash.")
    for a, b in zip(blocks, blocks[1:]):
        if b["number"] != a["number"] + 1 or b["parent_hash"] != a["hash"] or b["timestamp"] <= a["timestamp"]:
            raise ValueError("Require contiguous blocks, matching parent hashes and increasing timestamps.")
    contracts = {x["address"]: x for x in p["contracts"]}
    if len(contracts) != len(p["contracts"]):
        raise ValueError("Duplicate watched contract.")
    txs = {}
    positions = set()
    for t in p["transactions"]:
        if t["hash"] in txs or (t["block_number"], t["transaction_index"]) in positions:
            raise ValueError("Duplicate transaction hash or block/index.")
        if t["from_address"] != p["wallet_address"] and t["to_address"] != p["wallet_address"]:
            raise ValueError("Transaction is unrelated to the watched wallet.")
        check_header(t, headers)
        txs[t["hash"]] = t
        positions.add((t["block_number"], t["transaction_index"]))
    seen = set()
    log_positions = set()
    log_txs = {}
    hash_by_position = {(t["block_number"], t["transaction_index"]): t["hash"] for t in txs.values()}
    for e in p["logs"]:
        check_header(e, headers)
        key = (e["transaction_hash"], e["log_index"])
        position = (e["block_number"], e["log_index"])
        if key in seen or position in log_positions:
            raise ValueError("Duplicate contract event identity or block log index.")
        seen.add(key)
        log_positions.add(position)
        if e["address"] not in contracts:
            raise ValueError("Event is outside watched contracts.")
        locator = (e["block_number"], e["transaction_index"])
        if hash_by_position.setdefault(locator, e["transaction_hash"]) != e["transaction_hash"]:
            raise ValueError("Different event transaction hashes claim the same block/index.")
        prior = log_txs.setdefault(e["transaction_hash"], locator)
        if prior != locator:
            raise ValueError("Event transaction has inconsistent block/index.")
        if e["transaction_hash"] in txs:
            t = txs[e["transaction_hash"]]
            if locator != (t["block_number"], t["transaction_index"]) or t["status"] != 1:
                raise ValueError("Event conflicts with transaction identity or failed receipt.")
    p["transactions"] = sorted(p["transactions"], key=lambda t: (t["block_number"], t["transaction_index"]))
    p["logs"] = sorted(p["logs"], key=lambda e: (e["block_number"], e["transaction_index"], e["log_index"]))
    p["contracts"] = sorted(p["contracts"], key=lambda c: c["address"])
    quality = dict(
        start_block=blocks[0]["number"],
        end_block=blocks[-1]["number"],
        end_block_hash=blocks[-1]["hash"],
        block_count=len(blocks),
        transaction_count=len(txs),
        log_count=len(p["logs"]),
        source_verified=False,
        finality="user-supplied snapshot; not independently verified",
        warnings=[
            "No cryptographic proof or completeness guarantee.",
            "Standard RPC top-level transactions omit internal ETH transfers.",
            "Token metadata is declared by the uploader; a Transfer-shaped log does not certify a genuine ERC-20 token.",
        ],
    )
    return p, quality


def check_header(row, headers):
    b = headers.get(row["block_number"])
    if b is None or b["hash"] != row["block_hash"]:
        raise ValueError("Record block is missing or hash differs from its header.")


def preview(text):
    try:
        obj = json.loads(text)
        data = SnapshotInput.model_validate(obj)
        p, q = normalize(data)
        return dict(snapshot=p, quality=q)
    except (json.JSONDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            message = "; ".join(".".join(map(str, e["loc"])) + ": " + e["msg"] for e in exc.errors()[:5])
        else:
            message = "Use valid JSON snapshot data."
        raise ValueError(message) from None
