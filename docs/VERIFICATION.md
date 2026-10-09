# Verification - 7 October 2026 (Africa/Algiers)

- Python 3.12.14, Web3 7.16.0, scikit-learn 1.9.1.
- 53 pytest tests passed. Two upstream deprecation warnings: Starlette/HTTPX and Web3/websockets.legacy.
- Ruff check passed for app, tests, migrations and demo client.
- SQLite Alembic upgrade, downgrade base, upgrade and metadata check passed.
- Real localhost Uvicorn/HTTPX workflow passed, including seven exports and logout.
- Demo: 90 transactions, 159 transfers, 71 contract logs, 12 alerts under shipped settings.
- RPC: actual Web3 client with simulated JSON-RPC provider; no external provider request.
- Docker build, PostgreSQL integration, live RPC, concurrency/load testing not executed.
- Swagger delivered; custom dashboard, scheduler and notifications are proposed only.
