
## Blockchain Wallet
Monitoring API

FINANCE & CRYPTO SERIES / APPLICATION 04 / VERSION 1.0.0

Conception, application design, programming explanation and development plan. Prepared 7 October 2026 (Africa/Algiers).

Monitor public Ethereum mainnet wallets using reviewed snapshots. Keep balances and fees exact, retain transaction and contract-event evidence, and explain unusual activity using deterministic rules and optional local machine learning.

The source ZIP contains a runnable FastAPI backend, account authentication, migrations, tests, synthetic examples, an HTTP demo client, a Docker configuration and generated OpenAPI. This guide separates the delivered implementation from the proposed dashboard and recurring-monitoring roadmap.

Verified baseline: 53 tests passed and a real localhost HTTP workflow passed. Optional RPC behavior was tested through Web3 with simulated node responses. No external mainnet provider, Docker build or PostgreSQL runtime was tested.

| Scope | Status |
| --- | --- |
| Delivered | Offline JSON ingestion, wallet records, saved analyses, seven export formats |
| Optional | Server-configured read-only Ethereum RPC preview; local Isolation Forest |
| Proposed | Custom dashboard, scheduler, notifications, other chains and traces |

## 01 / Product conception

Target users include finance teams reviewing treasury wallets, e-commerce operators reconciling crypto receipts, analysts following public wallet activity, and developers integrating wallet observations into internal management applications.

The main question is: What changed in this wallet, which observed transactions explain it, and which events deserve human review? Each analysis belongs to a user, a wallet and one immutable snapshot. Public chain visibility does not replace access control over saved business records.

An operator registers a wallet, previews data quality, saves a reviewed snapshot, chooses per-asset thresholds and runs an analysis. The result contains balances, fees, transfers, raw contract logs, reconciliation calculations and explained alert evidence.

The first release deliberately uses Ethereum mainnet only. The wallet must be a syntactically valid address; registration is a watchlist action, not proof of ownership. It contains no fiat conversion, exchange trading, signing, private-key storage or NFT balance accounting.

A successful release must reject inconsistent block and event identities, preserve full integer amounts, prevent account-to-account record access, distinguish missing balance data from zero, and make every deterministic alert reproducible from the saved snapshot.

| Use case | Supported action |
| --- | --- |
| Treasury review | Compare opening/closing balances and sender-paid fees |
| Merchant receipts | Inspect token transfers and missing reconciliation evidence |
| Analyst monitoring | Review new recipients, large flows and unusual patterns |
| ERP integration | Download JSON/CSV or call authenticated HTTP routes |

## 02 / Application architecture

FastAPI exposes the account and monitoring routes. Pydantic validates requests before business logic runs. SQLAlchemy stores owner-scoped records; Alembic manages schema evolution. The calculation engine is pure snapshot processing, so an imported demo requires no blockchain connection.

JSON and optional RPC paths converge on the same normalized snapshot. RPC preview does not save records. The operator can review it and commit it through the standard upload route, which always labels the submitted snapshot as independently unverified.

Rules consume decoded transfers and raw receipts. Isolation Forest works on positive, non-self transfers for each asset separately. Saved results retain the engine version, input settings and library versions. CSV outputs come from those saved results rather than a fresh recalculation.

| Responsibility | Code |
| --- | --- |
| Input boundary | schemas.py, imports.py, rpc.py |
| Calculation boundary | events.py, engine.py, anomalies.py |
| Persistence boundary | models.py, database.py, services.py |
| HTTP boundary | main.py, security.py, routes.py |

## 03 / Languages, libraries and cost

Python 3.12 implements the backend and analytical engine. JSON is the request/report format, SQL is used through SQLAlchemy, CSV supplies tabular exports, YAML configures containers and CI, and Markdown documents the project. A future dashboard can use TypeScript and React; that frontend is not included.

The offline application uses local computation and needs no paid AI subscription. The optional algorithm is scikit-learn Isolation Forest, not a language model. Commercial RPC hosting, cloud servers, archival access, higher request quotas and optional external data services may introduce operating costs.

Direct runtime dependencies are version-pinned, with a compiled transitive requirements.lock.txt used for installation. Web3 7.16.0 is intentionally pinned; use the matching versioned documentation rather than assuming the current stable major version matches this project.

