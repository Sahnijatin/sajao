"""Arm B's API model: Gemini image editing on Vertex AI, called through the model gateway.

Credentials come only from the Modal secret `gcp` (GCP_SA_KEY, a service account
JSON), never from the repo or logs. Every call goes through sajao_gateway's
ModelGateway: spend cap, retries, timeout, output validation and a call log.
"""

from __future__ import annotations

import asyncio
import io
import json
import os

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
USD_INR = 85.0
# Upper bound per edit (one high-resolution output image plus inputs), in micro-rupees.
EST_MICRO_INR = int(0.25 * USD_INR * 1_000_000)
DAILY_CAP_MICRO_INR = int(2000 * 1_000_000)  # Rs 2,000 for the bake-off

_gw = None


class GeminiImageProvider:
    name = "vertex-gemini-image"
    model = MODEL
    modalities = frozenset({"image"})
    max_concurrency = 2

    def __init__(self) -> None:
        from google import genai
        from google.oauth2 import service_account

        info = json.loads(os.environ["GCP_SA_KEY"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._client = genai.Client(vertexai=True, project=info["project_id"],
                                    location=os.environ.get("GCP_LOCATION", "global"), credentials=creds)

    def estimate_cost_micro_inr(self, request) -> int:
        return EST_MICRO_INR

    async def call(self, request):
        from google.genai import types
        from PIL import Image
        from sajao_gateway.types import ProviderResult

        parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in request.blobs]
        parts.append(types.Part.from_text(text=request.payload["prompt"]))
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"], seed=int(request.payload["seed"]))
        resp = await self._client.aio.models.generate_content(model=self.model, contents=parts, config=cfg)
        out = []
        for c in resp.candidates or []:
            for p in (c.content.parts if c.content else []) or []:
                if getattr(p, "inline_data", None) and p.inline_data.data:
                    out.append(p.inline_data.data)
        usage = getattr(resp, "usage_metadata", None)
        # Cost from token usage at list prices (images are billed as output tokens).
        cost = EST_MICRO_INR
        if usage is not None and getattr(usage, "candidates_token_count", None):
            usd = (usage.prompt_token_count or 0) * 2e-6 + usage.candidates_token_count * 120e-6
            cost = int(usd * USD_INR * 1_000_000)
        sizes = [Image.open(io.BytesIO(b)).size for b in out]
        return ProviderResult(output={"images": len(out), "sizes": sizes}, blobs=tuple(out), cost_micro_inr=cost)


def gateway():
    global _gw
    if _gw is None:
        from sajao_gateway.gateway import ModelGateway
        from sajao_gateway.spend import InMemorySpendLedger, SpendCaps
        from sajao_gateway.types import RetryPolicy

        _gw = ModelGateway(
            [GeminiImageProvider()],
            ledger=InMemorySpendLedger(SpendCaps(per_user_daily_micro_inr=DAILY_CAP_MICRO_INR,
                                                 global_daily_micro_inr=DAILY_CAP_MICRO_INR)),
            retry=RetryPolicy(max_attempts=3, timeout_seconds=180.0),
        )
    return _gw


def _validate(resp_output) -> None:
    from sajao_gateway.errors import InvalidOutputError

    out = resp_output.output if hasattr(resp_output, "output") else resp_output
    if out.get("images", 0) < 1 or min(out["sizes"][0]) < 256:
        raise InvalidOutputError("expected one image of at least 256 px")


def gemini_edit(pils, prompt: str, seed: int):
    """Edit pils[0] with references pils[1:]. Returns a PIL image."""
    from PIL import Image
    from sajao_gateway.types import ModelRequest

    blobs = []
    for p in pils:
        b = io.BytesIO()
        p.save(b, format="PNG")
        blobs.append(b.getvalue())
    req = ModelRequest(task="render_bakeoff_arm_b", modality="image", prompt_id="arm_b_region_edit@1",
                       payload={"prompt": prompt, "seed": seed}, blobs=tuple(blobs))
    resp = asyncio.run(gateway().call(req, validate=_validate))
    return Image.open(io.BytesIO(resp.blobs[0])).convert("RGB")
