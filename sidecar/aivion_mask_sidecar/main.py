from __future__ import annotations
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import load_config, Config
from .masker import mask_message
from .mcp import get_manifest
from .proxy import forward_complete, forward_streaming
from .session import cleanup_expired, delete_session, init_db

_config: Config
_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _conn
    _config = load_config()
    _conn = init_db()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    _conn.close()


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(600)
        cleanup_expired(_conn)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # local-only service; all origins allowed
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/mcp")
def mcp():
    return get_manifest(_config.sidecar.port)


@app.delete("/v1/session/{session_id}")
def clear_session(session_id: str):
    delete_session(_conn, session_id)
    return {"deleted": session_id}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    session_id = (
        request.headers.get("X-Aivion-Session")
        or body.get("user")
        or str(uuid.uuid4())
    )

    if not _config.llm.api_key:
        raise HTTPException(
            status_code=400,
            detail="No LLM API key configured. Edit ~/.aivion-mask/config.toml",
        )

    # Mask each message content
    messages = body.get("messages", [])
    masked_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            content = mask_message(content, _conn, session_id, _config.sidecar.session_ttl_hours)
        masked_messages.append({**msg, "content": content})

    masked_body = {**body, "messages": masked_messages}
    masked_body.pop("user", None)  # don't leak session_id to upstream

    try:
        if body.get("stream", False):
            return StreamingResponse(
                forward_streaming(
                    masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn
                ),
                media_type="text/event-stream",
            )
        result = await forward_complete(
            masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream LLM unreachable: {exc}") from exc


def run() -> None:
    import uvicorn
    cfg = load_config()
    uvicorn.run("aivion_mask_sidecar.main:app", host="127.0.0.1", port=cfg.sidecar.port)
