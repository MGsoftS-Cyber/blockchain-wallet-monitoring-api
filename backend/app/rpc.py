"""Optional bounded read-only RPC preview; server environment chooses the endpoint."""

import time
from urllib.parse import urlsplit
import requests
from web3 import Web3
from fastapi import HTTPException
from . import config
from .schemas import SnapshotInput
from .imports import normalize

ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "balance", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]


def client():
    url = config.ETHEREUM_RPC_URL
    if not url:
        raise HTTPException(
            503, "Configure ETHEREUM_RPC_URL on the server to enable read-only RPC preview. Offline imports still work."
        )
    if urlsplit(url).scheme not in {"http", "https"}:
        raise HTTPException(503, "RPC endpoint must use HTTP or HTTPS.")
    session = requests.Session()
    session.trust_env = False
    return Web3(
        Web3.HTTPProvider(url, request_kwargs={"timeout": 5}, session=session, exception_retry_configuration=None)
    )


def hexvalue(v):
    return v.lower() if isinstance(v, str) else Web3.to_hex(v).lower()


def fetch(address, data, w3=None):
    w3 = w3 if w3 is not None else client()
    deadline = time.monotonic() + 30

    def read(fn):
        if time.monotonic() > deadline:
            raise ValueError("RPC time budget exhausted.")
        result = fn()
        if time.monotonic() > deadline:
            raise ValueError("RPC time budget exhausted.")
        return result

    try:
        if read(lambda: w3.eth.chain_id) != 1:
            raise ValueError("Wrong chain.")
        head = read(lambda: w3.eth.get_block("finalized"))
        end = int(head["number"])
        start = max(0, end - data.block_count + 1)
        wallet = Web3.to_checksum_address(address)
        blocks = []
        transactions = []
        warnings = []
        for number in range(start, end + 1):
            b = read(lambda n=number: w3.eth.get_block(n, full_transactions=True))
            if int(b["number"]) != number:
                raise ValueError("Provider returned a different block number.")
            if len(b["transactions"]) > 1000:
                raise ValueError("Block exceeds supported transaction count.")
            bh = hexvalue(b["hash"])
            blocks.append(
                dict(number=number, hash=bh, parent_hash=hexvalue(b["parentHash"]), timestamp=int(b["timestamp"]))
            )
            for t in b["transactions"]:
                sender = str(t["from"]).lower()
                receiver = str(t["to"]).lower() if t["to"] else None
                if address not in {sender, receiver}:
                    continue
                if len(transactions) >= 100:
                    raise ValueError("Wallet receipt count exceeds supported preview size.")
                receipt = read(lambda tx=t: w3.eth.get_transaction_receipt(tx["hash"]))
                if hexvalue(receipt["transactionHash"]) != hexvalue(t["hash"]):
                    raise ValueError("Receipt transaction mismatch.")
                if (
                    hexvalue(receipt["blockHash"]) != bh
                    or int(receipt["blockNumber"]) != number
                    or int(receipt["transactionIndex"]) != int(t["transactionIndex"])
                ):
                    raise ValueError("Receipt block mismatch.")
                if int(t.get("type", 0)) == 3 and ("blobGasUsed" not in receipt or "blobGasPrice" not in receipt):
                    raise ValueError("Blob fee metadata missing.")
                transactions.append(
                    dict(
                        hash=hexvalue(t["hash"]),
                        block_number=number,
                        block_hash=bh,
                        transaction_index=int(t["transactionIndex"]),
                        from_address=sender,
                        to_address=receiver,
                        value_wei=str(int(t["value"])),
                        gas_used=int(receipt["gasUsed"]),
                        effective_gas_price_wei=str(int(receipt["effectiveGasPrice"])),
                        blob_gas_used=int(receipt.get("blobGasUsed", 0)),
                        blob_gas_price_wei=str(int(receipt.get("blobGasPrice", 0))),
                        status=int(receipt["status"]),
                    )
                )
        closing = str(read(lambda: w3.eth.get_balance(wallet, end)))
        opening = None
        if start > 0:
            try:
                opening = str(read(lambda: w3.eth.get_balance(wallet, start - 1)))
            except Exception:
                warnings.append("Opening native balance unavailable from provider.")
        contracts = []
        for spec in data.contracts:
            c = spec.model_dump(mode="json")
            c["opening_balance"] = None
            c["closing_balance"] = None
            if spec.token_decimals is not None:
                try:
                    contract = w3.eth.contract(address=Web3.to_checksum_address(spec.address), abi=ABI)
                    decimals = int(read(lambda ct=contract: ct.functions.decimals().call(block_identifier=end)))
                    if decimals != spec.token_decimals:
                        raise ValueError("Declared decimals differ from contract.")
                    c["closing_balance"] = str(
                        read(lambda ct=contract: ct.functions.balanceOf(wallet).call(block_identifier=end))
                    )
                    if start > 0:
                        try:
                            c["opening_balance"] = str(
                                read(
                                    lambda ct=contract: ct.functions.balanceOf(wallet).call(block_identifier=start - 1)
                                )
                            )
                        except Exception:
                            warnings.append("Opening token balance unavailable.")
                except Exception:
                    warnings.append(
                        "A token balance or decimals call failed; balance remains unavailable when no closing value was obtained."
                    )
            contracts.append(c)
        logs = []
        if contracts:
            raw = read(
                lambda: w3.eth.get_logs(
                    {
                        "fromBlock": start,
                        "toBlock": end,
                        "address": [Web3.to_checksum_address(c["address"]) for c in contracts],
                    }
                )
            )
            if len(raw) > 1000:
                raise ValueError("Event count exceeds supported preview size.")
            for e in raw:
                logs.append(
                    dict(
                        transaction_hash=hexvalue(e["transactionHash"]),
                        block_number=int(e["blockNumber"]),
                        block_hash=hexvalue(e["blockHash"]),
                        transaction_index=int(e["transactionIndex"]),
                        log_index=int(e["logIndex"]),
                        address=str(e["address"]).lower(),
                        topics=[hexvalue(t) for t in e["topics"]],
                        data=hexvalue(e["data"]),
                        removed=bool(e.get("removed", False)),
                    )
                )
        after = read(lambda: w3.eth.get_block(end))
        if hexvalue(after["hash"]) != hexvalue(head["hash"]) or blocks[-1]["hash"] != hexvalue(head["hash"]):
            raise ValueError("Finalized header changed during preview.")
        snapshot, quality = normalize(
            SnapshotInput(
                wallet_address=address,
                source="Configured Ethereum RPC preview",
                blocks=blocks,
                opening_native_wei=opening,
                closing_native_wei=closing,
                contracts=contracts,
                transactions=transactions,
                logs=logs,
            )
        )
        return dict(
            snapshot=snapshot,
            quality=quality,
            rpc_evidence=dict(
                finalized_block=end,
                finalized_hash=hexvalue(head["hash"]),
                header_rechecked=True,
                warnings=warnings,
                interpretation="Provider-reported finalized state; committing a reviewed upload does not retain an independent proof.",
            ),
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            502,
            "RPC preview could not produce a consistent supported Ethereum snapshot. Check provider availability, finality support and scan limits.",
        ) from None
