# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import Depends, HTTPException, Request, Security, WebSocketException
from fastapi.security import APIKeyHeader
from starlette.requests import HTTPConnection

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    expected_key = request.app.state.api_key
    if not expected_key:
        return
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def verify_api_key_ws(connection: HTTPConnection):
    """API-key check for WebSocket routes.

    ``APIKeyHeader`` and ``Request`` are HTTP-only, so they cannot be used as
    dependencies on a WebSocket route. ``HTTPConnection`` is the common base of
    ``Request`` and ``WebSocket``, so the header is read from it directly.
    """
    expected_key = connection.app.state.api_key
    if not expected_key:
        return
    if connection.headers.get("X-API-Key") != expected_key:
        raise WebSocketException(code=1008)  # policy violation
