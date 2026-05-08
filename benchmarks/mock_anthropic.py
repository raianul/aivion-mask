"""Mock api.anthropic.com /v1/messages endpoint for benchmarks.

Returns a fixed canned response. SSE format mirrors the real Anthropic event
sequence enough for the proxy's parser to consume normally.
"""
from __future__ import annotations
import json
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# Allow the runner to choose which response shape to send via env var.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts import SHORT_RESPONSE_TEXT, LONG_RESPONSE_TEXT  # noqa: E402

app = FastAPI()


def _pick_text() -> str:
    return LONG_RESPONSE_TEXT if os.getenv("MOCK_RESPONSE", "short") == "long" else SHORT_RESPONSE_TEXT


def _json_response(text: str, model: str) -> dict:
    return {
        "id": "msg_bench_001",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 50, "output_tokens": 200},
    }


def _sse_event(name: str, payload: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode()


async def _sse_stream(text: str, model: str):
    yield _sse_event("message_start", {
        "type": "message_start",
        "message": {
            "id": "msg_bench_001", "type": "message", "role": "assistant",
            "model": model, "content": [], "stop_reason": None,
            "stop_sequence": None, "usage": {"input_tokens": 50, "output_tokens": 0},
        },
    })
    yield _sse_event("content_block_start", {
        "type": "content_block_start", "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    # Chunk the text into ~40-char pieces to simulate streaming.
    chunk_size = 40
    for i in range(0, len(text), chunk_size):
        yield _sse_event("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": text[i:i + chunk_size]},
        })
    yield _sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _sse_event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 200},
    })
    yield _sse_event("message_stop", {"type": "message_stop"})


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    text = _pick_text()
    model = body.get("model", "claude-haiku-4-5")
    if body.get("stream", False):
        return StreamingResponse(_sse_stream(text, model), media_type="text/event-stream")
    return JSONResponse(_json_response(text, model))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MOCK_PORT", "47475"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
