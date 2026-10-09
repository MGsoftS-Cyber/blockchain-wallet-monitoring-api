"""Environment configuration. Local development deliberately needs no cloud service."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wallet.db")
ALLOWED_ORIGINS = {
    value.strip()
    for value in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8091,http://127.0.0.1:8091,http://localhost:8011,http://127.0.0.1:8011",
    ).split(",")
    if value.strip()
}
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_SECONDS = 60 * 60 * 24 * 7

ETHEREUM_RPC_URL = os.getenv("ETHEREUM_RPC_URL", "")
