# Blockchain Wallet Monitoring API - v1.0.0

Finance/crypto API #4. Read-only Ethereum mainnet wallet monitoring with exact balances/fees, raw contract logs, explained alerts and optional local Isolation Forest. Python 3.12, FastAPI, SQLAlchemy, Web3 and scikit-learn. No private keys, signing or transaction submission.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Windows: use py -3.12 -m venv .venv and the virtual environment's Scripts/Activate.ps1.
Open http://127.0.0.1:8011/docs. In another activated terminal, from project root:

```bash
python scripts/demo_client.py
```

The HTTP client registers a random account, creates a synthetic demo, previews/commits JSON, runs analysis, downloads JSON plus six CSV tables, retrieves Swagger/OpenAPI and logs out. It refreshes examples/ and docs/openapi.json. The examples are synthetic, not actual mainnet observations.

## API workflow

Register/login at /api/auth/register or /api/auth/login with email/password. Preserve the session cookie; send the returned csrf_token as X-CSRF-Token on authenticated POST requests. Creates also need Idempotency-Key: new key per new intent, same key/payload for retries. Changed payload under a used key returns 409.

1. POST /api/v1/wallets with label, address, chain_id: 1.
2. POST /api/v1/imports/preview with snapshot_json (JSON string); writes nothing.
3. POST /api/v1/wallets/{id}/snapshots with the reviewed snapshot object.
4. POST /api/v1/wallets/{id}/analyses with snapshot_id and optional thresholds.
5. GET /api/v1/analyses/{id}/report?format=json or balances, transactions, transfers, contract_events, alerts, model_scores.

GET wallet/snapshot/analysis routes are account-scoped. POST /api/v1/demo creates an offline starter wallet/snapshot. Full schemas: docs/openapi.json. Working integration: scripts/demo_client.py.

## Data and exact units

See examples/snapshot.json. Money is an unsigned integer **string** in base units, below 2^256. Native ETH uses 18 decimals; token decimals are declared per contract (0-36). Never supply money floats. Missing balance state stays null, not zero.

Blocks retain hashes/parent hashes/timestamps; transactions retain receipt status, gas used, effective gas price and optional blob fees; raw logs retain topics/data/block/transaction/log identity. Normalization rejects inconsistent identities and noncontiguous headers. Upload bounds: 1,000 blocks, 5,000 transactions, 10,000 logs, five contracts; JSON preview <=6 million characters. Add proxy body/rate limits for production.

## Optional RPC preview

Set server environment ETHEREUM_RPC_URL before starting. POST /api/v1/wallets/{id}/rpc-preview with {"block_count":5,"contracts":[]}. Contract specs accept address, label and token_decimals (null for generic raw logs). The adapter requires Ethereum mainnet chain 1, provider finalized-tag support and historical state.

It reads at most 20 finalized blocks, 1,000 scanned transactions, 100 relevant receipts and 1,000 logs; no silent truncation. Five-second HTTP timeout, no automatic retries, 30-second budget checked before/after each call. Receipt identity and final end hash are checked. Token decimals are compared and failed balance calls yield unavailable state and warnings.

RPC preview writes nothing. Review then save through the snapshot endpoint. Provider-reported finality is not independent consensus verification; a committed upload always has source_verified=false. No private-key or client-provided RPC URL field exists.

## Rules and AI

Rules explain failed receipts, high sender-paid fees (execution + blob), per-asset large transfers, newly observed outgoing recipients after ten earlier same-asset transfers, burst threshold crossings, outgoing concentration and native/token balance gaps. Only top-level ETH is observed; internal transfers need traces and are omitted.

Transfer-compatible token decoding requires a declared contract, three topics, padded addresses and 32-byte value. This does not certify token authenticity. NFT-shaped/other logs stay raw; generic contract logs may not involve the wallet.

Optional Isolation Forest requires 40 positive non-self transfers per asset: first 30 train, later events score. Features: log amount, log gap and outgoing flag. Assets never mix raw-unit baselines. Scores are review signals, not fraud probabilities. No LLM/paid AI is required.

## Verification and deployment

53 tests passed; Ruff passed; SQLite Alembic upgrade/downgrade/upgrade/check passed. Real HTTP demo passed: 90 transactions, 159 transfers, 71 logs, 12 alerts with shipped settings. RPC was tested with the actual Web3 client and simulated node responses. Live RPC, Docker and PostgreSQL were not executed. Two upstream deprecation warnings remain (Starlette/HTTPX and Web3/websockets).

```bash
cd backend
pytest -q
ruff check app tests migrations ../scripts
alembic check
```

Docker option: copy .env.example to .env, choose a URL-safe POSTGRES_PASSWORD, run docker compose up --build. API binds localhost:8091; PostgreSQL 17 uses a persistent volume. Configuration supplied, not verified here. Production needs HTTPS, COOKIE_SECURE=true, correct ALLOWED_ORIGINS, shared rate limits, body limits, backups, metrics and load tests. Authentication throttling is in-process. No scheduler, notifications or custom frontend is delivered.

## Documentation, cost and license

docs/CONCEPTION-AND-DEVELOPMENT.md and the separate PDF explain the product, architecture, calculations, coding modules, proposed dashboard and work-package plan. The dashboard and roadmap are proposals.

Application code is MIT; dependencies retain their own licenses. Offline libraries require no subscription. Optional RPC hosting, cloud operation and commercial data can cost money; check current provider plans. No paid account is needed for the demo.
