from __future__ import annotations

import os
from secrets import compare_digest

from fastapi import Header, HTTPException


TOKEN_ENV = "QUANTBENCH_API_TOKEN"
ORIGINS_ENV = "QUANTBENCH_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def allowed_origins() -> list[str]:
    raw = os.environ.get(ORIGINS_ENV)
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return list(DEFAULT_ALLOWED_ORIGINS)


def configured_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise HTTPException(status_code=500, detail=f"{TOKEN_ENV} is required before starting the API")
    return token


def require_api_token(x_quantbench_token: str | None = Header(default=None)) -> None:
    expected = configured_token()
    if not x_quantbench_token or not compare_digest(x_quantbench_token, expected):
        raise HTTPException(status_code=401, detail="missing or invalid QuantBench API token")