Application code is MIT. Each dependency retains its own license; evaluate those licenses and current hosting/provider terms for distribution. No current provider price is guaranteed by this guide.

| Library | Purpose |
| --- | --- |
| FastAPI 0.142.2 / Pydantic | HTTP routes, validation and OpenAPI |
| SQLAlchemy 2.1.3 / Alembic 1.20.0 | Database ORM and migrations |
| Web3 7.16.0 / Requests 2.34.2 | Read-only RPC, ABI calls and bounded HTTP transport |
| NumPy 2.5.3 / scikit-learn 1.9.1 | Per-asset numerical features and Isolation Forest |
| Argon2-cffi 25.1.0 | Password hashing |
| HTTPX 0.28.1 / pytest 9.1.1 | Demo HTTP client and automated tests |

## 04 / Data model and ownership

User owns Wallet, and Wallet owns Snapshot and Analysis. LoginSession stores a digest of the opaque cookie token, a CSRF token and expiry. RequestRecord binds a mutation key to the owner, operation scope, request fingerprint and original response.

Wallet identity is unique per user, chain and address. Snapshots store normalized payload, quality metadata and a fingerprint unique within the wallet. Analyses retain inputs and JSON results, linked to the exact wallet and snapshot used for the calculation.

Snapshot identity contains the full block range and end hash. Reports remain associated with those observations; an analysis is not silently updated when another snapshot is uploaded. A duplicate normalized snapshot returns the existing record.

All record lookups constrain the current user. Unknown or another account's wallet/analysis returns 404. Wallet visibility on the public chain does not expose saved labels, analysis parameters or account history through this API.

SQLite is the verified local database. The supplied PostgreSQL configuration is a deployment starting point requiring integration and load testing. The JSON schema is convenient for an MVP; high-volume production should add indexing, pagination and retention controls.

| Entity | Stored responsibilities |
| --- | --- |
| User / LoginSession | Identity, password hash, session digest, CSRF, expiry |
| Wallet | user_id, label, address, chain_id |
| Snapshot | wallet_id, payload, quality, fingerprint, created_at |
| Analysis | wallet_id, snapshot_id, inputs, results, engine_version |
| RequestRecord | user_id, scope, key, request hash, saved response |

## 05 / Exact amounts and validation

All money values enter and leave the API as base-unit decimal strings. A uint256 may be much larger than JavaScript's safe integer range, so JSON numbers and floating-point arithmetic are unsuitable for balances. Python int preserves the entire value.

ETH uses 18 decimal places. For a token, its declared decimals determine the display value. The asset identifier is native for ETH or the token contract address; matching symbols do not imply matching assets. The engine never sums token base units with ETH base units.

Validation accepts ASCII integer strings of at most 78 digits strictly below 2^256 and normalizes leading zeros. Addresses use 0x plus 40 hex digits; mixed-case input must satisfy EIP-55 checksum. Addresses are normalized to lowercase. Chain ID is exactly integer 1, with booleans rejected.

Block numbers and timestamps are strict bounded integers; future timestamps are rejected. Hashes are lowercase 32-byte hex values. Hex event data must have even length. Item ceilings constrain uploaded blocks, transactions, contracts and logs; add proxy byte and rate limits for production.

The formatting helper uses quotient/remainder arithmetic and trims fractional trailing zeros. It returns strings and does not round an exact balance.


```python
amount = int("1234567890123456789")
whole, fraction = divmod(amount, 10 ** 18)
# Exact display: 1.234567890123456789 ETH
# UINT256 maximum stays an integer string in JSON.
# Missing closing token balance stays null, not "0".
```

## 06 / Snapshot conception and ingestion

A snapshot supplies chain_id, wallet_address, source, a block list, opening/closing native balances, watched contract declarations, top-level transactions and raw logs. examples/snapshot.json is a complete synthetic request, while docs/openapi.json is the authoritative field contract.

Each block carries number, hash, parent_hash and timestamp. Normalization sorts by number, requires a contiguous sequence, verifies parent links and strictly increasing timestamps, and rejects duplicate block numbers and hashes.

Transaction and log block references must match supplied headers. A top-level transaction must involve the monitored wallet. Contracts must be distinct and every log must refer to a watched contract. Duplicate transaction hashes, transaction positions and block-wide log positions are rejected.

