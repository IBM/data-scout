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
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(e).__name__}: {e}"},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
