"""Claude (Anthropic API) as a gateway provider, for text and vision tasks.

Used for the design engine's language and vision steps: brief to spec, designer,
ranker and explanations. The API key is read by the Anthropic SDK from
ANTHROPIC_API_KEY (the Modal secret `anthropic`); it is never logged.

Request payload:
  {"system": str (optional), "prompt": str, "effort": "low"|"medium"|"high" (optional),
   "max_tokens": int (optional), "schema": JSON schema (optional, for structured output)}
Images go in `request.blobs` (PNG or JPEG bytes) and are sent before the prompt.

Output: {"text": str, "json": object (when a schema was given), "stop_reason": str,
         "usage": {...}}. Cost is computed per call from the reported token usage.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from sajao_gateway.errors import ProviderError
from sajao_gateway.types import MICRO_INR_PER_RUPEE, Modality, ModelRequest, ProviderResult

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: (input, output, cache read). Cache writes cost 1.25x input.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
USD_TO_INR = 85.0
MONTHLY_BUDGET_USD = 100.0


def daily_cap_micro_inr(monthly_usd: float = MONTHLY_BUDGET_USD) -> int:
    """Global daily cap that keeps a month under `monthly_usd`."""
    return round(monthly_usd / 30 * USD_TO_INR * MICRO_INR_PER_RUPEE)


def cost_micro_inr(model: str, usage: dict[str, int]) -> int:
    inp, out, cache_read = PRICES_USD_PER_MTOK[model]
    usd = (
        usage.get("input_tokens", 0) * inp
        + usage.get("output_tokens", 0) * out
        + usage.get("cache_read_input_tokens", 0) * cache_read
        + usage.get("cache_creation_input_tokens", 0) * inp * 1.25
    ) / 1_000_000
    return round(usd * USD_TO_INR * MICRO_INR_PER_RUPEE)


def _media_type(blob: bytes) -> str:
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    raise ProviderError("unsupported image format", retryable=False)


@dataclass
class ClaudeProvider:
    """A Claude model behind the Anthropic API; `client` is an AsyncAnthropic or a test fake."""

    client: Any = None
    model: str = DEFAULT_MODEL
    name: str = "anthropic-claude"
    modalities: frozenset[Modality] = frozenset({"text", "vision"})
    max_concurrency: int = 4
    default_max_tokens: int = 8000
    use_fallbacks: bool = True
    timeout_seconds: float | None = 300.0
    max_attempts: int | None = None

    def _client(self) -> Any:
        if self.client is None:
            import anthropic

            self.client = anthropic.AsyncAnthropic(max_retries=0)  # the gateway retries
        return self.client

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        """Upper bound: prompt chars / 3 as tokens, about 1,600 tokens per image, full output."""
        prompt = str(request.payload.get("prompt", "")) + str(request.payload.get("system", ""))
        in_tokens = len(prompt) // 3 + 1600 * len(request.blobs) + 500
        out_tokens = int(request.payload.get("max_tokens", self.default_max_tokens))
        return cost_micro_inr(self.model, {"input_tokens": in_tokens, "output_tokens": out_tokens})

    def _params(self, request: ModelRequest) -> dict[str, Any]:
        p = request.payload
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _media_type(b),
                    "data": base64.standard_b64encode(b).decode(),
                },
            }
            for b in request.blobs
        ]
        content.append({"type": "text", "text": str(p["prompt"])})
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(p.get("max_tokens", self.default_max_tokens)),
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": p.get("effort", "medium")},
        }
        if p.get("system"):
            params["system"] = str(p["system"])
        if p.get("schema"):
            params["output_config"]["format"] = {"type": "json_schema", "schema": p["schema"]}
        if self.use_fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    async def call(self, request: ModelRequest) -> ProviderResult:
        import anthropic

        if "prompt" not in request.payload:
            raise ProviderError("payload needs a prompt", retryable=False)
        try:
            msg = await self._client().beta.messages.create(**self._params(request))
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"anthropic status {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection error", retryable=True) from exc
        usage = {
            k: int(getattr(msg.usage, k, 0) or 0)
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
        }
        served_by = getattr(msg, "model", self.model) or self.model
        price_model = served_by if served_by in PRICES_USD_PER_MTOK else self.model
        cost = cost_micro_inr(price_model, usage)
        if msg.stop_reason == "refusal":
            raise ProviderError("model declined the request", retryable=False)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        out: dict[str, Any] = {
            "text": text,
            "stop_reason": msg.stop_reason,
            "usage": usage,
            "served_by": served_by,
        }
        if request.payload.get("schema"):
            try:
                out["json"] = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProviderError("structured output was not JSON", retryable=True) from exc
        return ProviderResult(output=out, cost_micro_inr=cost)
