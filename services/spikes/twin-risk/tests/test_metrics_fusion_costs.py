import pytest

from twin_risk.costs import bitrate_mbps, gpu_cost_usd, stream_gpu_cost_per_minute
from twin_risk.fusion import Observation, fuse, instance_boxes, voxelize
from twin_risk.geometry import UprightBox
from twin_risk.metrics import LabelledBox, canonical_class, greedy_match, summarise
from twin_risk.split import BACKGROUND, decide_label, mask_iou


def box(x: float, length: float = 2.0) -> UprightBox:
    return UprightBox((x, 0.5, 0.0), length, 1.0, 1.0, 0.0, 1)


def test_canonical_class() -> None:
    assert canonical_class("couch") == "sofa"
    assert canonical_class("TV") == "tv_monitor"
    assert canonical_class("wooden chair") == "chair"
    assert canonical_class("tv_monitor") == "tv_monitor"
    assert canonical_class("potted plant") is None


def test_greedy_match_is_one_to_one_and_class_aware() -> None:
    gts = [LabelledBox("sofa", box(0)), LabelledBox("table", box(5))]
    preds = [
        LabelledBox("couch", box(0.1)),
        LabelledBox("couch", box(0.2)),
        LabelledBox("chair", box(5)),
    ]
    m = greedy_match(preds, gts, 0.25, class_aware=True)
    assert [(x.gt_index, x.pred_index) for x in m] == [(0, 0)]
    assert len(greedy_match(preds, gts, 0.25, class_aware=False)) == 2


def test_summarise_counts_and_errors() -> None:
    gts = [LabelledBox("sofa", box(0)), LabelledBox("table", box(5))]
    preds = [LabelledBox("sofa", box(0, length=2.2)), LabelledBox("plant", box(9))]
    s = summarise(preds, gts)
    assert s["recall_class_iou25"] == 0.5
    assert s["precision_class_iou25"] == 1.0
    assert s["predicted_objects"] == 2
    assert s["median_length_error_m"] == pytest.approx(0.2)


def test_fuse_merges_overlapping_same_class_only() -> None:
    pts = [(x * 0.05, y * 0.05, 0.0) for x in range(10) for y in range(10)]
    shifted = [(x + 0.1, y, z) for x, y, z in pts]
    obs = [
        Observation(0, "chair", 0.9, voxelize(pts, 0.05), key=7),
        Observation(1, "armchair", 0.8, voxelize(shifted, 0.05), key=8),
        Observation(2, "table", 0.7, voxelize(pts, 0.05)),
    ]
    inst = fuse(obs)
    assert len(inst) == 2
    chair = next(i for i in inst if i.label == "chair")
    assert chair.frames == {0, 1}
    assert chair.members == [(0, 7), (1, 8)]


def test_instance_boxes_requires_enough_frames() -> None:
    pts = [(x * 0.05, z * 0.05, y * 0.05) for x in range(20) for y in range(10) for z in range(8)]
    vox = voxelize(pts, 0.05)
    inst = fuse([Observation(i, "sofa", 1.0, vox) for i in range(4)])
    boxes = instance_boxes(inst, up_axis=1, min_frames=3)
    assert len(boxes) == 1
    label, b, n = boxes[0]
    assert label == "sofa" and n == 4
    assert b.length == pytest.approx(0.95, abs=0.06)
    assert instance_boxes(inst, up_axis=1, min_frames=5) == []


def test_decide_label() -> None:
    assert decide_label({3: 5}, visible=6) == 3
    assert decide_label({3: 2}, visible=2) == BACKGROUND
    assert decide_label({3: 3, 4: 3}, visible=10) == BACKGROUND
    assert decide_label({3: 4, 4: 4}, visible=8) == 3


def test_mask_iou() -> None:
    a = [[True, True], [False, False]]
    b = [[True, False], [False, False]]
    assert mask_iou(a, b) == 0.5


def test_costs() -> None:
    assert gpu_cost_usd("L40S", 3600) == pytest.approx(1.9512)
    assert stream_gpu_cost_per_minute("L4", 10.0, 30.0) == pytest.approx(0.000222 * 60 * 0.3)
    assert bitrate_mbps(1_000_000, 8.0) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        gpu_cost_usd("T4", -1)
