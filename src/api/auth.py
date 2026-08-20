from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    expected_key = request.app.state.api_key
    if not expected_key:
        return
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
