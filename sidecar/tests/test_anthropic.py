import json
import pytest
import respx
import httpx
from aivion_mask_sidecar.anthropic import (
    walk_request,
    walk_response,
    forward_complete_anthropic,
    forward_streaming_anthropic,
)
from aivion_mask_sidecar.session import init_db, save_token

_DB_URL = "postgresql://user:pass@host/db"
_DB_TOKEN = "__DB1__"

_HEADERS = {
    "x-api-key": "sk-ant-test",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}

_EMPTY_RESPONSE = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "content": [],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


@pytest.fixture
async def conn(tmp_path):
    c = await init_db(tmp_path / "t.db")
    await save_token(c, "s1", _DB_TOKEN, _DB_URL, 1, ttl_hours=8)
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# walk_request
# ---------------------------------------------------------------------------

async def test_walk_request_string_system(conn):
    body = {"system": f"Use the DB at {_DB_URL} for queries", "messages": []}
    result = await walk_request(body, conn, "s1", 8)
    assert _DB_TOKEN in result["system"]
    assert _DB_URL not in result["system"]


async def test_walk_request_block_system(conn):
    body = {
        "system": [{"type": "text", "text": f"DB is {_DB_URL}"}],
        "messages": [],
    }
    result = await walk_request(body, conn, "s1", 8)
    assert result["system"][0]["type"] == "text"
    assert _DB_TOKEN in result["system"][0]["text"]
    assert _DB_URL not in result["system"][0]["text"]


async def test_walk_request_string_content(conn):
    body = {"messages": [{"role": "user", "content": f"connect to {_DB_URL}"}]}
    result = await walk_request(body, conn, "s1", 8)
    assert _DB_TOKEN in result["messages"][0]["content"]
    assert _DB_URL not in result["messages"][0]["content"]


async def test_walk_request_block_content_text_and_tool_result(conn):
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"use {_DB_URL}"},
                    {"type": "tool_result", "tool_use_id": "x", "content": f"ok, used {_DB_URL}"},
                ],
            }
        ]
    }
    result = await walk_request(body, conn, "s1", 8)
    blocks = result["messages"][0]["content"]
    assert _DB_TOKEN in blocks[0]["text"]
    assert _DB_TOKEN in blocks[1]["content"]
    assert _DB_URL not in blocks[0]["text"]
    assert _DB_URL not in blocks[1]["content"]


async def test_walk_request_tool_use_input(conn):
    body = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "bash",
                        "input": {"command": f"psql {_DB_URL}"},
                    }
                ],
            }
        ]
    }
    result = await walk_request(body, conn, "s1", 8)
    cmd = result["messages"][0]["content"][0]["input"]["command"]
    assert _DB_TOKEN in cmd
    assert _DB_URL not in cmd


async def test_walk_request_preserves_non_text_blocks(conn):
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "url", "url": "https://example.com/img.png"}},
                    {"type": "text", "text": "describe this"},
                ],
            }
        ]
    }
    result = await walk_request(body, conn, "s1", 8)
    img = result["messages"][0]["content"][0]
    assert img["type"] == "image"
    assert img["source"]["url"] == "https://example.com/img.png"


async def test_walk_request_passthrough_when_no_secrets(conn):
    body = {"messages": [{"role": "user", "content": "hello world"}]}
    result = await walk_request(body, conn, "s1", 8)
    assert result["messages"][0]["content"] == "hello world"


# ---------------------------------------------------------------------------
# walk_response
# ---------------------------------------------------------------------------

def test_walk_response_text_block():
    mappings = {_DB_TOKEN: _DB_URL}
    body = {"content": [{"type": "text", "text": f"connected to {_DB_TOKEN} successfully"}]}
    result = walk_response(body, mappings)
    assert result["content"][0]["text"] == f"connected to {_DB_URL} successfully"


def test_walk_response_tool_use_input():
    mappings = {_DB_TOKEN: _DB_URL}
    body = {
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "bash", "input": {"command": f"psql {_DB_TOKEN}"}}
        ]
    }
    result = walk_response(body, mappings)
    assert result["content"][0]["input"]["command"] == f"psql {_DB_URL}"


def test_walk_response_unknown_blocks_pass_through():
    mappings = {_DB_TOKEN: _DB_URL}
    body = {"content": [{"type": "image", "source": {"url": "https://x.com/img.png"}}]}
    result = walk_response(body, mappings)
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["source"]["url"] == "https://x.com/img.png"


