"""Vision-language providers for the room inventory: Gemini on Vertex AI and Claude."""

import base64
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from sajao_gateway import InvalidOutputError, ModelRequest, ProviderError
from sajao_workers.twin.inventory import INVENTORY_SCHEMA
from sajao_workers.vision import ClaudeVision, VertexGeminiVision

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
LISTED = {"items": [{"name": "sofa", "type": "furniture", "count": 1, "prompts": []}]}


def request(images: int = 2) -> ModelRequest:
    payload = {
        "prompt": "List it all.",
        "response_schema": INVENTORY_SCHEMA,
        "max_output_tokens": 4000,
    }
    return ModelRequest("twin_inventory", "vision", "twin_inventory@1", payload, (JPEG,) * images)


class Tokens:
    def token(self) -> str:
        return "token"


def gemini(handler: Any) -> VertexGeminiVision:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return VertexGeminiVision(
        "gemini", "gemini-3-flash-preview", project="p", tokens=Tokens(), client=client
    )


async def test_gemini_sends_the_images_and_the_schema_and_is_charged_for_its_tokens() -> None:
    sent: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        sent.update(json.loads(r.content))
        sent["url"] = str(r.url)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(LISTED)}]}}],
                "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 500},
            },
        )

    provider = gemini(handler)
    result = await provider.call(request())

    assert result.output == LISTED
    parts = sent["contents"][0]["parts"]
    assert [p["inlineData"]["mimeType"] for p in parts[:2]] == ["image/jpeg"] * 2
    assert base64.b64decode(parts[0]["inlineData"]["data"]) == JPEG
    assert parts[2]["text"] == "List it all."
    assert sent["generationConfig"]["responseJsonSchema"] == INVENTORY_SCHEMA
    assert sent["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert sent["generationConfig"]["temperature"] == 0
    assert "gemini-3-flash-preview:generateContent" in sent["url"]
    # 2000 x 0.50 + 500 x 3.00 USD per million tokens, at 95 rupees per USD.
    assert result.cost_micro_inr == pytest.approx(0.0025 * 95 * 1e6, rel=0.01)
    assert provider.estimate_cost_micro_inr(request()) >= result.cost_micro_inr


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (503, True), (400, False)])
async def test_gemini_errors_say_whether_to_retry(status: int, retryable: bool) -> None:
    provider = gemini(lambda r: httpx.Response(status, json={}))
    with pytest.raises(ProviderError) as raised:
        await provider.call(request())
    assert raised.value.retryable is retryable


async def test_gemini_without_json_is_invalid_output() -> None:
    body = {"candidates": [{"content": {"parts": [{"text": "no"}]}, "finishReason": "STOP"}]}
    provider = gemini(lambda r: httpx.Response(200, json=body))
    with pytest.raises(InvalidOutputError):
        await provider.call(request())


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def claude_response(text: str, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=3000, output_tokens=1000),
    )


def claude(response: Any) -> tuple[ClaudeVision, FakeMessages]:
    messages = FakeMessages(response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeVision("claude", "claude-opus-5-5", client=client), messages


async def test_claude_asks_for_structured_json_with_fallbacks_on() -> None:
    provider, messages = claude(claude_response(json.dumps(LISTED)))

    result = await provider.call(request())

    assert result.output == LISTED
    sent = messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert sent["fallbacks"] == "default"
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": INVENTORY_SCHEMA}
    content = sent["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]
    assert content[0]["source"]["media_type"] == "image/jpeg"
    # 3000 x 4 + 1000 x 20 USD per million tokens, at 95 rupees per USD.
    assert result.cost_micro_inr == pytest.approx(0.032 * 95 * 1e6, rel=0.01)


async def test_a_refusal_is_invalid_output() -> None:
    provider, _ = claude(claude_response("", stop="refusal"))
    with pytest.raises(InvalidOutputError):
        await provider.call(request())
