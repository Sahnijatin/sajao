"""Vision-language models behind the gateway: Gemini on Vertex AI and Claude.

Both take JPEG images in `request.blobs` and a payload with `prompt`,
`response_schema` (JSON Schema) and `max_output_tokens`, and return the parsed
JSON object; the caller's validator checks it. Costs are pinned per model and
charged from the tokens each call used. Credentials are never printed, logged
or put in error messages.
"""

from __future__ import annotations

import base64
import json
import math
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from sajao_gateway import (
    MICRO_INR_PER_RUPEE,
    InvalidOutputError,
    ModelRequest,
    ProviderError,
    ProviderResult,
)
from sajao_gateway.types import Modality

INR_PER_USD = 95

GEMINI_3_FLASH = "gemini-3-flash-preview"
GEMINI_35_FLASH_LITE = "gemini-3.5-flash-lite"
CLAUDE_OPUS = "claude-opus-5-5"


@dataclass(frozen=True)
class Price:
    """USD per million tokens (output includes thinking tokens)."""

    input_usd_per_m: float
    output_usd_per_m: float


# Vertex AI standard tier, global endpoint; Claude API list prices. Update with
# the source when prices change.
PRICES: dict[str, Price] = {
    GEMINI_3_FLASH: Price(0.50, 3.00),
    GEMINI_35_FLASH_LITE: Price(0.30, 2.50),
    CLAUDE_OPUS: Price(4.00, 20.00),
}

# An upper bound on input tokens per image (images are at most 1024 px on the long side).
TOKENS_PER_IMAGE = 1600


def _micro_inr(price: Price, input_tokens: float, output_tokens: float) -> int:
    usd = input_tokens * price.input_usd_per_m / 1e6 + output_tokens * price.output_usd_per_m / 1e6
    return math.ceil(usd * INR_PER_USD * MICRO_INR_PER_RUPEE)


def _estimate(price: Price, request: ModelRequest) -> int:
    p = request.payload
    input_tokens = TOKENS_PER_IMAGE * len(request.blobs) + len(str(p["prompt"])) + 1000
    return _micro_inr(price, input_tokens, int(p["max_output_tokens"]))


def _json_object(text: str, what: str) -> dict[str, Any]:
    try:
        output = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidOutputError(f"no JSON in the response ({what})") from None
    if not isinstance(output, dict):
        raise InvalidOutputError("the response is not a JSON object")
    return output


class TokenSource(Protocol):
    def token(self) -> str: ...


class GoogleTokens:
    """Vertex AI access tokens from the service account key in `GCP_SA_KEY` (raw or base64)."""

    SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        from google.oauth2 import service_account

        raw = (env if env is not None else os.environ).get("GCP_SA_KEY", "").strip()
        if not raw:
            raise ValueError("GCP_SA_KEY is not set")
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            try:
                info = json.loads(base64.b64decode(raw, validate=True))
            except ValueError:
                raise ValueError("GCP_SA_KEY is neither JSON nor base64 JSON") from None
        self._lock = threading.Lock()
        self._creds: Any = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            info, scopes=self.SCOPES
        )

    def token(self) -> str:
        from google.auth.transport.requests import Request

        with self._lock:
            if not self._creds.valid:
                self._creds.refresh(Request())
            return str(self._creds.token)


class VertexGeminiVision:
    """One pinned Gemini model on Vertex AI, reading images."""

    modalities: frozenset[Modality] = frozenset({"vision"})
    timeout_seconds = 180.0

    def __init__(
        self,
        name: str,
        model: str,
        *,
        project: str,
        tokens: TokenSource,
        client: httpx.AsyncClient | None = None,
        location: str = "global",
        max_concurrency: int = 4,
    ) -> None:
        if model not in PRICES:
            raise ValueError(f"No pinned price for {model}")
        self.name = name
        self.model = model
        self.max_concurrency = max_concurrency
        self._price = PRICES[model]
        self._tokens = tokens
        self._client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        host = "aiplatform.googleapis.com"
        if location != "global":
            host = f"{location}-{host}"
        self._url = (
            f"https://{host}/v1/projects/{project}/locations/{location}"
            f"/publishers/google/models/{model}:generateContent"
        )

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return _estimate(self._price, request)

    async def call(self, request: ModelRequest) -> ProviderResult:
        p = request.payload
        parts: list[dict[str, Any]] = [
            {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(b).decode()}}
            for b in request.blobs
        ]
        parts.append({"text": p["prompt"]})
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                "responseMimeType": "application/json",
                "responseJsonSchema": p["response_schema"],
                "temperature": 0,
                "maxOutputTokens": int(p["max_output_tokens"]),
            },
        }
        if "thinking_level" in p:  # optional: "low" keeps simple tasks from over-thinking
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": p["thinking_level"]}
        try:
            token = self._tokens.token()
        except Exception as error:
            raise ProviderError(f"credentials: {type(error).__name__}", retryable=False) from None
        try:
            response = await self._client.post(
                self._url, headers={"Authorization": f"Bearer {token}"}, json=body
            )
        except httpx.TransportError as error:
            raise ProviderError(f"transport: {type(error).__name__}") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(f"Vertex AI HTTP {response.status_code}")
        if response.is_error:
            raise ProviderError(f"Vertex AI HTTP {response.status_code}", retryable=False)

        data = response.json()
        usage = data.get("usageMetadata", {})
        cost = _micro_inr(
            self._price,
            int(usage.get("promptTokenCount", 0)),
            int(usage.get("candidatesTokenCount", 0)) + int(usage.get("thoughtsTokenCount", 0)),
        )
        try:
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise InvalidOutputError("no candidate in the response") from None
        return ProviderResult(
            output=_json_object(text, str(candidate.get("finishReason"))), cost_micro_inr=cost
        )


class ClaudeVision:
    """One pinned Claude model, reading images, with server-side fallbacks on.

    If the model declines, the API retries on its default substitute model; the
    response says which model answered. A refusal from the whole chain is an
    invalid output, so the gateway moves on.
    """

    modalities: frozenset[Modality] = frozenset({"vision"})
    timeout_seconds = 300.0
    max_attempts = 2

    def __init__(
        self, name: str, model: str, *, client: Any | None = None, max_concurrency: int = 2
    ) -> None:
        if model not in PRICES:
            raise ValueError(f"No pinned price for {model}")
        self.name = name
        self.model = model
        self.max_concurrency = max_concurrency
        self._price = PRICES[model]
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic(max_retries=0)  # the gateway retries
        self._client: Any = client

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return _estimate(self._price, request)

    async def call(self, request: ModelRequest) -> ProviderResult:
        p = request.payload
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(b).decode(),
                },
            }
            for b in request.blobs
        ]
        content.append({"type": "text", "text": p["prompt"]})
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=int(p["max_output_tokens"]),
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema", "schema": p["response_schema"]}},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as error:
            status = getattr(error, "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            raise ProviderError(
                f"Claude API {status or type(error).__name__}", retryable=retryable
            ) from None

        usage = response.usage
        cost = _micro_inr(self._price, int(usage.input_tokens), int(usage.output_tokens))
        if response.stop_reason == "refusal":
            raise InvalidOutputError("the model declined")
        if response.stop_reason == "max_tokens":
            raise InvalidOutputError("the response was cut off")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return ProviderResult(
            output=_json_object(text, str(response.stop_reason)), cost_micro_inr=cost
        )
