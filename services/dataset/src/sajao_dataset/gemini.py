"""Gemini on Vertex AI as a model gateway provider, for screening YouTube URLs.

Vertex AI reads a public YouTube URL directly, so screening needs no download.
Measured with the project's service account: gemini-3-flash-preview and
gemini-3.5-flash-lite accept YouTube URLs at location `global`; gemini-3.5-flash
answers every YouTube request with HTTP 401, so it is not used here.

Credentials come from the `GCP_SA_KEY` environment variable (the service account
JSON, raw or base64) or, without it, Application Default Credentials. Tokens and
keys are never printed, logged or put in error messages.
"""

from __future__ import annotations

import base64
import binascii
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

# YouTube URLs are accepted only at the global endpoint.
VERTEX_LOCATION = "global"

GEMINI_3_FLASH = "gemini-3-flash-preview"
GEMINI_35_FLASH_LITE = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class Price:
    """Vertex AI standard tier, global endpoint, USD per million tokens."""

    input_usd_per_m: float
    output_usd_per_m: float  # Response and reasoning tokens.


# Source: https://cloud.google.com/vertex-ai/generative-ai/pricing (standard tier,
# global). Update with the source when prices change.
PRICES: dict[str, Price] = {
    GEMINI_3_FLASH: Price(0.50, 3.00),
    GEMINI_35_FLASH_LITE: Price(0.30, 2.50),
}

INR_PER_USD = 88  # Same rate as the workers' GPU prices.

# Measured at low media resolution: about 92 prompt tokens per second of video at
# 1 frame per second (frames plus the audio track) and about 60 at 0.5 fps.
# The estimate uses an upper bound so the spend cap is never passed.
VIDEO_TOKENS_PER_S_FIXED = 35  # Audio.
VIDEO_TOKENS_PER_S_PER_FPS = 65  # Frames.


def micro_inr(usd: float) -> int:
    return math.ceil(usd * INR_PER_USD * MICRO_INR_PER_RUPEE)


class TokenSource(Protocol):
    def token(self) -> str:
        """A current OAuth access token for Vertex AI."""
        ...


class GoogleTokens:
    """Access tokens from a service account key in `GCP_SA_KEY`, or from ADC."""

    SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        import google.auth
        from google.oauth2 import service_account

        raw = (env if env is not None else os.environ).get("GCP_SA_KEY", "").strip()
        self._lock = threading.Lock()
        if raw:
            self._creds: Any = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
                parse_service_account(raw), scopes=self.SCOPES
            )
        else:
            self._creds, _ = google.auth.default(scopes=self.SCOPES)

    def token(self) -> str:
        from google.auth.transport.requests import Request

        with self._lock:
            if not self._creds.valid:
                self._creds.refresh(Request())
            return str(self._creds.token)


def parse_service_account(raw: str) -> dict[str, Any]:
    """The key JSON, given raw or base64. Errors never echo the value."""
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        try:
            info = json.loads(base64.b64decode(raw, validate=True))
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("GCP_SA_KEY is neither service account JSON nor base64 JSON") from None
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise ValueError("GCP_SA_KEY is not a service account key")
    return info


class VertexGeminiProvider:
    """One pinned Gemini model on Vertex AI, reading a YouTube URL.

    The request payload carries `video_url`, `start_s`, `end_s`, `fps`, `prompt`,
    `response_schema` and `max_output_tokens`. The output is the parsed JSON
    response; the caller's validator checks it.

    Vertex bills a call even when its output is later rejected, but the gateway
    settles rejected calls at zero. `billed_micro_inr` counts every call Vertex
    answered, so a run's spend cap can use what was really billed.
    """

    modalities: frozenset[Modality] = frozenset({"vision"})
    timeout_seconds = 600.0

    def __init__(
        self,
        name: str,
        model: str,
        *,
        project: str,
        tokens: TokenSource,
        client: httpx.AsyncClient | None = None,
        location: str = VERTEX_LOCATION,
        max_concurrency: int = 4,
    ) -> None:
        if model not in PRICES:
            raise ValueError(f"No pinned price for {model}")
        self.name = name
        self.model = model
        self.max_concurrency = max_concurrency
        self.billed_micro_inr = 0
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
        p = request.payload
        seconds = float(p["end_s"]) - float(p["start_s"])
        per_s = VIDEO_TOKENS_PER_S_FIXED + VIDEO_TOKENS_PER_S_PER_FPS * float(p["fps"])
        input_tokens = seconds * per_s + len(str(p["prompt"])) + 1000
        output_tokens = int(p["max_output_tokens"])
        return micro_inr(
            input_tokens * self._price.input_usd_per_m / 1e6
            + output_tokens * self._price.output_usd_per_m / 1e6
        )

    def actual_cost_micro_inr(self, usage: Mapping[str, Any]) -> int:
        input_tokens = int(usage.get("promptTokenCount", 0))
        output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
            usage.get("thoughtsTokenCount", 0)
        )
        return micro_inr(
            input_tokens * self._price.input_usd_per_m / 1e6
            + output_tokens * self._price.output_usd_per_m / 1e6
        )

    def body(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {"fileUri": payload["video_url"], "mimeType": "video/mp4"},
                            "videoMetadata": self.video_metadata(payload),
                        },
                        {"text": payload["prompt"]},
                    ],
                }
            ],
            "generationConfig": {
                "mediaResolution": "MEDIA_RESOLUTION_LOW",
                "responseMimeType": "application/json",
                "responseSchema": payload["response_schema"],
                "temperature": 0,
                "maxOutputTokens": int(payload["max_output_tokens"]),
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }

    @staticmethod
    def video_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Offsets only when part of the video is screened (`clip` is true): the
        pilot's timestamps were checked on whole videos."""
        meta: dict[str, Any] = {"fps": float(payload["fps"])}
        if payload.get("clip"):
            meta["startOffset"] = f"{float(payload['start_s']):g}s"
            meta["endOffset"] = f"{float(payload['end_s']):g}s"
        return meta

    async def call(self, request: ModelRequest) -> ProviderResult:
        try:
            token = self._tokens.token()
        except Exception as error:
            # Credential errors can quote the key file; report only the type.
            raise ProviderError(f"credentials: {type(error).__name__}", retryable=False) from None
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {token}"},
                json=self.body(request.payload),
            )
        except httpx.TransportError as error:
            raise ProviderError(f"transport: {type(error).__name__}") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(f"Vertex AI HTTP {response.status_code}")
        if response.is_error:
            raise ProviderError(f"Vertex AI HTTP {response.status_code}", retryable=False)

        data = response.json()
        cost = self.actual_cost_micro_inr(data.get("usageMetadata", {}))
        self.billed_micro_inr += cost
        try:
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
            output = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            candidates = data.get("candidates") or [{}]
            reason = candidates[0].get("finishReason", "no candidate")
            raise InvalidOutputError(f"no JSON in the response ({reason})") from None
        if not isinstance(output, dict):
            raise InvalidOutputError("the response is not a JSON object")
        return ProviderResult(output=output, cost_micro_inr=cost)
