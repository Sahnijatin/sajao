"""Pure helpers for the Space Twin risk spike.

Plain Python only, so they run in CI and inside the GPU jobs alike. Nothing here
calls a model or sets a dimension from a generative model: boxes are fitted from
measured or estimated geometry and compared with annotated ground truth.
"""
