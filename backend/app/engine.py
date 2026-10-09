"""Balances and explained activity review from an immutable public-data snapshot."""

from collections import defaultdict, deque
from importlib.metadata import version
from .events import decode, units
from .anomalies import detect

ENGINE_VERSION = "wallet-1.0.0"


def evaluate(inputs):
    snapshot = inputs["snapshot"]
    txs, transfers, events = decode(snapshot)
    wallet = snapshot["wallet_address"]
    contracts = {c["address"]: c for c in snapshot["contracts"]}
    thresholds = {x["asset_id"]: int(x["amount_base_units"]) for x in inputs["large_transfer_thresholds"]}
    if any(k != "native" and k not in contracts for k in thresholds):
        raise ValueError("A threshold references an unwatched contract.")
    if any(k != "native" and contracts[k]["token_decimals"] is None for k in thresholds):
        raise ValueError("Token threshold requires declared token decimals.")
    alerts = []

    def emit(code, message, evidence, event_id=None, timestamp=None):
        alerts.append(dict(code=code, message=message, evidence=evidence, event_id=event_id, timestamp=timestamp))

    fees = sum(int(t["fee_paid_wei"]) for t in txs)
    for t in txs:
        if t["status"] == 0:
            emit(
                "FAILED_TRANSACTION",
                "Receipt reports a failed top-level transaction; its value is not counted as a successful transfer.",
                dict(transaction_hash=t["hash"], fee_paid_wei=t["fee_paid_wei"]),
                timestamp=t["timestamp"],
            )
        if int(t["fee_paid_wei"]) >= int(inputs["high_fee_wei"]):
            emit(
                "HIGH_TRANSACTION_FEE",
                "Watched wallet paid at least the configured receipt fee threshold.",
                dict(fee_paid_wei=t["fee_paid_wei"], threshold_wei=inputs["high_fee_wei"]),
                t["hash"],
                t["timestamp"],
            )
    summaries = {}
    recipients = defaultdict(lambda: defaultdict(int))
    seen = defaultdict(set)
    outcounts = defaultdict(int)
    window = deque()
    was_burst = False
    for t in transfers:
        asset = t["asset_id"]
        value = int(t["amount_base_units"])
        d = t["direction"]
        summary = summaries.setdefault(
            asset,
            dict(
                asset_id=asset,
                label=t["label"],
                decimals=t["decimals"],
                in_base_units=0,
                out_base_units=0,
                self_base_units=0,
                event_count=0,
            ),
        )
        summary["event_count"] += 1
        summary[d + "_base_units"] += value
        if asset in thresholds and value >= thresholds[asset] and d != "self":
            emit(
                "LARGE_TRANSFER",
                "Observed transfer reaches the configured threshold for this asset.",
                dict(asset_id=asset, amount_base_units=str(value), threshold_base_units=str(thresholds[asset])),
                t["event_id"],
                t["timestamp"],
            )
        if d == "out" and value > 0:
            recipient = t["to_address"] or "contract_creation"
            if recipient not in seen[asset] and outcounts[asset] >= 10:
                emit(
                    "NEW_OUTGOING_RECIPIENT",
                    "Recipient first appears after at least ten earlier outgoing transfers of this asset in the snapshot.",
                    dict(asset_id=asset, recipient=recipient, earlier_outgoing_events=outcounts[asset]),
                    t["event_id"],
                    t["timestamp"],
                )
            seen[asset].add(recipient)
            outcounts[asset] += 1
            recipients[asset][recipient] += value
        while window and window[0] <= t["timestamp"] - inputs["burst_window_seconds"]:
            window.popleft()
        window.append(t["timestamp"])
        burst = len(window) >= inputs["burst_count"]
        if burst and not was_burst:
            emit(
                "ACTIVITY_BURST",
                "Transfer count crosses the configured trailing-window threshold.",
                dict(count=len(window), window_seconds=inputs["burst_window_seconds"], threshold=inputs["burst_count"]),
                t["event_id"],
                t["timestamp"],
            )
        was_burst = burst
    concentration = []
    for asset, peers in sorted(recipients.items()):
        total = sum(peers.values())
        peer, amount = max(peers.items(), key=lambda x: x[1])
        share = amount / total
        concentration.append(
            dict(
                asset_id=asset,
                recipient=peer,
                amount_base_units=str(amount),
                total_out_base_units=str(total),
                share=share,
            )
        )
        if share >= inputs["concentration_limit"]:
            emit(
                "OUTGOING_CONCENTRATION",
                "A recipient has at least the configured share of observed outgoing amount for this asset.",
                dict(asset_id=asset, recipient=peer, share=share, threshold=inputs["concentration_limit"]),
            )
    native = summaries.get("native", {"in_base_units": 0, "out_base_units": 0})
    opening = snapshot["opening_native_wei"]
    closing = int(snapshot["closing_native_wei"])
    expected = int(opening) + native["in_base_units"] - native["out_base_units"] - fees if opening is not None else None
    gap = closing - expected if expected is not None else None
    reconciliation = dict(
        status="opening_unavailable"
        if gap is None
        else "matches_observed_top_level_flows"
        if gap == 0
        else "unreconciled",
        opening_native_wei=opening,
        closing_native_wei=str(closing),
        expected_closing_wei=str(expected) if expected is not None else None,
        gap_wei=str(gap) if gap is not None else None,
    )
    if gap not in {None, 0}:
        emit(
            "NATIVE_BALANCE_GAP",
            "Observed top-level transfers and fees do not explain the native balance change. Internal transfers or incomplete data may contribute.",
            dict(gap_wei=str(gap), expected_closing_wei=str(expected), observed_closing_wei=str(closing)),
        )
    token_reconciliation = []
    for c in snapshot["contracts"]:
        if c["token_decimals"] is None:
            continue
        flow = summaries.get(c["address"], {"in_base_units": 0, "out_base_units": 0})
        expected_token = (
            int(c["opening_balance"]) + flow["in_base_units"] - flow["out_base_units"]
            if c["opening_balance"] is not None
            else None
        )
        token_gap = (
            int(c["closing_balance"]) - expected_token
            if c["closing_balance"] is not None and expected_token is not None
            else None
        )
        token_reconciliation.append(
            dict(
                asset_id=c["address"],
                status="balance_unavailable"
                if token_gap is None
                else "matches_observed_transfer_logs"
                if token_gap == 0
                else "unreconciled",
                expected_closing_base_units=str(expected_token) if expected_token is not None else None,
                gap_base_units=str(token_gap) if token_gap is not None else None,
            )
        )
        if token_gap not in {None, 0}:
            emit(
                "TOKEN_BALANCE_GAP",
                "Observed Transfer-compatible logs do not explain the declared token balance change; incomplete logs or token-specific mechanics may contribute.",
                dict(asset_id=c["address"], gap_base_units=str(token_gap)),
            )
    balances = [
        dict(
            asset_id="native",
            label="ETH",
            decimals=18,
            balance_base_units=str(closing),
            balance=units(closing, 18),
            status="observed_snapshot_value",
        )
    ]
    for c in snapshot["contracts"]:
        if c["token_decimals"] is not None:
            balances.append(
                dict(
                    asset_id=c["address"],
                    label=c["label"],
                    decimals=c["token_decimals"],
                    balance_base_units=c["closing_balance"],
                    balance=units(c["closing_balance"], c["token_decimals"])
                    if c["closing_balance"] is not None
                    else None,
                    status="declared_snapshot_value" if c["closing_balance"] is not None else "unavailable",
                )
            )
    for summary in summaries.values():
        for key in ["in_base_units", "out_base_units", "self_base_units"]:
            summary[key] = str(summary[key])
    ml = detect(transfers, inputs["enable_ml"])
    for score in ml["scores"]:
        if score["flagged"]:
            emit(
                "UNUSUAL_TRANSFER_PATTERN",
                "IsolationForest score falls below the fitted earlier same-asset baseline threshold.",
                dict(asset_id=score["asset_id"], score=score["score"], offset=score["offset"]),
                score["event_id"],
            )
    return dict(
        engine_version=ENGINE_VERSION,
        wallet_address=wallet,
        chain_id=1,
        start_block=snapshot["blocks"][0]["number"],
        end_block=snapshot["blocks"][-1]["number"],
        end_block_hash=snapshot["blocks"][-1]["hash"],
        balances=balances,
        transactions=txs,
        transfers=transfers,
        contract_events=events,
        asset_flows=list(summaries.values()),
        concentration=concentration,
        total_fees_wei=str(fees),
        total_fees_eth=units(fees, 18),
        native_reconciliation=reconciliation,
        token_reconciliation=token_reconciliation,
        alerts=alerts,
        anomaly_model=ml,
        libraries={k: version(k) for k in ["web3", "numpy", "scikit-learn"]},
        limitations=[
            "Snapshot data is user supplied and not independently authenticated.",
            "No internal ETH tracing, fiat valuation, NFT balance accounting, token authenticity certification, wallet signing or transaction submission.",
            "Alerts describe observed data and are not fraud allegations or investment advice.",
        ],
    )
