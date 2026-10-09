# Development

Use Python 3.12 and backend/requirements-dev.txt. Run pytest from backend and Ruff on app/tests/migrations/scripts. Preserve exact base-unit strings, owner constraints, provenance and event identities. Missing balances must never become zero. Add Alembic migrations for schema changes and verify upgrade/downgrade.

RPC changes require simulated Web3 tests and separately recorded live-provider checks. Never commit .env, databases, credentials, cookies or private keys. The proposed dashboard/scheduler are future work, not implemented features.
