"""Which Gaussians a trained room splat keeps: the rules, as pure code.

The GPU counts, per Gaussian, how many training cameras have it in view and how
often it sits in front of, or on, the surface the depth sensor measured. These
functions turn the counts into what is removed.
"""

import numpy as np

# A Gaussian only one camera ever had in view is unconstrained: it fits that one
# photo and streaks from anywhere else.
MIN_VIEWS = 2
# Floaters are culled where they hurt: within this distance of where a camera stood.
NEAR_CAMERA_M = 0.5
# A point this far in front of the measured surface is in free space...
FREE_MARGIN_M, FREE_MARGIN_SHARE = 0.10, 0.10
# ...and counts as a floater when at least this many cameras say so, and they
# outnumber the cameras that see it on a surface two to one.
MIN_FREE_VOTES = 2


def free_margin(depth_m: np.ndarray) -> np.ndarray:
    """How far in front of a measured depth a point must be to count as in free space."""
    return np.maximum(FREE_MARGIN_M, FREE_MARGIN_SHARE * depth_m)


def unseen(views: np.ndarray, min_views: int = MIN_VIEWS) -> np.ndarray:
    """Gaussians in view of fewer than `min_views` training cameras."""
    return views < min_views


def floaters(camera_gap_m: np.ndarray, free: np.ndarray, surface: np.ndarray) -> np.ndarray:
    """Gaussians near a camera position that the depth sensor saw through.

    `camera_gap_m` is each Gaussian's distance to the nearest training camera;
    `free` counts the cameras whose measured depth lies well behind it, and
    `surface` the cameras that measured a surface where it is. Furniture the
    phone passed close to is on a measured surface, so it stays.
    """
    return (camera_gap_m <= NEAR_CAMERA_M) & (free >= MIN_FREE_VOTES) & (free > 2 * surface)
