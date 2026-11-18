import numpy as np

from sajao_catalog.gate.gate import Thresholds, ViewScore, calibrate, decide, fit_to_listing
from sajao_catalog.gate.metrics import ciede2000, silhouette, srgb_to_lab, to_square
from sajao_catalog.gate.raster import look_at, render, sample_surface
from sajao_catalog.gate.views import classify


def box(w: float, h: float, d: float) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = w / 2, h / 2, d / 2
    signs = [(a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]
    v = np.array([[a * x, b * y, c * z] for a, b, c in signs], float)
    f = np.array(
        [
            [0, 1, 3],
            [0, 3, 2],
            [4, 6, 7],
            [4, 7, 5],
            [0, 4, 5],
            [0, 5, 1],
            [2, 3, 7],
            [2, 7, 6],
            [0, 2, 6],
            [0, 6, 4],
            [1, 5, 7],
            [1, 7, 3],
        ]
    )
    return v, f


def test_render_box_front_is_a_centred_square() -> None:
    v, f = box(1, 1, 1)
    cloud = sample_surface(v, f, np.full((8, 3), 0.5), 60_000)
    rgb, mask = render(cloud, look_at(np.array([0, 0, 4.0]), np.zeros(3)), 30, 128)
    ys, xs = np.nonzero(mask)
    assert abs(ys.mean() - 64) < 2 and abs(xs.mean() - 64) < 2
    assert abs((ys.max() - ys.min()) - (xs.max() - xs.min())) <= 2
    assert np.all(rgb[~mask] == 1.0)


def test_render_respects_depth() -> None:
    v, f = box(1, 1, 1)
    near = sample_surface(v + np.array([0, 0, 1.0]), f, np.tile([1.0, 0, 0], (8, 1)), 30_000)
    far = sample_surface(v * 2, f, np.tile([0, 0, 1.0], (8, 1)), 30_000)
    from sajao_catalog.gate.raster import Cloud

    both = Cloud(
        np.r_[near.points, far.points],
        np.r_[near.colors, far.colors],
        np.r_[near.normals, far.normals],
    )
    rgb, _ = render(both, look_at(np.array([0, 0, 6.0]), np.zeros(3)), 30, 128)
    c = rgb[64, 64]
    assert c[0] > c[2]


def test_silhouette_identity_and_tolerance() -> None:
    a = np.zeros((100, 100), bool)
    a[20:80, 45:55] = True
    assert silhouette(a, a) == 1.0
    b = np.roll(a, 1, axis=1)
    assert silhouette(a, b) == 1.0
    c = np.zeros_like(a)
    c[20:80, 0:10] = True
    assert silhouette(a, c) == 0.0


def test_to_square_removes_position_and_scale() -> None:
    a = np.zeros((200, 200), bool)
    a[10:30, 10:50] = True
    b = np.zeros((400, 300), bool)
    b[200:280, 100:260] = True
    sa, sb = to_square(a, a, 64)[1], to_square(b, b, 64)[1]
    assert silhouette(sa, sb) > 0.95


def test_ciede2000_reference_pair() -> None:
    # Sharma et al. test data, pair 1
    de = ciede2000(np.array([50, 2.6772, -79.7751]), np.array([50, 0, -82.7485]))
    assert abs(de - 2.0425) < 1e-3
    white = srgb_to_lab(np.array([1.0, 1.0, 1.0]))
    assert abs(white[0] - 100) < 1e-3


def test_fit_to_listing_sets_size_and_handles_a_turned_model() -> None:
    v, _ = box(1, 2, 3)
    out = fit_to_listing(v, {"width": 200.0, "depth": 50.0, "height": 100.0})
    ext = out.max(0) - out.min(0)
    assert np.allclose(ext, [0.5, 1.0, 2.0]) and np.isclose(out[:, 1].min(), 0)
    lamp = fit_to_listing(v, {"height": 150.0})  # height only: proportions kept
    assert np.allclose(lamp.max(0) - lamp.min(0), [0.75, 1.5, 2.25])


def _view(s: float, c: float = 5, e: float = 0.6, lit: bool = False) -> ViewScore:
    return ViewScore("v", s, c, e, lit)


def test_decide_rules() -> None:
    th = Thresholds()
    assert decide([], th) == "unverifiable"
    assert decide([_view(0.9), _view(0.85)], th) == "pass"
    assert decide([_view(0.9), _view(0.6)], th) == "fail"
    assert decide([_view(0.9, c=20, lit=True)], th) == "pass"
    assert decide([_view(0.9, c=20)], th) == "fail"
    assert decide([_view(0.9, e=0.3)], th) == "fail"


def test_calibrate_caps_wrong_passes() -> None:
    true = [[_view(0.9)]] * 10
    wrong = [[_view(s)] for s in np.linspace(0.5, 0.86, 20)]
    th, t, w = calibrate(true, wrong, Thresholds())
    assert w <= 0.05 and t == 1.0 and th.silhouette > 0.8


def test_category_thresholds() -> None:
    from sajao_catalog.gate.gate import thresholds_for

    assert thresholds_for("bed") == Thresholds()
    assert thresholds_for("bed", "development").embedding == 0.35
    assert thresholds_for("lamp", "development") == Thresholds()


def test_a_development_pass_never_becomes_the_launch_result() -> None:
    from sajao_catalog.gate.gate import ViewScore, report, thresholds_for

    view = ViewScore(view="v", silhouette=0.9, colour=5.0, embedding=0.40, lit=False, pose={})
    out = report([view], thresholds_for("bed"), thresholds_for("bed", "development"))
    assert out["result"] == "fail"
    assert out["development_result"] == "pass"


def _photo(fill: tuple[int, int, int], region: tuple[slice, slice]) -> np.ndarray:
    img = np.zeros((200, 200, 4), np.uint8)
    img[..., :3] = 255
    img[region] = (*fill, 255)
    return img


def test_classify_crop_and_several_objects() -> None:
    whole = _photo((120, 80, 40), (slice(40, 160), slice(40, 160)))
    ramp = np.linspace(60, 200, 120)[:, None, None]
    whole[40:160, 40:160, :3] = ramp * np.array([1, 0.7, 0.4])
    assert classify(whole, "bed").use == "check"
    crop = _photo((120, 80, 40), (slice(0, 200), slice(0, 150)))
    assert classify(crop, "bed").use == "crop"
    two = whole.copy()
    two[30:170, 170:198] = (120, 80, 40, 255)
    two[40:160, 160:170, 3] = 0
    assert classify(two, "bed").use == "several_objects"


def test_classify_line_drawing() -> None:
    img = _photo((255, 255, 255), (slice(30, 170), slice(30, 170)))
    img[30:170:20, 30:170, :3] = 0
    assert classify(img, "bed").use == "drawing"


def test_classify_drawing_with_blue_labels() -> None:
    img = _photo((255, 255, 255), (slice(30, 170), slice(30, 170)))
    img[30:170, 30:170, 3] = 0
    img[30:170:10, 30:170] = (20, 20, 20, 255)
    img[100:110, 40:80] = (30, 80, 200, 255)
    assert classify(img, "bed").use == "drawing"


def test_render_hides_far_surface_seen_through_sparse_samples() -> None:
    from sajao_catalog.gate.raster import Cloud

    rng = np.random.default_rng(0)
    near = np.c_[rng.uniform(-1, 1, (12000, 2)), np.full(12000, 1.0)]  # front face, gaps
    far = np.c_[rng.uniform(-1, 1, (40000, 2)), np.full(40000, -1.0)]  # dense back face
    pts = np.r_[near, far]
    cols = np.r_[np.tile([0, 0, 1.0], (12000, 1)), np.tile([1.0, 0, 0], (40000, 1))]
    nrm = np.tile([0, 0, 1.0], (len(pts), 1))
    rgb, mask = render(Cloud(pts, cols, nrm), look_at(np.array([0, 0, 5.0]), np.zeros(3)), 40, 256)
    inner = rgb[96:160, 96:160][mask[96:160, 96:160]]
    assert (inner[:, 0] > inner[:, 2]).mean() < 0.05  # almost no red from the back face
