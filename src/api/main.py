from fastapi import FastAPI, Depends
from .routes import router, ws_router
from .auth import verify_api_key, verify_api_key_ws
from src.storage import create_storage_backend
from src.config import SearchConfig
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Data Scout API")

config = SearchConfig()
storage = create_storage_backend(config)

app.state.storage = storage
app.state.redis_url = config.redis_url
app.state.api_key = config.api_key

app.include_router(router, dependencies=[Depends(verify_api_key)])
app.include_router(ws_router, dependencies=[Depends(verify_api_key_ws)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
