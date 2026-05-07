from __future__ import annotations
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .anthropic import forward_complete_anthropic, forward_streaming_anthropic, walk_request
from .config import load_config, Config
from .masker import mask_message, register_custom_patterns
from .mcp import get_manifest
from .proxy import forward_complete, forward_streaming
from .session import cleanup_expired, delete_session, init_db

_config: Config
_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _conn
    _config = load_config()
    register_custom_patterns(_config.sidecar.custom_patterns)
    _conn = await init_db()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    await _conn.close()


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(600)
        await cleanup_expired(_conn)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://.*|moz-extension://.*",
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
async def clear_session(session_id: str):
    await delete_session(_conn, session_id)
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

    messages = body.get("messages", [])
    masked_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            content = await mask_message(content, _conn, session_id, _config.sidecar.session_ttl_hours)
        masked_messages.append({**msg, "content": content})

    masked_body = {**body, "messages": masked_messages}
    masked_body.pop("user", None)

    try:
        unmask = _config.sidecar.unmask_response
        if body.get("stream", False):
            return StreamingResponse(
                forward_streaming(
                    masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn,
                    unmask_response=unmask,
                ),
                media_type="text/event-stream",
            )
        result = await forward_complete(
            masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn,
            unmask_response=unmask,
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream LLM unreachable: {exc}") from exc


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    session_id = (
        request.headers.get("X-Aivion-Session")
        or str(uuid.uuid4())
    )

    upstream_headers: dict[str, str] = {}
    skip = {"host", "content-length", "transfer-encoding", "x-aivion-session"}
    for name, value in request.headers.items():
        if name.lower() in skip:
            continue
        upstream_headers[name] = value
    upstream_headers["Content-Type"] = "application/json"

    # Preserve upstream query string (e.g. ?beta=true from Claude Code)
    query_string = request.url.query  # e.g. "beta=true" or ""

    has_auth = any(k.lower() in ("authorization", "x-api-key") for k in upstream_headers)
    if not has_auth:
        raise HTTPException(
            status_code=401,
            detail="No auth provided. Send Authorization: Bearer <token> or x-api-key.",
        )

    ttl = _config.sidecar.session_ttl_hours
    unmask = _config.sidecar.unmask_response

    try:
        masked_body = await walk_request(body, _conn, session_id, ttl)
        if body.get("stream", False):
            return StreamingResponse(
                forward_streaming_anthropic(
                    masked_body, upstream_headers, session_id, _conn,
                    unmask_response=unmask, query_string=query_string,
                ),
                media_type="text/event-stream",
            )
        result = await forward_complete_anthropic(
            masked_body, upstream_headers, session_id, _conn,
            unmask_response=unmask, query_string=query_string,
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream LLM unreachable: {exc}") from exc


def run() -> None:
    import logging
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = load_config()
    uvicorn.run(
        "aivion_mask_sidecar.main:app",
        host="127.0.0.1",
        port=cfg.sidecar.port,
        workers=2,
    )
