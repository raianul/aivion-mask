from __future__ import annotations
import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import httpx

from . import __version__
from .anthropic import UpstreamError, forward_complete_anthropic, forward_streaming_anthropic, walk_request
from .mcp import get_manifest
from aivion_mask_core.auth import get_or_create_token, verify_token
from aivion_mask_core.config import AIVION_DIR, load_config, Config
from aivion_mask_core.masker import register_custom_patterns
from aivion_mask_core.session import cleanup_expired, count_sessions, delete_session, init_db, list_sessions

PID_FILE = AIVION_DIR / "sidecar.pid"

_config: Config
_conn = None
_auth_token: str = ""

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _conn, _auth_token
    _pkg_log = logging.getLogger("aivion_mask_claude")
    _pkg_log.setLevel(logging.INFO)
    if not _pkg_log.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(levelname)s:  %(name)s - %(message)s"))
        _pkg_log.addHandler(_h)
    _config = load_config()
    _auth_token = get_or_create_token()
    register_custom_patterns(_config.sidecar.custom_patterns)
    _conn = await init_db()
    AIVION_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    PID_FILE.chmod(0o600)
    _pkg_log.info(
        "Dashboard: http://127.0.0.1:%d/?token=%s",
        _config.sidecar.port, _auth_token,
    )
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _conn.close()
        PID_FILE.unlink(missing_ok=True)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(600)
        await cleanup_expired(_conn)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_auth(request: Request) -> None:
    token = (
        request.headers.get("X-Aivion-Auth")
        or request.query_params.get("token")
    )
    if not verify_token(token, _auth_token):
        raise HTTPException(status_code=401, detail="Invalid or missing auth token")


@app.get("/", response_class=HTMLResponse)
async def dashboard(_: None = Depends(require_auth)):
    html = (Path(__file__).parent / "dashboard.html").read_text()
    return HTMLResponse(html)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/mcp")
def mcp():
    return get_manifest(_config.sidecar.port)


@app.get("/v1/sessions")
async def sessions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: None = Depends(require_auth),
):
    offset = (page - 1) * per_page
    rows = await list_sessions(_conn, offset, per_page)
    total = await count_sessions(_conn)
    return {"total": total, "page": page, "per_page": per_page, "sessions": rows}


@app.post("/v1/sessions/cleanup")
async def force_cleanup(_: None = Depends(require_auth)):
    deleted = await cleanup_expired(_conn)
    return {"deleted": deleted}


@app.delete("/v1/session/{session_id}")
async def clear_session(session_id: str, _: None = Depends(require_auth)):
    if not _UUID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="session_id must be a UUID")
    await delete_session(_conn, session_id)
    return {"deleted": session_id}


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()

    supplied_session = request.headers.get("X-Aivion-Session")
    if supplied_session:
        if not _UUID_RE.match(supplied_session):
            raise HTTPException(
                status_code=400,
                detail="X-Aivion-Session must be a UUID",
            )
        if not verify_token(request.headers.get("X-Aivion-Auth"), _auth_token):
            raise HTTPException(
                status_code=401,
                detail="X-Aivion-Session requires X-Aivion-Auth",
            )
        session_id = supplied_session
    else:
        session_id = str(uuid.uuid4())

    upstream_headers: dict[str, str] = {}
    skip = {"host", "content-length", "transfer-encoding", "x-aivion-session", "x-aivion-auth"}
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

    masked_body = await walk_request(body, _conn, session_id, ttl)
    if body.get("stream", False):
        return StreamingResponse(
            forward_streaming_anthropic(
                masked_body, upstream_headers, session_id, _conn,
                unmask_response=unmask, query_string=query_string,
            ),
            media_type="text/event-stream",
        )
    try:
        result = await forward_complete_anthropic(
            masked_body, upstream_headers, session_id, _conn,
            unmask_response=unmask, query_string=query_string,
        )
    except UpstreamError as exc:
        return JSONResponse(exc.payload, status_code=exc.status)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unreachable: {exc}") from exc
    return JSONResponse(result)


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = load_config()
    uvicorn.run(
        "aivion_mask_claude.main:app",
        host="127.0.0.1",
        port=cfg.sidecar.port,
        workers=1,
    )