Logs attached to supplied wallet transactions must match block and transaction indexes and a successful receipt. Logs belonging to other transactions may still be retained because a watched contract can emit events unrelated to the wallet. This is useful context, not proof of wallet involvement.

POST /imports/preview accepts a JSON string, validates and normalizes without a database write. Saving checks the wallet identity again and fingerprints the normalized payload. The quality record always distinguishes user-supplied data from independently authenticated evidence.

| Control | Implemented behavior |
| --- | --- |
| Upload bounds | 1,000 blocks; 5,000 transactions; 10,000 logs; 5 contracts |
| JSON preview | At most 6 million characters |
| Identity checks | Parent chain, hash references, transaction/log positions |
| Provenance | source_verified false on committed uploads |

## 07 / Native transactions and fees

Top-level transactions retain sender, optional recipient, value in wei, receipt status, gas used, effective gas price and optional blob gas fields. Status 1 with positive value produces an observed native transfer. Status 0 retains its receipt but does not count the attempted value as a successful transfer.

The monitored wallet pays a recorded transaction fee only when it is the sender. A wallet receiving ETH does not pay the sender's fee. A self-transfer is visible but has zero native principal net change; its sender fee still reduces the balance.

Execution fee equals gas_used multiplied by effective_gas_price_wei. Blob transactions additionally pay blob_gas_used multiplied by blob_gas_price_wei. The engine adds both integer components. RPC receipts for blob transactions must include the blob fee evidence.

Example: 21,000 gas at 10 gwei costs 210,000,000,000,000 wei, exactly 0.00021 ETH. A failed outgoing transaction can still incur that fee. Incoming transactions, failed attempts and self-transfers therefore need distinct handling.

Standard block and receipt methods do not reveal internal ETH movements produced by contract execution. Reconciliation gaps can indicate such omitted movements or incomplete data; they must not be labeled theft.

| Case | Native balance contribution |
| --- | --- |
| Successful outgoing | Subtract value and sender fee |
| Successful incoming | Add value; wallet sender fee is zero |
| Self-transfer | Principal net zero; subtract sender fee |
| Failed outgoing | Do not subtract attempted value; subtract fee |

## 08 / Token decoding and raw events

Every watched-contract log is retained as evidence: contract address, topics, data, block number/hash, transaction hash/index and log index. Generic contract logs remain useful without an ABI or event interpretation.

A declared token contract enables Transfer-compatible decoding. The decoder requires the Transfer(address,address,uint256) signature, exactly three topics, properly zero-padded indexed addresses and a 32-byte data value. It then derives the exact integer amount and direction relative to the monitored wallet.

The compatible shape is not a certification that the contract is ERC-20 or that a transfer changed balances as expected. Rebasing tokens, incomplete logs and nonstandard contract mechanics can cause discrepancies. Decimals are a display declaration in uploaded snapshots.

NFT Transfer events typically have four topics and do not enter the fungible-token flow ledger here. Malformed or differently shaped events remain raw. Zero-value token transfers are retained as activity, though the anomaly model excludes nonpositive amounts.

A generic watched-contract event may be unrelated to the wallet. UI and ERP consumers should show wallet relevance as unknown when it is not decoded. Do not aggregate every contract log into wallet inflow/outflow.

| Input | Result |
| --- | --- |
| Decoded token event | Declared decimals + compatible signature/topics/data + wallet involved |
| NFT-shaped event | Raw event only; no NFT balance accounting |
| Generic contract event | Raw event; wallet relevance can be unknown |
| Asset label | Display metadata; contract address remains identity |

## 09 / Balance reconciliation

For ETH, expected closing balance equals opening plus observed successful incoming value minus outgoing value minus sender-paid fees. Self principal cancels. Gap equals declared closing minus expected closing. All arithmetic is performed with integers in wei.

If opening native balance is unavailable, the engine reports unavailable reconciliation rather than inventing a zero. A match means the supplied top-level flow evidence explains the supplied balances; it does not prove there were no omitted offsetting internal movements.

Token reconciliation is independent for each declared token: expected closing equals opening plus decoded inflows minus decoded outflows. Native network fees are not subtracted from token balances. Missing opening or closing token state makes reconciliation unavailable.

