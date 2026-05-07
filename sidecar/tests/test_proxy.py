import json
import pytest
import respx
import httpx
from aivion_mask_sidecar.proxy import forward_streaming, forward_complete
from aivion_mask_sidecar.session import init_db, save_token

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "t.db")
    save_token(c, "s1", "__DB1__", "secret123", 1, ttl_hours=8)
    yield c
    c.close()

@respx.mock
@pytest.mark.asyncio
async def test_forward_complete_unscrubs(conn):
    body = {"choices": [{"message": {"role": "assistant", "content": "the value is __DB1__ ok"}}]}
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = await forward_complete(
        request_body={"messages": [], "model": "gpt-4o"},
        api_base="https://api.openai.com/v1",
        api_key="test-key",
        session_id="s1",
        conn=conn,
    )
    assert result["choices"][0]["message"]["content"] == "the value is secret123 ok"

@respx.mock
@pytest.mark.asyncio
async def test_forward_complete_passes_auth_header(conn):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )
    await forward_complete(
        request_body={"messages": []},
        api_base="https://api.openai.com/v1",
        api_key="sk-mykey",
        session_id="s1",
        conn=conn,
    )
    call = respx.calls.last
    assert call.request.headers["authorization"] == "Bearer sk-mykey"

@respx.mock
@pytest.mark.asyncio
async def test_forward_streaming_unscrubs(conn):
    chunks = [
        'data: {"choices":[{"delta":{"content":"value is __DB"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":"1__ ok"},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text="".join(chunks),
                                    headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for line in forward_streaming(
        request_body={"messages": [], "stream": True},
        api_base="https://api.openai.com/v1",
        api_key="test-key",
        session_id="s1",
        conn=conn,
    ):
        collected.append(line.decode())

    full = "".join(collected)
    assert "secret123" in full
    assert "__DB1__" not in full
