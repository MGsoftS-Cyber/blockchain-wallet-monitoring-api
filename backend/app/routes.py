"""Owner-scoped public wallet snapshots and immutable monitoring reports."""

import csv
import io
import json
import hashlib
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from .database import get_db
from .security import current_user
from .models import Wallet, Snapshot, Analysis
from .schemas import WalletInput, SnapshotInput, AnalysisInput, JsonPreviewInput, RpcPreviewInput
from .services import mutation
from .imports import normalize, preview
from .engine import evaluate, ENGINE_VERSION
from .rpc import fetch
from .demo import sample

router = APIRouter(prefix="/api/v1")
Key = Header(min_length=1, max_length=100)


def owned_wallet(db, identifier, user):
    x = db.scalar(select(Wallet).where(Wallet.id == identifier, Wallet.user_id == user.id))
    if not x:
        raise HTTPException(404, "Wallet not found in your account.")
    return x


def owned_analysis(db, identifier, user):
    x = db.scalar(select(Analysis).join(Wallet).where(Analysis.id == identifier, Wallet.user_id == user.id))
    if not x:
        raise HTTPException(404, "Analysis not found in your account.")
    return x


def wallet_view(x):
    return dict(id=x.id, label=x.label, address=x.address, chain_id=x.chain_id)


def snapshot_view(x):
    return dict(id=x.id, wallet_id=x.wallet_id, snapshot=x.payload, quality=x.quality, created_at=x.created_at)


def analysis_view(x):
    return dict(
        id=x.id,
        wallet_id=x.wallet_id,
        snapshot_id=x.snapshot_id,
        inputs=x.inputs,
        results=x.results,
        engine_version=x.engine_version,
        created_at=x.created_at,
    )