Reconciliation alerts include the exact gap and asset identifier. Differences can arise from incomplete data, internal transfers, rebases, token mechanics or incorrect declarations. A gap is a review prompt with bounded evidence.

These calculations support finance review, but they do not assign fiat cost basis, recognize accounting revenue or estimate tax liability. ERP integrations should preserve chain block identity and unit metadata when importing balances.


```python
expected_wei = opening_wei + in_wei - out_wei - fees_wei
gap_wei = closing_wei - expected_wei
# Token: expected = opening + token_in - token_out
# Missing state: reconciliation.status = unavailable
# Demo native status: matches_observed_top_level_flows
```

## 10 / Explained rule engine

Rules emit a code, explanation and evidence tied to a transaction, event or asset calculation. Large-transfer thresholds are configured per asset in base units; no universal cross-token monetary threshold is invented.

A newly observed outgoing recipient requires at least ten earlier positive outgoing transfers for the same asset in this snapshot. “New” is relative to this bounded history, not the wallet's lifetime. Concentration divides the largest recipient's outgoing amount by total outgoing amount for the same asset.

Burst detection counts observed transfers in the trailing interval (now - window, now], including zero-value and self events. An alert marks crossing the configured count; another crossing can occur after the rolling count drops. This is transfer-event frequency, not raw blockchain transaction frequency.

The engine keeps deterministic rules available when AI is disabled or history is too short. Evidence explains why the threshold fired and preserves the relevant asset units. Model alerts are reported separately.

| Rule | Meaning |
| --- | --- |
| FAILED_TRANSACTION | Receipt status 0 |
| HIGH_TRANSACTION_FEE | Sender-paid execution + blob fee >= threshold |
| LARGE_TRANSFER | Configured asset threshold reached |
| NEW_OUTGOING_RECIPIENT | First observed recipient after earlier same-asset history |
| ACTIVITY_BURST | Trailing transfer count crosses threshold |
| OUTGOING_CONCENTRATION | Largest recipient share reaches fraction |
| NATIVE / TOKEN_BALANCE_GAP | Available reconciliation has nonzero gap |
| UNUSUAL_TRANSFER_PATTERN | Later same-asset score below fitted model offset |

## 11 / Optional AI conception

Isolation Forest estimates how unusual a transfer is compared with an earlier same-asset baseline. It requires no labeled fraud examples and no external AI API. It is useful for prioritizing review, but it cannot verify identity, malicious intent or transaction legitimacy.

Events are grouped by asset and kept in canonical block/transaction/log order. Only positive, non-self transfers enter the model. At least 40 such events per asset are needed: the first 30 train the baseline, and at least ten later events are scored. Another asset's history cannot satisfy that minimum.

Features are log1p of base-unit amount, log1p of the time gap since the previous same-asset transfer, and an outgoing indicator. The first gap is zero. Integer accounting remains exact; floating-point features are used only for statistical scoring.

Parameters are fixed: 100 trees, contamination 0.1, seed 42 and one worker. The training prefix stays fixed as later events are scored; there is no training on future observations. The fitted offset determines the flag, not a confidence percentage.

The result reports training event IDs, training end, scoring start, model offset and individual scores. Status is disabled, insufficient_history or available. A future production model needs baseline governance, labeled evaluations, drift monitoring and operator feedback.


```python
model = IsolationForest(
    n_estimators=100, contamination=0.1,
    random_state=42, n_jobs=1,
).fit(features[:30])
scores = model.score_samples(features[30:])
flagged = score < model.offset_
```

## 12 / Optional live RPC adapter

The RPC endpoint is configured on the server, not supplied by an API caller. Only HTTP(S) URLs are accepted. The Requests session disables inherited proxy settings, and Web3 automatic retries are disabled so transport work stays bounded.

The adapter checks chain_id equals 1 and reads the provider's finalized block. It scans up to 20 blocks ending there, fetches wallet-related receipts, retrieves native historical balances and optionally reads watched-token decimals and balanceOf at the range boundaries.

Each relevant receipt must match its transaction hash, block hash, block number and transaction index. Logs must be consistent with the watched contracts and range; removed logs are rejected. The final block hash is reread after collection and a changed hash aborts the preview.

