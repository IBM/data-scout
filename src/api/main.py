# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from .routes import router, ws_router
from .auth import verify_api_key, verify_api_key_ws
from src.storage import create_storage_backend
from src.config import SearchConfig
from fastapi.middleware.cors import CORSMiddleware
import logging

app = FastAPI(title="Data Scout API")

config = SearchConfig()
storage = create_storage_backend(config)

app.state.storage = storage
app.state.redis_url = config.redis_url
app.state.api_key = config.api_key

app.include_router(router, dependencies=[Depends(verify_api_key)])
app.include_router(ws_router, dependencies=[Depends(verify_api_key_ws)])


# Registered on the app rather than the authenticated router: a container
# healthcheck has no API key, and liveness should not depend on one. Reports
# whether this process can serve, not whether the pipeline is healthy -- redis
# and the worker report their own state.
@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# Added before CORSMiddleware so it sits *inside* it: Starlette's built-in
# server-error handling runs outside the CORS layer, so an unhandled exception
# returns a 500 with no Access-Control-Allow-Origin header. The browser then
# blocks the response and the UI reports a bare "Network error" instead of the
# real failure. Converting it to a normal JSONResponse here lets CORS annotate
# it on the way out.
@app.middleware("http")
async def surface_server_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logging.getLogger("pipeline_logger").exception("Unhandled API error")
        # The exception type and text can name absolute paths, a Redis URL with
        # credentials, or a raw S3 error body. The traceback is already in the log
        # above, so withhold it here unless DEBUG_ERRORS is set.
        detail = (
            f"{type(e).__name__}: {e}" if config.debug_errors
            else "Internal server error. The cause was written to the server log."
        )
        return JSONResponse(status_code=500, content={"detail": detail})


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
