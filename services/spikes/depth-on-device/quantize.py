"""Store the converted models' weights as int8 (about 4 times smaller).

``weight_only_wi8_afp32`` expands the weights back to float at load time, so
the computation, and its speed, match the float model. See README.md.
"""

import time

import numpy as np
from ai_edge_litert.interpreter import Interpreter
from ai_edge_quantizer import quantizer, recipe

SIZES = [(196, 252), (266, 350)]


def run(path: str, pixels: np.ndarray) -> tuple[np.ndarray, float]:
    interpreter = Interpreter(model_path=path, num_threads=4)
    interpreter.allocate_tensors()
    source = interpreter.get_input_details()[0]
    target = interpreter.get_output_details()[0]
    interpreter.set_tensor(source["index"], pixels)
    started = time.time()
    interpreter.invoke()
    return interpreter.get_tensor(target["index"]), (time.time() - started) * 1000


def main() -> None:
    for width, height in SIZES:
        model = quantizer.Quantizer(f"fp32_{width}x{height}.tflite")
        model.load_quantization_recipe(recipe.weight_only_wi8_afp32())
        name = f"depth_anything_v2_small_{width}x{height}.tflite"
        model.quantize().export_model(name, overwrite=True)
        ramp = np.linspace(0, 1, height, dtype=np.float32).reshape(1, 1, height, 1)
        pixels = np.ascontiguousarray(np.broadcast_to(ramp, (1, 3, height, width)))
        reference, _ = run(f"fp32_{width}x{height}.tflite", pixels)
        quantized, ms = run(name, pixels)
        corr = np.corrcoef(reference.ravel(), quantized.ravel())[0, 1]
        print(f"{name}: correlation with float {corr:.4f}, one CPU run here {ms:.0f} ms")


if __name__ == "__main__":
    main()
