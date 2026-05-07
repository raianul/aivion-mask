from __future__ import annotations
import json
import logging
from typing import AsyncIterator

import httpx

from .masker import mask_message
from .session import get_all_mappings
from .stream import LookaheadBuffer
from .tokens import replace_tokens

_log = logging.getLogger(__name__)

ANTHROPIC_UPSTREAM = "https://api.anthropic.com"


async def _walk_json_async(obj, conn, session_id: str, ttl_hours: int):
    """Recursively mask string leaves in a JSON-like object."""
    if isinstance(obj, str):
        return await mask_message(obj, conn, session_id, ttl_hours)
    if isinstance(obj, dict):
        return {k: await _walk_json_async(v, conn, session_id, ttl_hours) for k, v in obj.items()}
    if isinstance(obj, list):
        return [await _walk_json_async(v, conn, session_id, ttl_hours) for v in obj]
    return obj


def _walk_json_sync(obj, mappings: dict[str, str]):
    """Recursively replace token placeholders in string leaves of a JSON-like object."""
    if isinstance(obj, str):
        return replace_tokens(obj, mappings)
    if isinstance(obj, dict):
        return {k: _walk_json_sync(v, mappings) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_json_sync(v, mappings) for v in obj]
    return obj


async def _mask_content(content, conn, session_id: str, ttl_hours: int):
    """Mask an Anthropic content field — handles string, block array, or passthrough."""
    if isinstance(content, str):
        return await mask_message(content, conn, session_id, ttl_hours)
    if isinstance(content, list):
        result = []
        for block in content:
            block = dict(block)
            btype = block.get("type")
            if btype == "text" and isinstance(block.get("text"), str):
                block["text"] = await mask_message(block["text"], conn, session_id, ttl_hours)
            elif btype == "tool_result":
                block["content"] = await _mask_content(block.get("content", ""), conn, session_id, ttl_hours)
            elif btype == "tool_use" and isinstance(block.get("input"), dict):
                block["input"] = await _walk_json_async(block["input"], conn, session_id, ttl_hours)
            result.append(block)
        return result
    return content


async def walk_request(body: dict, conn, session_id: str, ttl_hours: int) -> dict:
    """Return a copy of an Anthropic /v1/messages request body with all user text masked."""
    result = dict(body)
    if "system" in result:
        result["system"] = await _mask_content(result["system"], conn, session_id, ttl_hours)
    if "messages" in result:
        masked = []
        for msg in result["messages"]:
            msg = dict(msg)
            msg["content"] = await _mask_content(msg.get("content", ""), conn, session_id, ttl_hours)
            masked.append(msg)
        result["messages"] = masked
    return result


def walk_response(body: dict, mappings: dict[str, str]) -> dict:
    """Return a copy of an Anthropic response body with all token placeholders restored."""
    result = dict(body)
    unmasked = []
    for block in result.get("content", []):
        block = dict(block)
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = replace_tokens(block["text"], mappings)
        elif block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            block["input"] = _walk_json_sync(block["input"], mappings)
        unmasked.append(block)
    result["content"] = unmasked
    return result


async def _parse_anthropic_sse(response: httpx.Response):
    """Yield (event_name, json_payload) pairs from an Anthropic SSE stream."""
    pending_event = None
    async for line in response.aiter_lines():
        if line.startswith("event: "):
            pending_event = line[7:].strip()
        elif line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                _log.warning("Unparseable SSE data line: %r", line[:80])
                continue
            yield pending_event, payload
            pending_event = None
        # blank lines are SSE event boundaries — skip


async def forward_complete_anthropic(
    body: dict,
    upstream_headers: dict,
    session_id: str,
    conn,
    unmask_response: bool = True,
) -> dict:
    """Forward a non-streaming Anthropic /v1/messages request; optionally unmask the response."""
    mappings = await get_all_mappings(conn, session_id) if unmask_response else {}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{ANTHROPIC_UPSTREAM}/v1/messages",
            json=body,
            headers=upstream_headers,
        )
        response.raise_for_status()
        data = response.json()
    if unmask_response:
        data = walk_response(data, mappings)
    return data


async def forward_streaming_anthropic(
    body: dict,
    upstream_headers: dict,
    session_id: str,
    conn,
    unmask_response: bool = True,
) -> AsyncIterator[bytes]:
    """Forward a streaming Anthropic /v1/messages request; unmask text as it arrives."""
    mappings = await get_all_mappings(conn, session_id) if unmask_response else {}

    # Per-block state (keyed by content block index)
    text_bufs: dict[int, LookaheadBuffer] = {}
    json_accum: dict[int, str] = {}
    block_types: dict[int, str] = {}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{ANTHROPIC_UPSTREAM}/v1/messages", json=body, headers=upstream_headers
        ) as response:
            async for event_name, payload in _parse_anthropic_sse(response):
                ename = event_name or "data"

                if ename == "content_block_start":
                    idx = payload["index"]
                    btype = payload["content_block"]["type"]
                    block_types[idx] = btype
                    if btype == "text":
                        text_bufs[idx] = LookaheadBuffer(mappings)
                    elif btype == "tool_use":
                        json_accum[idx] = ""
                    yield f"event: {ename}\ndata: {json.dumps(payload)}\n\n".encode()

                elif ename == "content_block_delta":
                    idx = payload["index"]
                    delta = payload["delta"]
                    dtype = delta.get("type")

                    if dtype == "text_delta":
                        buf = text_bufs.get(idx)
                        if buf and unmask_response:
                            safe = buf.push(delta.get("text", ""))
                            payload = {**payload, "delta": {**delta, "text": safe}}
                        yield f"event: {ename}\ndata: {json.dumps(payload)}\n\n".encode()

                    elif dtype == "input_json_delta":
                        # Accumulate — emit as one reconstructed delta on content_block_stop
                        json_accum[idx] = json_accum.get(idx, "") + delta.get("partial_json", "")

                    else:
                        yield f"event: {ename}\ndata: {json.dumps(payload)}\n\n".encode()

                elif ename == "content_block_stop":
                    idx = payload["index"]
                    btype = block_types.get(idx)

                    if btype == "text":
                        buf = text_bufs.pop(idx, None)
                        if buf and unmask_response:
                            remainder = buf.flush()
                            if remainder:
                                flush_payload = {
                                    "type": "content_block_delta",
                                    "index": idx,
                                    "delta": {"type": "text_delta", "text": remainder},
                                }
                                yield f"event: content_block_delta\ndata: {json.dumps(flush_payload)}\n\n".encode()

                    elif btype == "tool_use":
                        accumulated = json_accum.pop(idx, "")
                        if accumulated:
                            if unmask_response:
                                accumulated = replace_tokens(accumulated, mappings)
                            delta_payload = {
                                "type": "content_block_delta",
                                "index": idx,
                                "delta": {"type": "input_json_delta", "partial_json": accumulated},
                            }
                            yield f"event: content_block_delta\ndata: {json.dumps(delta_payload)}\n\n".encode()

                    yield f"event: {ename}\ndata: {json.dumps(payload)}\n\n".encode()

                else:
                    # message_start, message_delta, message_stop, ping, error — pass through
                    yield f"event: {ename}\ndata: {json.dumps(payload)}\n\n".encode()
