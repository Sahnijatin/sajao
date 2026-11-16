"""Convert Depth Anything V2 Small to LiteRT at small fixed inputs.

Measurement only: the Android depth benchmark runs these models. Usage:
``python convert.py <revision>``. See README.md.
"""

import sys
import time

import litert_torch
import numpy as np
import torch
from transformers import AutoModelForDepthEstimation

REPO = "depth-anything/Depth-Anything-V2-Small-hf"
# Width by height, portrait, multiples of the model's 14 px patch.
SIZES = [(196, 252), (266, 350)]


class DepthOnly(torch.nn.Module):
    """Returns just the depth map, so the LiteRT model has one output."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        return self.model(pixel_values=pixels).predicted_depth


def main(revision: str) -> None:
    model = AutoModelForDepthEstimation.from_pretrained(REPO, revision=revision).eval()
    wrapped = DepthOnly(model).eval()
    for width, height in SIZES:
        started = time.time()
        edge = litert_torch.convert(wrapped, (torch.rand(1, 3, height, width),))
        name = f"fp32_{width}x{height}.tflite"
        edge.export(name)
        # The converted model must agree with PyTorch on a gradient image.
        ramp = torch.linspace(0, 1, height).view(1, 1, height, 1).expand(1, 3, height, width)
        ramp = ramp.contiguous()
        reference = wrapped(ramp).detach().numpy()
        converted = np.asarray(edge(ramp))
        corr = np.corrcoef(reference.ravel(), converted.ravel())[0, 1]
        print(f"{name}: {time.time() - started:.0f} s, correlation with PyTorch {corr:.4f}")


if __name__ == "__main__":
    main(sys.argv[1])