def test_walk_response_empty_content():
    result = walk_response({"content": []}, {})
    assert result["content"] == []


# ---------------------------------------------------------------------------
# forward_complete_anthropic
# ---------------------------------------------------------------------------

@respx.mock
async def test_forward_complete_passes_x_api_key(conn):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=_EMPTY_RESPONSE)
    )
    await forward_complete_anthropic({"messages": [], "model": "claude-sonnet-4-6"}, _HEADERS, "s1", conn)
    assert respx.calls.last.request.headers["x-api-key"] == "sk-ant-test"


@respx.mock
async def test_forward_complete_passes_oauth_bearer(conn):
    oauth_headers = {
        "Authorization": "Bearer sk-ant-oat01-token",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=_EMPTY_RESPONSE)
    )
    await forward_complete_anthropic({"messages": [], "model": "claude-sonnet-4-6"}, oauth_headers, "s1", conn)
    assert respx.calls.last.request.headers["authorization"] == "Bearer sk-ant-oat01-token"


@respx.mock
async def test_forward_complete_forwards_anthropic_version(conn):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=_EMPTY_RESPONSE)
    )
    await forward_complete_anthropic({"messages": [], "model": "m"}, _HEADERS, "s1", conn)
    assert respx.calls.last.request.headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_forward_complete_unmasks_text_response(conn):
    response_body = {**_EMPTY_RESPONSE, "content": [{"type": "text", "text": f"connected to {_DB_TOKEN} fine"}]}
    respx.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json=response_body))
    result = await forward_complete_anthropic({"messages": [], "model": "m"}, _HEADERS, "s1", conn)
    assert result["content"][0]["text"] == f"connected to {_DB_URL} fine"


@respx.mock
async def test_forward_complete_skips_unmask_when_disabled(conn):
    response_body = {**_EMPTY_RESPONSE, "content": [{"type": "text", "text": f"token is {_DB_TOKEN}"}]}
    respx.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json=response_body))
    result = await forward_complete_anthropic(
        {"messages": [], "model": "m"}, _HEADERS, "s1", conn, unmask_response=False
    )
    assert _DB_TOKEN in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# forward_streaming_anthropic
# ---------------------------------------------------------------------------

def _sse(events: list[tuple[str, dict]]) -> str:
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events)


@respx.mock
async def test_streaming_text_delta_split_placeholder_unmasked(conn):
    stream = _sse([
        ("message_start", {"type": "message_start", "message": {"id": "msg_1"}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": f"connected to __DB"}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "1__ successfully"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_stop", {"type": "message_stop"}),
    ])
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for chunk in forward_streaming_anthropic(
        {"messages": [], "model": "m", "stream": True}, _HEADERS, "s1", conn
    ):
        collected.append(chunk.decode())
    full = "".join(collected)
    assert _DB_URL in full
    assert "__DB1__" not in full


@respx.mock
async def test_streaming_tool_use_json_split_across_deltas(conn):
    stream = _sse([
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "tu_1", "name": "bash", "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"command": "psql __DB'}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '1__"}'}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_stop", {"type": "message_stop"}),
    ])
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for chunk in forward_streaming_anthropic(
        {"messages": [], "model": "m", "stream": True}, _HEADERS, "s1", conn
    ):
        collected.append(chunk.decode())
    full = "".join(collected)
    assert _DB_URL in full
    assert "__DB1__" not in full


@respx.mock
async def test_streaming_passthrough_events(conn):
    stream = _sse([
        ("ping", {"type": "ping"}),
        ("message_stop", {"type": "message_stop"}),
    ])
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for chunk in forward_streaming_anthropic(
        {"messages": [], "model": "m", "stream": True}, _HEADERS, "s1", conn
    ):
        collected.append(chunk.decode())
    full = "".join(collected)
    assert "ping" in full
    assert "message_stop" in full


@respx.mock
async def test_streaming_preserves_event_names(conn):
    stream = _sse([
        ("message_start", {"type": "message_start", "message": {}}),
        ("message_stop", {"type": "message_stop"}),
    ])
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for chunk in forward_streaming_anthropic(
        {"messages": [], "model": "m", "stream": True}, _HEADERS, "s1", conn
    ):
        collected.append(chunk.decode())
    full = "".join(collected)
    assert "event: message_start" in full
    assert "event: message_stop" in full
