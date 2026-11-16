"""Pinned models for the twin worker, primary first then fallback.

Changing a model or version here reruns the golden-set evaluations. Every model
is listed in docs/24-third-party-register.md.
"""

from sajao_workers.gpu import MAX_GPUS, GpuModelProvider, Invoke

# The model function and the splat function split the GPU cap (gpu/app.py).
MODEL_GPUS = 2
SPLAT_GPUS = MAX_GPUS - MODEL_GPUS

# Household classes the detector looks for. Changing the list is a model change.
VOCABULARY = (
    "bed",
    "sofa",
    "chair",
    "armchair",
    "table",
    "desk",
    "cabinet",
    "wardrobe",
    "nightstand",
    "shelf",
    "television",
    "refrigerator",
    "stove",
    "oven",
    "sink",
    "toilet",
    "washing machine",
    "stool",
    "bathtub",
    "dishwasher",
    "fireplace",
    "lamp",
    "potted plant",
    "rug",
    "curtain",
    "pillow",
    "ottoman",
    "toy",
    "vase",
    "bowl",
)

YOLOE = "yoloe-26x-seg@ultralytics-8.4.214"
GROUNDING_DINO = "IDEA-Research/grounding-dino-base@12bdfa3120f3e7ec7b434d90674b3396eccf88eb"
SAM_LARGE = "facebook/sam2.1-hiera-large@665f8e2ad61cf5f53d65644ff27c8ee525124610"
SAM_BASE_PLUS = "facebook/sam2.1-hiera-base-plus@b7320756a13354e7530a63935656d35b2f91a290"

GSPLAT = "gsplat@1.5.3"

# Time limits per call (a batch of up to 300 frames), from the spike's timings with headroom.
DETECT_SECONDS = 300.0
SEGMENT_SECONDS = 600.0
# Splat training took 4.5 to 10 minutes per room in the spike; the function stops at an hour.
SPLAT_SECONDS = 3600.0


def detect_chain(invoke: Invoke) -> list[GpuModelProvider]:
    """YOLOE finds more objects and is 8x faster; Grounding DINO is the fallback."""
    return [
        GpuModelProvider(
            "yoloe", YOLOE, "L40S", DETECT_SECONDS, invoke, max_concurrency=MODEL_GPUS
        ),
        GpuModelProvider(
            "grounding-dino",
            GROUNDING_DINO,
            "L40S",
            DETECT_SECONDS,
            invoke,
            max_concurrency=MODEL_GPUS,
        ),
    ]


def segment_chain(invoke: Invoke) -> list[GpuModelProvider]:
    """SAM 2.1 large masks from detector boxes; base plus is the lighter fallback."""
    return [
        GpuModelProvider(
            "sam2.1-large", SAM_LARGE, "L40S", SEGMENT_SECONDS, invoke, max_concurrency=MODEL_GPUS
        ),
        GpuModelProvider(
            "sam2.1-base-plus",
            SAM_BASE_PLUS,
            "L40S",
            SEGMENT_SECONDS,
            invoke,
            max_concurrency=MODEL_GPUS,
        ),
    ]


def splat_chain(invoke: Invoke) -> list[GpuModelProvider]:
    """Splat training with pose and exposure refinement (gsplat, Apache 2.0).

    One provider: the splat function itself falls back from an L40S to an A100
    when none is free, so cost is reserved and charged at the A100 price.
    """
    return [
        GpuModelProvider(
            "gsplat",
            GSPLAT,
            "A100-40GB",
            SPLAT_SECONDS,
            invoke,
            max_concurrency=SPLAT_GPUS,
            max_attempts=1,
        ),
    ]
