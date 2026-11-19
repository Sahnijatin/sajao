"""A synthetic photo of a box room with a door: exact depth for tests and smoke runs.

Ray-cast, no randomness: a room 4 m wide and 6 m deep with a 2.8 m ceiling and a
2.05 m door on the back wall, seen from a camera standing at the front.
"""

import math

import numpy as np

from sajao_workers.twin.single_photo import intrinsics_from_fov

W, H = 320, 240
K = intrinsics_from_fov(W, H, 70.0)
# A room 4 m wide and 6 m deep with a 2.8 m ceiling; the camera stands at its front.
ROOM = {"x": (-2.0, 2.0), "y": (0.0, 2.8), "z": (-5.0, 1.0)}
DOOR = {"x": (-0.6, 0.3), "y": (0.0, 2.05)}  # on the back wall, z = -5


def render_room(
    height: float, tilt_deg: float, yaw_deg: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Z-depth (metres) and the door mask seen from a camera at (0, height, 0)."""
    k = np.asarray(K)
    ys, xs = np.mgrid[0:H, 0:W]
    cam = np.stack(
        [(xs + 0.5 - k[0, 2]) / k[0, 0], (ys + 0.5 - k[1, 2]) / k[1, 1], np.ones((H, W))], -1
    )
    t, yaw = -math.radians(tilt_deg), math.radians(yaw_deg)
    # Camera to world: OpenCV axes (y down, z forward) to y up, looking along -z.
    flip = np.diag([1.0, -1.0, -1.0])
    pitch = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
    turn = np.array(
        [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    )
    r = turn @ pitch @ flip
    rays = cam @ r.T
    origin = np.array([0.0, height, 0.0])
    best = np.full((H, W), np.inf)
    door = np.zeros((H, W), dtype=bool)
    for axis, name in enumerate(("x", "y", "z")):
        for bound in ROOM[name]:
            with np.errstate(divide="ignore", invalid="ignore"):
                s = (bound - origin[axis]) / rays[..., axis]
            hit = origin + s[..., None] * rays
            inside = s > 0
            for other, oname in enumerate(("x", "y", "z")):
                if other != axis:
                    lo, hi = ROOM[oname]
                    inside &= (hit[..., other] >= lo - 1e-6) & (hit[..., other] <= hi + 1e-6)
            closer = inside & (s < best)
            best = np.where(closer, s, best)
            if name == "z" and bound == ROOM["z"][0]:
                on_door = (
                    (hit[..., 0] >= DOOR["x"][0])
                    & (hit[..., 0] <= DOOR["x"][1])
                    & (hit[..., 1] <= DOOR["y"][1])
                )
                door = np.where(closer, on_door, door & ~closer)
    return best, door  # z-depth: the rays have unit camera z
