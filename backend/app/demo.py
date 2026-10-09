"""Synthetic mainnet-shaped data, not actual Ethereum history."""

import time
from .events import TRANSFER_TOPIC
from .schemas import SnapshotInput
from .imports import normalize

WALLET = "0x" + "1" * 40
PEER = "0x" + "2" * 40
NEW_PEER = "0x" + "3" * 40
TOKEN = "0x" + "4" * 40


def hash_number(n):
    return "0x" + f"{n:064x}"


def topic_address(a):
    return "0x" + "0" * 24 + a[2:]


def sample():
    blocks = []
    txs = []
    logs = []
    timestamp = int(time.time()) - 86400
    native = 5 * 10**18
    tokens = 1000 * 10**6
    for i in range(90):
        number = 1000 + i
        bh = hash_number(number)
        blocks.append(dict(number=number, hash=bh, parent_hash=hash_number(number - 1), timestamp=timestamp + i * 12))
        outgoing = i % 2 == 0
        sender = WALLET if outgoing else PEER
        recipient = (NEW_PEER if i >= 60 else PEER) if outgoing else WALLET
        amount = 10**16 + (i % 7) * 10**12
        if i == 70:
            amount = 5 * 10**17
        status = 0 if i == 80 else 1
        gas = 800000 if i == 60 else 21000
        gas_price = 50 * 10**9 if i == 60 else 10 * 10**9
        txhash = hash_number(100000 + i)
        txs.append(
            dict(
                hash=txhash,
                block_number=number,
                block_hash=bh,
                transaction_index=0,
                from_address=sender,
                to_address=recipient,
                value_wei=str(amount),
                gas_used=gas,
                effective_gas_price_wei=str(gas_price),
                status=status,
            )
        )
        if status:
            native += -amount if outgoing else amount
        if outgoing:
            native -= gas * gas_price
        if i < 70 and status:
            token_amount = 200 * 10**6 if i == 60 else 10**6 + (i % 5) * 100
            tokens += -token_amount if outgoing else token_amount
            logs.append(
                dict(
                    transaction_hash=txhash,
                    block_number=number,
                    block_hash=bh,
                    transaction_index=0,
                    log_index=0,
                    address=TOKEN,
                    topics=[TRANSFER_TOPIC, topic_address(sender), topic_address(recipient)],
                    data="0x" + f"{token_amount:064x}",
                )
            )
            if i == 40:
                logs.append(
                    dict(
                        transaction_hash=txhash,
                        block_number=number,
                        block_hash=bh,
                        transaction_index=0,
                        log_index=1,
                        address=TOKEN,
                        topics=[hash_number(123)],
                        data="0x1234",
                    )
                )
    return normalize(
        SnapshotInput(
            wallet_address=WALLET,
            source="Synthetic offline wallet demonstration",
            blocks=blocks,
            opening_native_wei=str(5 * 10**18),
            closing_native_wei=str(native),
            contracts=[
                dict(
                    address=TOKEN,
                    label="DEMO",
                    token_decimals=6,
                    opening_balance=str(1000 * 10**6),
                    closing_balance=str(tokens),
                )
            ],
            transactions=txs,
            logs=logs,
        )
    )
