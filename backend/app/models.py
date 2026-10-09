"""Owner-scoped wallets, immutable snapshots and monitoring analyses."""

import time
from uuid import uuid4
from sqlalchemy import String, Text, Float, ForeignKey, JSON, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def new_id():
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("user_id", "chain_id", "address"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(42))
    chain_id: Mapped[int] = mapped_column(Integer, default=1)


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("wallet_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    quality: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"), index=True)
    inputs: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class RequestRecord(Base):
    __tablename__ = "request_records"
    __table_args__ = (UniqueConstraint("user_id", "scope", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
