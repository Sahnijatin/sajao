import numpy as np

from bakeoff.gate import Thresholds, calibrate, sku_passes
from bakeoff.lock import lock
from bakeoff.metrics import (
    ciede2000,
    crop_pad,
    edge_f1,
    mask_iou,
    max_edge_shift,
    mean_color_delta_e,
    scale_invariant_depth_error,
    square_crop,
    srgb_to_lab,
)


def test_mask_iou_and_shift() -> None:
    a = np.zeros((10, 10), bool)
    a[2:6, 2:6] = True
    b = np.zeros_like(a)
    b[3:7, 2:6] = True
    assert mask_iou(a, a) == 1.0
    assert abs(mask_iou(a, b) - 12 / 20) < 1e-9
    assert max_edge_shift(a, b) == 1


def test_ciede2000_reference_pairs() -> None:
    # Sharma, Wu and Dalal (2005) test data, pairs 1 and 17
    assert (
        abs(ciede2000(np.array([50, 2.6772, -79.7751]), np.array([50, 0, -82.7485])) - 2.0425)
        < 1e-3
    )
    assert abs(ciede2000(np.array([50, 2.5, 0]), np.array([73, 25, -18])) - 27.1492) < 1e-3


def test_lab_white_and_delta_e_same_colour() -> None:
    assert np.allclose(srgb_to_lab(np.array([1.0, 1, 1])), [100, 0, 0], atol=1e-2)
    img = np.full((4, 4, 3), 120, np.uint8)
    m = np.ones((4, 4), bool)
    assert mean_color_delta_e(img, m, img, m) < 1e-9


def test_square_crop_pads_outside() -> None:
    m = np.zeros((10, 20), bool)
    m[0:10, 0:4] = True
    x0, y0, side = square_crop(m, margin=0)
    out = crop_pad(np.ones((10, 20)), x0, y0, side, fill=0)
    assert out.shape == (10, 10) and out.sum() == 10 * 10 - 10 * 3


def test_edge_f1_and_depth() -> None:
    e = np.zeros((20, 20), bool)
    e[10, 2:18] = True
    shifted = np.roll(e, 1, axis=0)
    assert edge_f1(e, shifted, tol=1) == 1.0
    assert edge_f1(e, np.roll(e, 5, axis=0), tol=1) == 0.0
    ref = np.linspace(1, 5, 400).reshape(20, 20)
    assert scale_invariant_depth_error(ref * 3, ref, np.ones_like(ref, bool)) < 1e-9


def test_lock_keeps_product_detail_and_takes_light() -> None:
    rng = np.random.default_rng(0)
    comp = rng.integers(60, 200, (64, 64, 3)).astype(np.uint8)
    passed = np.clip(comp.astype(float) * 0.5, 0, 255).astype(np.uint8)  # darker, same detail
    passed[:, :32] = 30  # pass destroyed the left half's detail
    m = np.zeros((64, 64), bool)
    m[16:48, 8:40] = True
    out = lock(comp, passed, m, sigma=4)
    # outside the mask the pass wins
    assert np.array_equal(out[0:8, 50:64], passed[0:8, 50:64])
    # inside the mask, detail (high-frequency) follows the composite, not the flat pass
    inside = out[20:44, 12:28].astype(float)
    assert inside.std() > 10
    assert np.corrcoef(inside.ravel(), comp[20:44, 12:28].astype(float).ravel())[0, 1] > 0.8


def test_gate_calibration_separates() -> None:
    good = [[{"iou": 0.9, "de": 5, "emb": 0.9}]] * 8 + [[{"iou": 0.7, "de": 20, "emb": 0.6}]] * 2
    wrong = [[{"iou": 0.75, "de": 15, "emb": 0.7}]] * 20
    th, tp, fp = calibrate(good, wrong, max_false_pass=0.05)
    assert fp <= 0.05 and tp == 0.8
    assert sku_passes(good[0], th) and not sku_passes(wrong[0], th)
    assert not sku_passes([], Thresholds(0, 100, 0))
