"""Ethereum public data contracts: integer base units, hashes and block identity."""

import re
import time
from typing import Annotated
from pydantic import Field, BeforeValidator, field_validator, model_validator
from web3 import Web3
from .auth_schemas import Credentials, StrictModel  # noqa: F401


def address(v):
    if not isinstance(v, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", v):
        raise ValueError("Use a 20-byte 0x Ethereum address.")
    body = v[2:]
    if body != body.lower() and body != body.upper() and not Web3.is_checksum_address(v):
        raise ValueError("Mixed-case address has an invalid EIP-55 checksum.")
    return v.lower()


def uint(v):
    if not isinstance(v, str) or not re.fullmatch(r"[0-9]{1,78}", v) or int(v) >= 2**256:
        raise ValueError("Use an unsigned uint256 decimal string.")
    return str(int(v))


Address = Annotated[str, BeforeValidator(address)]
UInt = Annotated[str, BeforeValidator(uint)]
Hash = Annotated[str, Field(pattern=r"^0x[0-9a-f]{64}$")]
BlockNumber = Annotated[int, Field(ge=0, le=2**53 - 1, strict=True)]


class WalletInput(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    address: Address
    chain_id: Annotated[int, Field(strict=True, ge=1, le=1)] = 1


class BlockInput(StrictModel):
    number: BlockNumber
    hash: Hash
    parent_hash: Hash
    timestamp: int = Field(ge=0, le=2**53 - 1, strict=True)

    @field_validator("timestamp")
    @classmethod
    def past(cls, v):
        if v > int(time.time()):
            raise ValueError("Block timestamp cannot be future.")
        return v


class ContractInput(StrictModel):
    address: Address
    label: str = Field(min_length=1, max_length=40)
    token_decimals: int | None = Field(default=None, ge=0, le=36, strict=True)
    opening_balance: UInt | None = None
    closing_balance: UInt | None = None


class TransactionInput(StrictModel):
    hash: Hash
    block_number: BlockNumber
    block_hash: Hash
    transaction_index: int = Field(ge=0, le=100000, strict=True)
    from_address: Address
    to_address: Address | None = None
    value_wei: UInt
    gas_used: int = Field(ge=0, le=1000000000, strict=True)
    effective_gas_price_wei: UInt
    blob_gas_used: int = Field(default=0, ge=0, le=1000000000, strict=True)
    blob_gas_price_wei: UInt = "0"
    status: Annotated[int, Field(strict=True, ge=0, le=1)]


class LogInput(StrictModel):
    transaction_hash: Hash
    block_number: BlockNumber
    block_hash: Hash
    transaction_index: int = Field(ge=0, le=100000, strict=True)
    log_index: int = Field(ge=0, le=1000000, strict=True)
    address: Address
    topics: list[Hash] = Field(default_factory=list, max_length=4)
    data: str = Field(pattern=r"^0x(?:[0-9a-f]{2})*$", max_length=8194)
    removed: bool = False

    @field_validator("removed")
    @classmethod
    def canonical(cls, v):
        if v:
            raise ValueError("Removed logs cannot enter a canonical snapshot.")
        return v


class SnapshotInput(StrictModel):
    chain_id: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    wallet_address: Address
    source: str = Field(min_length=1, max_length=200)
    blocks: list[BlockInput] = Field(min_length=1, max_length=1000)
    opening_native_wei: UInt | None = None
    closing_native_wei: UInt
    contracts: list[ContractInput] = Field(default_factory=list, max_length=5)
    transactions: list[TransactionInput] = Field(default_factory=list, max_length=5000)
    logs: list[LogInput] = Field(default_factory=list, max_length=10000)


class JsonPreviewInput(StrictModel):
    snapshot_json: str = Field(min_length=1, max_length=6000000)


class AssetThreshold(StrictModel):
    asset_id: str
    amount_base_units: UInt

    @field_validator("asset_id")
    @classmethod
    def asset(cls, v):
        return v if v == "native" else address(v)

    @field_validator("amount_base_units")
    @classmethod
    def positive(cls, v):
        if int(v) == 0:
            raise ValueError("Threshold must be positive.")
        return v


class AnalysisInput(StrictModel):
    snapshot_id: str = Field(min_length=1, max_length=36)
    name: str = Field(default="Wallet activity review", min_length=1, max_length=120)
    enable_ml: bool = True
    large_transfer_thresholds: list[AssetThreshold] = Field(default_factory=list, max_length=6)
    high_fee_wei: UInt = "10000000000000000"
    burst_count: int = Field(default=10, ge=2, le=1000, strict=True)
    burst_window_seconds: int = Field(default=60, ge=1, le=86400, strict=True)
    concentration_limit: float = Field(default=0.7, gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def unique(self):
        ids = [x.asset_id for x in self.large_transfer_thresholds]
        if len(ids) != len(set(ids)):
            raise ValueError("Use one threshold per asset.")
        if int(self.high_fee_wei) == 0:
            raise ValueError("High-fee threshold must be positive.")
        return self


class RpcPreviewInput(StrictModel):
    block_count: int = Field(default=5, ge=1, le=20, strict=True)
    contracts: list[ContractInput] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def specs_only(self):
        if any(x.opening_balance is not None or x.closing_balance is not None for x in self.contracts):
            raise ValueError("RPC request specifies contract metadata, not balances.")
        if len({x.address for x in self.contracts}) != len(self.contracts):
            raise ValueError("Use distinct contract addresses.")
        return self