RPC limits are 1,000 scanned transactions, 100 relevant receipts and 1,000 logs. Exceeding a bound fails explicitly. Individual HTTP requests time out at five seconds; a 30-second budget is checked before and after each call, so wall time may exceed it by an in-flight call and processing overhead.

A failed opening balance read yields missing data and a warning. Failed token metadata/closing reads yield unavailable token state and sanitized warnings. Provider exceptions do not expose the configured secret-bearing URL. The optional adapter has simulated-client tests, not live-provider certification.

| Aspect | Contract |
| --- | --- |
| Read evidence | Provider-reported finalized head plus end-hash recheck |
| Commit provenance | Uploaded snapshot remains independently unverified |
| Provider requirements | Mainnet chain 1; finalized tag; historical state access |
| Unavailable features | Internal traces, signing, sendTransaction, background polling |

## 13 / API integration and replay

The client registers or logs in, retains the session cookie and sends X-CSRF-Token for authenticated POST requests. The server verifies trusted Origin values when present. Password input is not echoed in validation errors.

Create operations require Idempotency-Key. The same user, scope, key and payload returns the originally committed response. Reusing that key with another payload returns 409. Business data and the request record are committed in the same transaction.

JSON/RPC previews are read operations and do not require a mutation replay key. Snapshot commit checks that the submitted address and chain match the account-owned wallet. Analysis inputs must reference a snapshot belonging to that wallet.

Swagger at /docs and generated docs/openapi.json describe full schemas. The demo client exercises seven report formats: one JSON report and six CSV tables. CSV export neutralizes formula-style untrusted text while retaining exact numeric strings.

Cookies and CSRF tokens support a same-origin application. A cross-origin SPA, service-to-service credentials or public API subscription layer would need a separately designed authentication policy.

| Route (monitoring prefix /api/v1) | Purpose |
| --- | --- |
| POST /api/auth/register, /login | Credentials; response includes csrf_token |
| GET/POST /api/v1/wallets | List or register watched wallet |
| POST /api/v1/imports/preview | Validate snapshot_json string |
| GET/POST /wallets/{id}/snapshots | List or save normalized snapshot |
| POST /wallets/{id}/rpc-preview | Optional bounded provider read |
| POST /wallets/{id}/analyses | Calculate and save report |
| GET /analyses/{id}/report | JSON or selected CSV format |

## 14 / Application design proposal

The delivered user interface is Swagger. The following dashboard is a proposed implementation for the next phase, not a supplied frontend. It can be built in TypeScript/React using the existing HTTP contracts.

Navigation: Wallets, Data preview, Analysis, Alerts and Exports. A wallet page shows its address, chain, source label, exact closing block/hash and provenance badge. Display ETH and tokens separately, with unavailable state visibly distinct from zero.

The analysis page uses four summary cards: observed block range, sender-paid ETH fees, decoded transfer count and alert count. Below them, balances and reconciliation appear per asset. The transfer table filters by asset, direction and block range.

An alert detail panel shows rule code, plain explanation, threshold, exact measured value and linked transaction/log identity. Model panels show baseline window and score/offset without a fabricated risk percentage. Raw-event rows retain topics and data for technical review.

Preview requires a visible data-quality summary before Save snapshot. RPC timeout/error states offer retry without pretending partial collection is complete. Re-running an analysis creates a distinct saved report with its own settings.

Use a restrained navy/teal palette, readable tables and badges labeled observed, declared, unavailable and unverified upload. Color supports the text labels; it must not carry meaning alone.

| Region | Proposed content |
| --- | --- |
| Header | Wallet label | Ethereum 1 | end block/hash | provenance |
| Summary cards | Range | ETH fees | transfer count | alerts |
| Main table | Asset | exact units | direction | tx/log identity |
| Review panel | Explanation | threshold | evidence | baseline status |
| Actions | Preview | Save snapshot | Run analysis | Export |

## Design / Dashboard wireframe

Proposed layout for a future custom frontend. This wireframe shows regions and labels, not live balances or a delivered screen. The current runnable interface is Swagger.

Selecting an asset filters its balance and flow ledger. Selecting an alert opens its evidence panel. Show exact base units alongside formatted display values, and always retain block identity and source provenance.

