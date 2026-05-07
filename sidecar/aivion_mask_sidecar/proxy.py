from __future__ import annotations
import json
import sqlite3
from typing import AsyncIterator

import httpx

from .session import get_all_mappings
from .stream import LookaheadBuffer
from .tokens import replace_tokens


async def forward_complete(
    request_body: dict,
    api_base: str,
    api_key: str,
    session_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Forward a non-streaming request; unscrub tokens in the response."""
    mappings = get_all_mappings(conn, session_id)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{api_base}/chat/completions", json=request_body, headers=headers
        )
        response.raise_for_status()
        data = response.json()
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        if isinstance(msg.get("content"), str):
            msg["content"] = replace_tokens(msg["content"], mappings)
    return data


async def forward_streaming(
    request_body: dict,
    api_base: str,
    api_key: str,
    session_id: str,
    conn: sqlite3.Connection,
) -> AsyncIterator[bytes]:
    """Forward a streaming request; unscrub tokens via lookahead buffer."""
    mappings = get_all_mappings(conn, session_id)
    buf = LookaheadBuffer(mappings)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{api_base}/chat/completions", json=request_body, headers=headers
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    yield (line + "\n").encode()
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    yield (line + "\n\n").encode()
                    continue
                try:
                    content = chunk["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError):
                    yield f"data: {json.dumps(chunk)}\n\n".encode()
                    continue
                safe = buf.push(content)
                chunk["choices"][0]["delta"]["content"] = safe
                yield f"data: {json.dumps(chunk)}\n\n".encode()

    remainder = buf.flush()
    if remainder:
        final = {"choices": [{"delta": {"content": remainder}, "index": 0}]}
        yield f"data: {json.dumps(final)}\n\n".encode()
    yield b"data: [DONE]\n\n"
