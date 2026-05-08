from __future__ import annotations
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .anthropic import forward_complete_anthropic, forward_streaming_anthropic, walk_request
from .mcp import get_manifest
from aivion_mask_core.config import load_config, Config
from aivion_mask_core.masker import register_custom_patterns
from aivion_mask_core.session import cleanup_expired, delete_session, init_db

_config: Config
_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _conn
    _pkg_log = logging.getLogger("aivion_mask_claude")
    _pkg_log.setLevel(logging.INFO)
    if not _pkg_log.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(levelname)s:  %(name)s - %(message)s"))
        _pkg_log.addHandler(_h)
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
    return {"status": "ok", "version": "0.2.0"}


@app.get("/mcp")
def mcp():
    return get_manifest(_config.sidecar.port)


@app.delete("/v1/session/{session_id}")
async def clear_session(session_id: str):
    await delete_session(_conn, session_id)
    return {"deleted": session_id}


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

    query_string = request.url.query

    has_auth = any(k.lower() in ("authorization", "x-api-key") for k in upstream_headers)
    if not has_auth:
        raise HTTPException(
            status_code=401,
            detail="No auth provided. Send Authorization: Bearer <token> or x-api-key.",
        )

    ttl = _config.sidecar.session_ttl_hours
    unmask = _config.sidecar.unmask_response

    _log = logging.getLogger("aivion_mask_claude.main")
    _log.info("[REQUEST] session=%s model=%s stream=%s unmask=%s",
              session_id[:8], body.get("model", "?"), body.get("stream", False), unmask)

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
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = load_config()
    uvicorn.run(
        "aivion_mask_claude.main:app",
        host="127.0.0.1",
        port=cfg.sidecar.port,
        workers=2,
    )