| Interaction state | Design behavior |
| --- | --- |
| Empty wallet | Offer JSON preview or optional RPC preview |
| Missing state | Display unavailable; disable reconciliation claim |
| Error state | Show sanitized failure; do not silently save partial data |
| Model short history | Show insufficient_history; keep rule results visible |

## 15 / Demo results and acceptance

The offline dataset has 90 contiguous synthetic blocks and 90 wallet-related transactions, with one failed receipt, a high-fee transaction, a large native transfer, a large token transfer and a newly observed recipient. One declared six-decimal token and an extra raw contract event exercise both decoding paths.

The real HTTP client completed registration, demo creation, JSON preview, normalized-snapshot deduplication, saved analysis, seven exports, OpenAPI retrieval, Swagger access and logout. The synthetic dataset is not real mainnet evidence.

With the shipped client settings, results contain 90 transactions, 159 decoded transfers, 71 raw contract logs and 12 explained alerts. Large thresholds are 0.2 ETH and 100 token units; burst settings are 15 events over 120 seconds. Counts depend on these saved inputs.

Native reconciliation matches the observed top-level flows and the model status is available. The bar chart compares counts only; it does not combine ETH and token amounts or imply monetary portfolio value.

| Alert code in shipped demo | Count |
| --- | --- |
| ACTIVITY_BURST | 1 |
| FAILED_TRANSACTION | 1 |
| HIGH_TRANSACTION_FEE | 1 |
| LARGE_TRANSFER | 2 |
| NEW_OUTGOING_RECIPIENT | 2 |
| OUTGOING_CONCENTRATION | 1 |
| UNUSUAL_TRANSFER_PATTERN | 4 |

## 16 / Programming module map

Start with schemas and normalization: every later calculation assumes validated identities and exact amounts. Then understand the event decoder, followed by accounting/rules and the optional model. HTTP routes should orchestrate these modules rather than duplicate calculations.

The dependency boundaries make auditing practical. A failed transfer must be excluded from native value but not sender fees; a malformed token event must remain raw; unavailable token balances must stay null. The tests enforce these differences.

Configuration is read from environment variables at startup. DATABASE_URL defaults to local SQLite; ETHEREUM_RPC_URL defaults empty, which makes RPC preview return 503 until explicitly configured. The offline path remains available.

| File | Coding responsibility |
| --- | --- |
| schemas.py | Strict request contracts, address checks, uint256 strings |
| imports.py | Canonical order, parent/hash/identity checks, quality metadata |
| events.py | Exact formatting, receipt fees, native/token decoding |
| engine.py | Flow totals, reconciliation, explained deterministic rules |
| anomalies.py | Earlier per-asset baseline and later scores |
| rpc.py | Bounded Web3 reads, receipt matching, finality checks |
| models.py / services.py | Storage model and atomic idempotent mutations |
| main.py / security.py / routes.py | Authentication, authorization, validation and HTTP |
| scripts/demo_client.py | Working HTTP integration and export example |

## 17 / Verification and remaining checks

53 automated tests passed under Python 3.12.14. The suite covers exact uint256 formatting, fees including blob components, failed/incoming/self transactions, token/NFT event shape, reconciliation missing-state behavior, per-asset ML history and future-prefix separation.

Identity tests cover duplicate blocks, discontinuous ranges, incorrect block references, receipt/log position mismatches, removed logs and unauthorized record access. HTTP tests cover CSRF, session expiry/logout, mutation replay conflicts, failed mutation rollback and deduplicated snapshots.

Nine RPC tests instantiate the actual Web3 client against a simulated JSON-RPC provider. They verify supported method formatting/ABI calls, chain rejection, final-hash changes, receipt mismatches, bounds, removed logs, token-call failures and sanitized errors. This does not verify a live provider's behavior.

Ruff lint passed. Alembic SQLite upgrade, downgrade to base, upgrade again and metadata check passed. A real localhost server passed the integration demo. Docker was unavailable, and PostgreSQL/live external RPC checks remain open.

Two upstream deprecation warnings occurred: Starlette's HTTPX TestClient integration and Web3's websockets.legacy dependency. They did not fail the suite; dependency upgrades require compatibility verification.

Before production, test a provider with historical state, finalize-tag support and type-3 receipts; run Docker/PostgreSQL migrations; check concurrent retries, proxy limits, backups, deployment security and realistic throughput.

