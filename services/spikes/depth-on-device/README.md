# On-device depth speed (measurement only)

Builds the two models the Android benchmark runs, to decide whether a small
depth model can drive the live scan (decision: reverse "surface effect
without a depth model", pending this measurement).

- Model: `depth-anything/Depth-Anything-V2-Small-hf`, revision
  `5426e4f0f36572d16453bbda7a8389317b1bef99`, Apache 2.0.
- `convert.py <revision>`: PyTorch to LiteRT with `litert-torch` at fixed
  inputs 196 by 252 and 266 by 350 (portrait, multiples of the 14 px patch).
  The converted output matches PyTorch (correlation 1.0000).
- `quantize.py`: weights to int8 with `ai-edge-quantizer`
  (`weight_only_wi8_afp32`): 27.7 MB each instead of 99 MB, computation
  still in float, correlation with the float model 0.997 and 0.999.

Run in a separate virtual environment (Python 3.11):
`uv pip install litert-torch transformers ai-edge-quantizer pillow`, then
`python convert.py 5426e4f0f36572d16453bbda7a8389317b1bef99 && python quantize.py`.
The outputs go to `apps/mobile/modules/sajao-ar/android/benchmark-assets/`.

Bundled files (sha256):

- `depth_anything_v2_small_196x252.tflite`: `124c9dcb936a3191b75e3fd2fd3b51997df525496ee98abcc9ce2908c0f57397`
- `depth_anything_v2_small_266x350.tflite`: `ad3caa0c10888a7513dc0fc8b4585c960ec58c2d5364a19ac0b3b7c1864b1e6f`

Tools (measurement only, not in the app): `litert-torch` 0.10.0 and
`ai-edge-quantizer` 0.10.1 (Apache 2.0). App runtime for the benchmark:
LiteRT 1.4.2 and its GPU delegate (Apache 2.0).
