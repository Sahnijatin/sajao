"""ClaudeProvider with a fake Anthropic client: no network, no key."""

from types import SimpleNamespace
from typing import Any

import pytest

from sajao_gateway import InMemorySpendLedger, ModelGateway, ModelRequest, SpendCaps
from sajao_gateway.claude import ClaudeProvider, cost_micro_inr, daily_cap_micro_inr
from sajao_gateway.errors import ProviderError
from sajao_gateway.types import ProviderResult

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class FakeMessages:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.params: dict[str, Any] = {}

    async def create(self, **params: Any) -> Any:
        self.params = params
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def fake_client(reply: Any) -> SimpleNamespace:
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(reply)))


def reply(text: str, stop: str = "end_turn", model: str = "claude-opus-5-5") -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop,
        model=model,
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def req(**payload: Any) -> ModelRequest:
    return ModelRequest(
        task="ranker", modality="vision", prompt_id="ranker@1", payload=payload, blobs=(PNG,)
    )


async def test_builds_request_and_costs_from_usage() -> None:
    client = fake_client(reply('{"order": [2, 1]}'))
    p = ClaudeProvider(client=client)
    res = await p.call(
        req(prompt="Rank these", system="You rank rooms.", schema={"type": "object"})
    )
    sent = client.beta.messages.params
    assert sent["model"] == "claude-opus-5-5"
    assert sent["messages"][0]["content"][0]["source"]["media_type"] == "image/png"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["fallbacks"] == "default"
    assert res.output["json"] == {"order": [2, 1]}
    # 1000 in at $4/M + 200 out at $20/M = $0.008 = Rs 0.76 at Rs 95 per USD
    assert res.cost_micro_inr == cost_micro_inr(
        "claude-opus-5-5", {"input_tokens": 1000, "output_tokens": 200}
    )
    assert res.cost_micro_inr == 760_000


async def test_refusal_is_not_retryable() -> None:
    p = ClaudeProvider(client=fake_client(reply("", stop="refusal")))
    with pytest.raises(ProviderError) as e:
        await p.call(req(prompt="x"))
    assert e.value.retryable is False


async def test_server_error_is_retryable() -> None:
    import anthropic
    import httpx2

    resp = httpx2.Response(
        529, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    err = anthropic.APIStatusError("overloaded", response=resp, body=None)
    p = ClaudeProvider(client=fake_client(err))
    with pytest.raises(ProviderError) as e:
        await p.call(req(prompt="x"))
    assert e.value.retryable is True


async def test_through_the_gateway_with_spend_tracking() -> None:
    p = ClaudeProvider(client=fake_client(reply("ok")))
    ledger = InMemorySpendLedger(
        SpendCaps(
            per_user_daily_micro_inr=daily_cap_micro_inr(),
            global_daily_micro_inr=daily_cap_micro_inr(),
        )
    )
    gw = ModelGateway([p], ledger=ledger)

    def validate(r: ProviderResult) -> None:
        assert r.output["text"]

    out = await gw.call(
        ModelRequest(
            task="explanations",
            modality="text",
            prompt_id="explain@1",
            payload={"prompt": "Why does this work?"},
        ),
        validate=validate,
    )
    assert out.output["text"] == "ok"
    assert ledger.spent_today() == out.cost_micro_inr > 0


def test_daily_cap_matches_monthly_budget() -> None:
    # 100 USD a month at Rs 95 per USD is about Rs 317 a day.
    assert daily_cap_micro_inr() == round(100 / 30 * 95 * 1_000_000)