| Evidence category | Status |
| --- | --- |
| Verified | 53 tests, actual localhost HTTP, SQLite migrations, Ruff |
| Simulated | Web3 read-only RPC integration and failure cases |
| Not executed | Live RPC, Docker, PostgreSQL, sustained load |
| Not implemented | Scheduler, dashboard, notifications, traces, multi-chain |

## 18 / Local setup and operations

From the extracted project root, create a Python 3.12 virtual environment, install backend/requirements-dev.txt, enter backend, migrate and start Uvicorn. Run the demo client from another activated terminal at the project root. It writes new synthetic example outputs and uses a random temporary account.

For container deployment, copy .env.example to .env and choose a URL-safe PostgreSQL password because it is embedded in DATABASE_URL. docker compose up --build supplies PostgreSQL 17 and binds the API to localhost:8091. This configuration was not executed in the verification environment.

Production needs HTTPS with COOKIE_SECURE=true, correct allowed origins, shared throttling, request-body limits, secret management, retention, database backups and health/latency metrics. The included auth throttle is in-memory per process and resets on restart.

RPC credentials belong only in server environment or a secret store. Do not put them in snapshots, examples or repository history. Monitor provider request quotas; synchronous bounded previews can still consume worker capacity under concurrency.


```python
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8011
# Another activated terminal, project root:
python scripts/demo_client.py
# Tests, from backend:
pytest -q
ruff check app tests migrations ../scripts
```

## 19 / Planning for each module

The following estimates describe a staged production-development effort for one experienced backend developer with part-time frontend/QA support. The supplied MVP already implements the core baseline, but estimates include requirements review and hardening rather than claiming the work is deployment-ready.

Complete exact accounting and input integrity before designing recurring monitoring. Establish source/finality evidence and migration checks before expanding chain support. Give UI users explicit missing-data and provenance states before adding model-driven ranking.

Total indicative effort is 31-48 working days. Work can overlap after contracts stabilize; discovery, provider limitations and compliance requirements can extend the calendar. No paid infrastructure budget is estimated without deployment/provider choices.

| Work package | Estimate | Exit criterion |
| --- | --- | --- |
| Requirements / data contracts | 2-3 days | Acceptance examples; supported assets and unit policy |
| Authentication / ownership | 3-4 days | Sessions, shared throttling, tenant-access review |
| Ingestion / exact accounting | 5-7 days | Identity validation, ERC events, fee/gap fixtures |
| RPC integration | 4-6 days | Live provider tests, finality, quotas, historical state |
| Rules / analytical AI | 4-6 days | Threshold governance, labeled review, drift checks |
| Dashboard / ERP client | 5-8 days | Preview, asset tables, alert evidence, exports |
| QA / Docker / deployment | 5-8 days | PostgreSQL, concurrency, backup/restore, load tests |
| Operations / documentation | 3-6 days | Runbooks, metrics, rollback and onboarding |

## 20 / Roadmap and source references

Phase 1: deploy the verified offline workflow to a staging environment and execute the outstanding Docker/PostgreSQL/live-RPC checks. Phase 2: build the proposed dashboard and obtain operator feedback on reconciliation and alerts. Phase 3: add an audited scheduler, explicit cursor/reorg handling and notification delivery.

Later extensions can include chain-specific adapters, internal-transfer tracing, token metadata verification, fiat valuation and ERP webhooks. Each changes the evidence/accounting contract and requires its own tests. Chain IDs, finality, decimals and fee models must not be assumed identical across networks.

Consult the following primary documentation for library/API behavior. Provider-reported finalized blocks are a provenance statement, not an independent guarantee supplied by this application. Commercial terms and current prices should be checked directly when choosing infrastructure.

| Reference | Location |
| --- | --- |
| Ethereum JSON-RPC | https://ethereum.org/developers/docs/apis/json-rpc/ |
| ERC-20 specification | https://eips.ethereum.org/EIPS/eip-20 |
| Blob transactions / fees | https://eips.ethereum.org/EIPS/eip-4844 |
| Web3 7.16 providers | https://web3py.readthedocs.io/en/v7.16.0/providers.html |
| Isolation Forest reference | https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html |
| Project API contract | docs/openapi.json in the source ZIP |
| Reproducible integration | scripts/demo_client.py and examples/ in the source ZIP |