def fingerprint(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


@router.get("/wallets")
def wallets(user=Depends(current_user), db=Depends(get_db)):
    return [wallet_view(x) for x in db.scalars(select(Wallet).where(Wallet.user_id == user.id))]


@router.post("/wallets", status_code=201)
def create_wallet(data: WalletInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        x = Wallet(user_id=user.id, **data.model_dump())
        db.add(x)
        db.flush()
        return wallet_view(x)

    return mutation(db, user, "wallet", idempotency_key, data.model_dump(mode="json"), work)


@router.post("/imports/preview")
def import_preview(data: JsonPreviewInput, user=Depends(current_user)):
    try:
        return preview(data.snapshot_json)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/wallets/{identifier}/snapshots")
def snapshots(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    owned_wallet(db, identifier, user)
    return [
        snapshot_view(x)
        for x in db.scalars(
            select(Snapshot).where(Snapshot.wallet_id == identifier).order_by(Snapshot.created_at.desc())
        )
    ]


@router.post("/wallets/{identifier}/snapshots", status_code=201)
def create_snapshot(
    identifier: str, data: SnapshotInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    w = owned_wallet(db, identifier, user)
    if data.wallet_address != w.address or data.chain_id != w.chain_id:
        raise HTTPException(422, "Snapshot chain/address must match the watched wallet.")
    try:
        p, q = normalize(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    digest = fingerprint(p)

    def work():
        prior = db.scalar(select(Snapshot).where(Snapshot.wallet_id == identifier, Snapshot.fingerprint == digest))
        if prior:
            return snapshot_view(prior)
        x = Snapshot(wallet_id=identifier, payload=p, quality=q, fingerprint=digest)
        db.add(x)
        db.flush()
        return snapshot_view(x)

    return mutation(db, user, "snapshot:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.post("/wallets/{identifier}/rpc-preview")
def rpc_preview(identifier: str, data: RpcPreviewInput, user=Depends(current_user), db=Depends(get_db)):
    w = owned_wallet(db, identifier, user)
    return fetch(w.address, data)


@router.post("/wallets/{identifier}/analyses", status_code=201)
def analyze(
    identifier: str, data: AnalysisInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    w = owned_wallet(db, identifier, user)
    s = db.scalar(select(Snapshot).where(Snapshot.id == data.snapshot_id, Snapshot.wallet_id == identifier))
    if not s:
        raise HTTPException(404, "Snapshot not found in this wallet.")
    inputs = dict(**data.model_dump(mode="json"), wallet=wallet_view(w), snapshot=s.payload, quality=s.quality)

    def work():
        try:
            results = evaluate(inputs)
            json.dumps(results, allow_nan=False)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        x = Analysis(
            wallet_id=identifier, snapshot_id=s.id, inputs=inputs, results=results, engine_version=ENGINE_VERSION
        )
        db.add(x)
        db.flush()
        return analysis_view(x)

    return mutation(db, user, "analysis:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.get("/analyses")
def analyses(user=Depends(current_user), db=Depends(get_db)):
    return [
        analysis_view(x)
        for x in db.scalars(
            select(Analysis)
            .join(Wallet)
            .where(Wallet.user_id == user.id)
            .order_by(Analysis.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/analyses/{identifier}")
def analysis(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    return analysis_view(owned_analysis(db, identifier, user))


@router.get("/analyses/{identifier}/report")
def report(identifier: str, format: str = "json", user=Depends(current_user), db=Depends(get_db)):
    x = owned_analysis(db, identifier, user)
    if format == "json":
        text = json.dumps(analysis_view(x), indent=2)
        media = "application/json"
        ext = "json"
    elif format in {"balances", "transactions", "transfers", "contract_events", "alerts", "model_scores"}:
        keys = {
            "balances": ["asset_id", "label", "decimals", "balance_base_units", "balance", "status"],
            "transactions": [
                "hash",
                "block_number",
                "transaction_index",
                "from_address",
                "to_address",
                "value_wei",
                "status",
                "gas_used",
                "effective_gas_price_wei",
                "blob_gas_used",
                "blob_gas_price_wei",
                "fee_paid_wei",
                "timestamp",
                "direction",
            ],
            "transfers": [
                "event_id",
                "transaction_hash",
                "block_number",
                "timestamp",
                "asset_id",
                "label",
                "decimals",
                "from_address",
                "to_address",
                "direction",
                "amount_base_units",
                "amount",
                "source",
            ],
            "contract_events": [
                "transaction_hash",
                "block_number",
                "log_index",
                "address",
                "topics",
                "data",
                "event_type",
                "wallet_related",
            ],
            "alerts": ["code", "message", "event_id", "timestamp", "evidence"],
            "model_scores": ["event_id", "asset_id", "score", "offset", "flagged"],
        }[format]
        rows = x.results["anomaly_model"]["scores"] if format == "model_scores" else x.results[format]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(keys)
        for row in rows:
            values = []
            for k in keys:
                v = row.get(k)
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, sort_keys=True)
                if (
                    isinstance(v, str)
                    and k
                    not in {
                        "balance_base_units",
                        "balance",
                        "amount_base_units",
                        "amount",
                        "value_wei",
                        "effective_gas_price_wei",
                        "blob_gas_price_wei",
                        "fee_paid_wei",
                    }
                    and v.lstrip().startswith(("=", "+", "-", "@"))
                ):
                    v = "'" + v
                values.append(v)
            writer.writerow(values)
        text = output.getvalue()
        media = "text/csv"
        ext = "csv"
    else:
        raise HTTPException(
            422, "Use json, balances, transactions, transfers, contract_events, alerts or model_scores."
        )
    return Response(
        text, media_type=media, headers={"Content-Disposition": f'attachment; filename="wallet-{format}-{x.id}.{ext}"'}
    )


@router.post("/demo", status_code=201)
def demo(idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        if db.scalar(select(Wallet).where(Wallet.user_id == user.id)):
            raise HTTPException(409, "Demo requires an empty wallet catalog.")
        p, q = sample()
        w = Wallet(user_id=user.id, label="Synthetic Ethereum Watch", address=p["wallet_address"], chain_id=1)
        db.add(w)
        db.flush()
        s = Snapshot(wallet_id=w.id, payload=p, quality=q, fingerprint=fingerprint(p))
        db.add(s)
        db.flush()
        return dict(
            wallet_id=w.id, snapshot_id=s.id, message="Synthetic public-data shapes, not actual Ethereum history."
        )

    return mutation(db, user, "demo", idempotency_key, {}, work)
