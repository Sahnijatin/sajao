"""The render on the photo: products drawn where they stand, removal masks from the twin."""

import io
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_workers.render.compose import PhotoCamera, composite, place_asset
from sajao_workers.render.removal import removal_mask, removed_ids
from sajao_workers.steps import LocalArtifactStore

W, H = 320, 240


def camera() -> PhotoCamera:
    # At (0, -3, 1.2) in the space frame, looking along +y, level.
    rotation = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
    k = np.array([[250.0, 0.0, W / 2], [0.0, 250.0, H / 2], [0.0, 0.0, 1.0]])
    return PhotoCamera(k, rotation, np.array([0.0, -3.0, 1.2]), W, H)


def cube() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (0.0, 1.0) for z in (-0.5, 0.5)])
    f = np.array(
        [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
         [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]
    )  # fmt: skip
    return v, f, np.full((len(v), 3), [0.8, 0.2, 0.2])


def test_a_product_is_drawn_where_it_stands_with_its_size() -> None:
    v, f, c = cube()
    placed = place_asset(v, f, c, (1.0, 0.6, 0.8), (0.0, 0.0), 0.0, "sofa")
    photo = np.full((H, W, 3), 0.5)
    out = composite(photo, camera(), [placed])
    mask = out.masks["sofa"]
    ys, xs = np.nonzero(mask)
    # 1 m wide at 3 m with f = 250: about 83 px, centred.
    assert 70 < xs.max() - xs.min() < 100
    assert abs((xs.max() + xs.min()) / 2 - W / 2) < 4
    # The front's foot is 1.2 m below the camera and 2.7 m away: 120 + 250 * 1.2 / 2.7 px.
    assert abs(ys.max() - (120 + 250 * 1.2 / 2.7)) <= 2
    assert out.image[mask].mean(axis=0)[0] > out.image[mask].mean(axis=0)[2]
    # A contact shadow darkens the floor just below the product, nothing far away.
    assert out.image[min(H - 1, ys.max() + 3), int(xs.mean())].mean() < 0.5
    assert out.image[5, 5].mean() == pytest.approx(0.5)


def test_the_nearer_product_hides_the_farther() -> None:
    v, f, c = cube()
    near = place_asset(v, f, c, (0.6, 0.6, 0.6), (0.0, -0.5), 0.0, "near")
    far = place_asset(v, f, c, (1.2, 0.6, 1.0), (0.0, 1.0), 0.0, "far")
    out = composite(np.full((H, W, 3), 0.5), camera(), [far, near])
    assert out.masks["near"].sum() > 0 and out.masks["far"].sum() > 0
    assert not (out.masks["near"] & out.masks["far"]).any()


def png(mask: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8) * 255).save(buf, format="PNG")
    return buf.getvalue()


def test_the_removal_mask_covers_removed_things_only(tmp_path: Any) -> None:
    store = LocalArtifactStore(tmp_path)
    a = np.zeros((H, W), bool)
    a[100:150, 50:100] = True
    b = np.zeros((H, W), bool)
    b[100:150, 200:250] = True
    twin = {
        "objects": [
            {
                "id": "o1",
                "hero_masks": [{"hero_view_id": "h1", "mask": f"x/{store.put_blob(png(a))}"}],
            },
            {
                "id": "o2",
                "hero_masks": [{"hero_view_id": "h1", "mask": f"x/{store.put_blob(png(b))}"}],
            },
        ]
    }
    mask = removal_mask(twin, "h1", ["o1"], store, (H, W))
    assert mask[a].all() and not mask[b].any()
    # Grown a little and with a band below for the shadow.
    assert mask[152, 75] and not mask[100:150, 120].any()
    design = {"twin": {"edits": [{"op": "remove", "object_id": "o1"}, {"op": "add"}]}}
    assert removed_ids(design) == ["o1"]
