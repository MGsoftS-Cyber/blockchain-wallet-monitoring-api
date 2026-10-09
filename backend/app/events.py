"""Native transfers and shape-compatible ERC-20 logs retain exact base units."""

from web3 import Web3

TRANSFER_TOPIC = "0x" + Web3.keccak(text="Transfer(address,address,uint256)").hex().removeprefix("0x")


def units(amount, decimals):
    n = int(amount)
    base = 10**decimals
    whole, remainder = divmod(n, base)
    if not remainder:
        return str(whole)
    return str(whole) + "." + str(remainder).zfill(decimals).rstrip("0")


def direction(sender, receiver, wallet):
    return (
        "self"
        if sender == receiver == wallet
        else "out"
        if sender == wallet
        else "in"
        if receiver == wallet
        else "unrelated"
    )


def decode(snapshot):
    wallet = snapshot["wallet_address"]
    headers = {x["number"]: x for x in snapshot["blocks"]}
    contracts = {x["address"]: x for x in snapshot["contracts"]}
    transfers = []
    transactions = []
    events = []
    for t in snapshot["transactions"]:
        outgoing = t["from_address"] == wallet
        fee = (
            (
                t["gas_used"] * int(t["effective_gas_price_wei"])
                + t.get("blob_gas_used", 0) * int(t.get("blob_gas_price_wei", "0"))
            )
            if outgoing
            else 0
        )
        tx = dict(
            **t,
            fee_paid_wei=str(fee),
            timestamp=headers[t["block_number"]]["timestamp"],
            direction=direction(t["from_address"], t["to_address"], wallet),
        )
        transactions.append(tx)
        if t["status"] == 1 and int(t["value_wei"]) > 0:
            transfers.append(
                dict(
                    event_id=t["hash"] + ":native",
                    transaction_hash=t["hash"],
                    block_number=t["block_number"],
                    transaction_index=t["transaction_index"],
                    log_index=-1,
                    timestamp=tx["timestamp"],
                    asset_id="native",
                    label="ETH",
                    decimals=18,
                    from_address=t["from_address"],
                    to_address=t["to_address"],
                    direction=tx["direction"],
                    amount_base_units=t["value_wei"],
                    amount=units(t["value_wei"], 18),
                    source="successful_top_level_value",
                )
            )
    for e in snapshot["logs"]:
        c = contracts[e["address"]]
        item = dict(
            **e, timestamp=headers[e["block_number"]]["timestamp"], event_type="raw_contract_log", wallet_related=None
        )
        if (
            c["token_decimals"] is not None
            and len(e["topics"]) == 3
            and e["topics"][0] == TRANSFER_TOPIC
            and len(e["data"]) == 66
            and all(t[2:26] == "0" * 24 for t in e["topics"][1:])
        ):
            sender = "0x" + e["topics"][1][-40:]
            receiver = "0x" + e["topics"][2][-40:]
            d = direction(sender, receiver, wallet)
            amount = str(int(e["data"], 16))
            item.update(
                event_type="erc20_compatible_transfer",
                wallet_related=d != "unrelated",
                from_address=sender,
                to_address=receiver,
                amount_base_units=amount,
            )
            if d != "unrelated":
                transfers.append(
                    dict(
                        event_id=e["transaction_hash"] + ":" + str(e["log_index"]),
                        transaction_hash=e["transaction_hash"],
                        block_number=e["block_number"],
                        transaction_index=e["transaction_index"],
                        log_index=e["log_index"],
                        timestamp=item["timestamp"],
                        asset_id=e["address"],
                        label=c["label"],
                        decimals=c["token_decimals"],
                        from_address=sender,
                        to_address=receiver,
                        direction=d,
                        amount_base_units=amount,
                        amount=units(amount, c["token_decimals"]),
                        source="erc20_compatible_log",
                    )
                )
        events.append(item)
    transfers.sort(key=lambda t: (t["block_number"], t["transaction_index"], t["log_index"]))
    return transactions, transfers, events
