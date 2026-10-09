"""Exercise real Web3 formatting against an in-memory JSON-RPC provider."""

import time
import copy
import pytest
from fastapi import HTTPException
from web3 import Web3
from web3.providers import BaseProvider
from app.rpc import fetch, client
from app import config
from app.schemas import RpcPreviewInput
from app.demo import WALLET, PEER, TOKEN, hash_number, topic_address
from app.events import TRANSFER_TOPIC


class FixtureProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.requests = []
        self.chain = 1
        self.changed = False
        self.recheck = 0
        self.bad_receipt = False
        self.token_error = False
        self.too_many_logs = False
        self.removed = False

    def make_request(self, method, params):
        self.requests.append((method, params))
        h = hash_number(100)
        tx = hash_number(700)
        if method == "eth_chainId":
            result = hex(self.chain)
        elif method == "eth_getBlockByNumber":
            if params[0] == "finalized":
                pass
            else:
                self.recheck += 1
            result = dict(
                number=hex(100),
                hash=hash_number(999) if self.changed and self.recheck > 1 else h,
                parentHash=hash_number(99),
                timestamp=hex(int(time.time()) - 100),
                transactions=[
                    dict(
                        hash=tx,
                        blockNumber=hex(100),
                        blockHash=h,
                        transactionIndex="0x0",
                        **{"from": WALLET, "to": PEER},
                        value=hex(10**16),
                        type="0x2",
                    )
                ],
            )
        elif method == "eth_getTransactionReceipt":
            result = dict(
                transactionHash=hash_number(999) if self.bad_receipt else tx,
                blockHash=h,
                blockNumber=hex(100),
                transactionIndex="0x0",
                status="0x1",
                gasUsed=hex(21000),
                effectiveGasPrice=hex(10**9),
                logs=[],
            )
        elif method == "eth_getBalance":
            result = hex(10**18)
        elif method == "eth_call":
            if self.token_error:
                return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "secret-url-api-token"}}
            data = params[0].get("data", "")
            result = "0x" + f"{6 if data.startswith('0x313ce567') else 10**6:064x}"
        elif method == "eth_getLogs":
            event = dict(
                transactionHash=tx,
                blockHash=h,
                blockNumber=hex(100),
                transactionIndex="0x0",
                logIndex="0x0",
                address=TOKEN,
                topics=[TRANSFER_TOPIC, topic_address(WALLET), topic_address(PEER)],
                data="0x" + f"{10**6:064x}",
                removed=self.removed,
            )
            result = [event] * 1001 if self.too_many_logs else [event]
        else:
            raise AssertionError("Unexpected RPC method: " + method)
        return {"jsonrpc": "2.0", "id": 1, "result": copy.deepcopy(result)}


def data():
    return RpcPreviewInput(block_count=1, contracts=[{"address": TOKEN, "label": "TOKEN", "token_decimals": 6}])


def test_real_web3_read_only_preview():
    provider = FixtureProvider()
    r = fetch(WALLET, data(), Web3(provider))
    assert r["rpc_evidence"]["finalized_block"] == 100
    assert r["rpc_evidence"]["header_rechecked"]
    assert r["snapshot"]["contracts"][0]["closing_balance"] == "1000000"
    assert r["snapshot"]["transactions"][0]["value_wei"] == "10000000000000000"
    assert r["snapshot"]["logs"][0]["topics"][0] == TRANSFER_TOPIC
    assert not any("send" in m.lower() or "sign" in m.lower() for m, p in provider.requests)


@pytest.mark.parametrize("fault", ["wrong_chain", "changed_hash", "bad_receipt", "too_many_logs", "removed"])
def test_rpc_rejects_inconsistent_or_excessive_results(fault):
    provider = FixtureProvider()
    if fault == "wrong_chain":
        provider.chain = 137
    elif fault == "changed_hash":
        provider.changed = True
    elif fault == "bad_receipt":
        provider.bad_receipt = True
    elif fault == "too_many_logs":
        provider.too_many_logs = True
    elif fault == "removed":
        provider.removed = True
    with pytest.raises(HTTPException) as exc:
        fetch(WALLET, data(), Web3(provider))
    assert exc.value.status_code == 502
    assert "secret" not in exc.value.detail


def test_token_call_failure_yields_null_balance():
    p = FixtureProvider()
    p.token_error = True
    r = fetch(WALLET, data(), Web3(p))
    assert r["snapshot"]["contracts"][0]["closing_balance"] is None
    assert r["rpc_evidence"]["warnings"]
    assert "secret-url" not in str(r)


def test_unconfigured_rpc_is_explicit(monkeypatch):
    monkeypatch.setattr(config, "ETHEREUM_RPC_URL", "")
    with pytest.raises(HTTPException) as exc:
        client()
    assert exc.value.status_code == 503


def test_http_provider_configuration_without_network(monkeypatch):
    monkeypatch.setattr(config, "ETHEREUM_RPC_URL", "http://127.0.0.1:8545")
    w3 = client()
    assert w3.provider.endpoint_uri == "http://127.0.0.1:8545"
    assert w3.provider.exception_retry_configuration is None
