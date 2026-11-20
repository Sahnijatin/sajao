# Generated from schemas/v1 by scripts/generate.mjs. Do not edit.

from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel
from uuid import UUID


class SajaoContract(RootModel[Any]):
    root: Annotated[
        Any, Field(description="Generated from schemas/v1. Do not edit.", title="SajaoContract")
    ]


class ArPoint(BaseModel):
    """
    A point in the AR session's world frame, in metres, y up.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x_m: float
    y_m: float
    z_m: float


class RotationItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1.0, le=1.0)]


class ArPose(BaseModel):
    """
    Camera pose from AR tracking: position and a unit quaternion (x, y, z, w).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    position: ArPoint
    rotation: Annotated[list[RotationItem], Field(max_length=4, min_length=4)]


class MustHave(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class TasteAnswerSwipe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    card_id: Annotated[str, Field(min_length=1)]
    liked: bool


class CameraIntrinsics(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fx: Annotated[float, Field(gt=0.0)]
    fy: Annotated[float, Field(gt=0.0)]
    cx: Annotated[float, Field(ge=0.0)]
    cy: Annotated[float, Field(ge=0.0)]
    width_px: Annotated[int, Field(ge=1)]
    height_px: Annotated[int, Field(ge=1)]


class CaptureDevice(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    platform: Literal["ios", "android"]
    tier: Annotated[
        Literal["standard", "low"], Field(description="Device tier detected at launch.")
    ]
    has_ar: bool


class Ar(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tracking: Literal["arkit", "arcore", "none"]
    lidar: bool
    depth: Annotated[bool, Field(description="Depth images are in the package.")]


class ReviewWindow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]


class CompassReading(BaseModel):
    """
    Compass headings averaged across the capture, used for Vastu direction.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    mean_heading_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]
    sample_count: Annotated[int, Field(ge=1)]


class LightingScheme(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    layers: Annotated[list[Literal["ambient", "task", "accent"]], Field(min_length=1)]


class Explanation(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class HexColor(RootModel[str]):
    root: Annotated[str, Field(pattern="^#[0-9a-f]{6}$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[str, Field(max_length=2048, pattern="^https://\\S+$")]


class ImagePoint(BaseModel):
    """
    A point on a photo as a share of its width (x, from the left) and height (y, from the top).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x: Annotated[float, Field(ge=0.0, le=1.0)]
    y: Annotated[float, Field(ge=0.0, le=1.0)]


class ListedByItem(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class TriedItem(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class InventoryItem(BaseModel):
    """
    An item a vision model listed that could not be placed in 3D. Kept and shown, never dropped silently.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=80, min_length=1)]
    type: Literal["furniture", "fixture", "wall_item", "textile", "decor", "built_in"]
    count: Annotated[int | None, Field(ge=1)] = None
    listed_by: Annotated[
        list[ListedByItem], Field(description="Pinned models that listed it.", min_length=1)
    ]
    tried: Annotated[
        list[TriedItem], Field(description="Detector prompts and models tried to place it.")
    ]
    reason: Literal["not_detected", "not_seen_in_enough_frames", "no_depth", "implausible_size"]


class LocalId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]


class MeasurementConfidence(BaseModel):
    """
    How a room's lengths were measured. taped: a tape value the person entered checked or set them. ar_measured: the phone's AR (planes or LiDAR) measured them. estimated: a depth model guessed them from pictures, as for imported photos and videos; the app shows sizes with measure to confirm and makes no fit claim.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    level: Literal["taped", "ar_measured", "estimated"]
    basis: Annotated[
        Literal["tape", "ar_planes", "lidar", "depth_model"],
        Field(description="Where the room's lengths came from."),
    ]
    tape_values: Annotated[
        int | None, Field(description="Tape values the person entered for this room.", ge=0)
    ] = None


class Money(BaseModel):
    """
    A price. Set only from retailer data, never by a generative model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    currency: Literal["INR"]
    amount_minor: Annotated[int, Field(description="Amount in paise.", ge=0)]


class Swing(BaseModel):
    """
    Door swing. Its clearance is a hard rule.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    hinge: Literal["start", "end"]
    opens: Literal["inward", "outward"]


class Point2(BaseModel):
    """
    A point on the floor in the space frame, in metres.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x_m: float
    y_m: float


class Point3(BaseModel):
    """
    A point in the space frame, in metres. z is height above the floor.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x_m: float
    y_m: float
    z_m: float


class ProductRoute(BaseModel):
    """
    A permitted affiliate or rental route to a product.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["buy", "rent"]
    retailer: Annotated[str, Field(min_length=1)]
    url: Annotated[
        str,
        Field(
            description="Retailer destination. The app always opens it through the redirect service.",
            max_length=2048,
            pattern="^https://\\S+$",
        ),
    ]
    price: Annotated[
        Money, Field(description="Purchase price for buy routes; price per month for rent routes.")
    ]
    coupon_code: Annotated[str | None, Field(min_length=1)] = None


class Redesign(BaseModel):
    """
    Whether a redesign keeps this thing or may replace it. The rule keeps fixtures (fans, lights, AC units, switchboards, geysers) and lets everything else be replaced; the person can change it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    state: Literal["keep", "replace"]
    source: Literal["rule", "user"]


class RedoArea(BaseModel):
    """
    What the user wants redone: all of the scanned space, or just a part they drew around.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    scope: Literal["all", "part"]
    polygon: Annotated[
        list[Point2] | None,
        Field(
            description="The part to redo, in the space frame. Present when scope is part; the design engine checks this.",
            min_length=3,
        ),
    ] = None


class RemoveEdit(BaseModel):
    """
    Remove an object; the fill behind it is a render concern.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["remove"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    object_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]


class ModelRef(BaseModel):
    """
    Pinned model that produced a guided photo render.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    provider: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]


class RotateEdit(BaseModel):
    """
    Turn an object about the vertical axis.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["rotate"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    object_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    yaw_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]


class SafeRegion(BaseModel):
    """
    Where the camera may stand: within radius_m of any anchor. Anchors are the keyframe camera positions along the capture path, in the space frame. A viewing limit, not a room measurement.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    anchors: Annotated[list[Point3], Field(min_length=1)]
    radius_m: Annotated[float, Field(gt=0.0, le=1.0)]


class ScaleAnchor(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal[
        "geometry_model", "door_height", "switchboard_height", "ceiling_prior", "tile_grid", "tape"
    ]
    implied_scale: Annotated[
        float, Field(description="Scale factor this anchor implies for the reconstruction.", gt=0.0)
    ]


class ScaleEvidence(BaseModel):
    """
    Independent scale anchors and whether they agree.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    anchors: Annotated[list[ScaleAnchor], Field(min_length=1)]
    anchors_agree: Annotated[
        bool, Field(description="Agreement tightens error bands; disagreement widens them.")
    ]
    needs_tape_value: Annotated[
        bool, Field(description="True when the app should ask for one tape value.")
    ]


class GroupSubtotal(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    group: Annotated[
        Literal["furniture", "lighting", "decor", "paint", "flooring"],
        Field(description="Top-level grouping used for the cost breakdown."),
    ]
    subtotal: Money


class SpaceDirection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    north_deg: Annotated[
        float,
        Field(
            description="Compass bearing of the space frame's positive y axis.", ge=0.0, lt=360.0
        ),
    ]
    confidence: Annotated[
        Literal["approximate", "confirmed"],
        Field(
            description="confirmed only when more than the compass agrees. Strict Vastu needs confirmed."
        ),
    ]
    sources: Annotated[list[Literal["compass", "main_door_confirmation"]], Field(min_length=1)]


class SpaceLight(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    natural_light: Literal["low", "medium", "high"]
    main_direction_deg: Annotated[
        float | None, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ] = None


class StageRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    stage: Literal["measure", "inventory", "spec", "placement", "render"]
    status: Literal["queued", "running", "done", "failed"]
    detail: Annotated[
        str | None, Field(description="The failure reason code when the row failed.", min_length=1)
    ] = None


class StorageKey(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]


class TapeMeasurement(BaseModel):
    """
    An optional value read from a tape by the user.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    target: Literal[
        "wall_length", "ceiling_height", "door_height", "door_width", "window_width", "other"
    ]
    value_m: Annotated[float, Field(gt=0.0)]
    note: str | None = None


class MaterialPreference(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class TasteContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    age_band: Annotated[
        Literal["18_24", "25_34", "35_44", "45_54", "55_plus"],
        Field(
            description="A weak prior for the first guess only. Never filters products and is never shown back as a label."
        ),
    ]
    household: Annotated[
        list[Literal["alone", "couple", "family_with_kids", "parents", "pets"]], Field(min_length=1)
    ]
    tenure: Literal["owned", "rented"]


class TasteSwipe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    card_id: Annotated[str, Field(min_length=1)]
    liked: bool


class TasteEmbedding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Annotated[str, Field(description="Pinned embedding model identifier.", min_length=1)]
    vector: Annotated[list[float], Field(min_length=1)]


class UnitScore(RootModel[float]):
    root: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]


class ViewOrbit(BaseModel):
    """
    How far the camera may move and turn around a hero view. Viewing limits, not room measurements.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    max_offset_m: Annotated[
        float,
        Field(
            description="Largest distance of the camera from the hero pose, in metres.",
            ge=0.0,
            le=1.0,
        ),
    ]
    max_yaw_deg: Annotated[
        float,
        Field(description="Largest turn about the vertical axis, either way.", ge=0.0, le=90.0),
    ]


class Area(BaseModel):
    """
    One space of a capture: its floor, what is in it and a photo that shows it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    space_type: Annotated[
        Literal["living_room", "bedroom", "balcony", "other"] | None,
        Field(
            description="What the scanned space is. Detected from the scan, never picked up front; the user can change it."
        ),
    ] = None
    floor_polygon: Annotated[
        list[Point2], Field(description="In the space frame, seen from above.", min_length=3)
    ]
    floor_area_m2: Annotated[float, Field(ge=0.0)]
    object_ids: Annotated[
        list[LocalId],
        Field(description="Objects and built-ins whose footprint centre is in this area."),
    ]
    keyframe_ids: Annotated[
        list[LocalId], Field(description="Keyframes taken standing in this area.")
    ]
    photo_keyframe_id: Annotated[
        str | None,
        Field(
            description="The keyframe that shows the most of this area's floor, for the app to show when asking which area to redesign.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ] = None
    confidence: MeasurementConfidence | None = None


class Budget(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Money
    flexibility: Annotated[
        Literal["strict", "stretch_10"],
        Field(description="strict is never relaxed; stretch_10 allows up to 10% over."),
    ]


class TasteAnswers(BaseModel):
    """
    What the person answered in the app before asking for designs, as they answered it. The brief's own budget and must_haves are what the engine applies; these are the raw answers, kept for the spec and for learning taste.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    styles: Annotated[
        list[
            Literal[
                "modern_indian",
                "warm_luxe",
                "japandi",
                "warm_maximalist",
                "eclectic_retro",
                "minimal_wabi_sabi",
            ]
        ]
        | None,
        Field(description="Style profiles the person picked, preferred first."),
    ] = None
    swipes: Annotated[
        list[TasteAnswerSwipe] | None, Field(description="Swipe answers, in the order given.")
    ] = None
    budget: Annotated[Money | None, Field(description="The budget as the person set it.")] = None
    must_haves: Annotated[
        list[MustHave] | None,
        Field(
            description="What the person said the room must have, in their words or as category keys."
        ),
    ] = None


class Brief(BaseModel):
    """
    Per-room choices on top of the taste profile. With the space profile and the catalog, the only input the design engine reads.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    space_profile_id: UUID
    taste_profile_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    intent: Literal["refresh", "full_makeover", "rearrange_only"]
    budget: Annotated[Budget, Field(title="Budget")]
    must_haves: Annotated[list[MustHave], Field(description="Product categories that must appear.")]
    keep_item_ids: Annotated[
        list[LocalId], Field(description="Existing items in the space profile to keep.")
    ]
    consider_vastu: bool
    taste_answers: Annotated[
        TasteAnswers | None,
        Field(
            description="What the person answered in the app before asking for designs, as they answered it. The brief's own budget and must_haves are what the engine applies; these are the raw answers, kept for the spec and for learning taste.",
            title="TasteAnswers",
        ),
    ] = None


class Detection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["live_scan", "server_segmentation", "user"]
    confidence: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]


class CameraPose(BaseModel):
    """
    Camera position and orientation in the space frame. Rotation is a unit quaternion (x, y, z, w).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    position: Point3
    rotation: Annotated[list[RotationItem], Field(max_length=4, min_length=4)]


class CaptureKeyframe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    image: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    captured_at_ms: Annotated[
        int, Field(description="Milliseconds from the start of the scan.", ge=0)
    ]
    sharpness: Annotated[float, Field(ge=0.0)]
    pose: ArPose | None = None
    intrinsics: CameraIntrinsics | None = None


class CaptureMedia(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    kind: Literal["photo", "video"]
    origin: Literal["camera", "gallery"]
    storage_key: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    width_px: Annotated[int, Field(ge=1)]
    height_px: Annotated[int, Field(ge=1)]
    duration_s: Annotated[float | None, Field(description="Video only.", gt=0.0)] = None
    sharpness: Annotated[
        float | None, Field(description="On-device sharpness check result.", ge=0.0, le=1.0)
    ] = None
    has_ar_pose: Annotated[
        bool, Field(description="True when an ARKit or ARCore pose is attached. Never required.")
    ]
    compass_heading_deg: Annotated[
        float | None, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ] = None


class CatalogMatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    product_id: Annotated[str, Field(min_length=1)]
    similarity: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    fits_box: Annotated[
        bool,
        Field(
            description="The product's catalog size fits this object's box, with the error band as margin."
        ),
    ]


class RuleResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rule: Annotated[str, Field(min_length=1)]
    kind: Literal["hard", "soft"]
    passed: bool
    score: Annotated[float | None, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)] = None
    detail: str | None = None


class CheckReport(BaseModel):
    """
    The verifier's independent re-check.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    passed: Annotated[
        bool,
        Field(description="True only when every hard rule, the budget and the stock check pass."),
    ]
    checked_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    rules: list[RuleResult]
    budget_ok: bool
    stock_ok: bool


class CheckResult(BaseModel):
    """
    Outcome of one automated check.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    passed: bool
    score: Annotated[float | None, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)] = None
    detail: str | None = None


class Dimension(BaseModel):
    """
    A length that is honest about where it came from. Every dimension carries a value, a source and an error band.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value_m: Annotated[float, Field(description="Best value in metres.", ge=0.0)]
    source: Annotated[
        Literal["measured", "estimated", "user_confirmed"],
        Field(
            description="measured: tape or verified retailer data. estimated: from geometry models or unverified listings. user_confirmed: accepted by the user without a tape value."
        ),
    ]
    error_band_m: Annotated[
        float,
        Field(
            description="Half-width of the error band in metres: the true value is expected within value_m plus or minus error_band_m. The solver adds it as margin.",
            ge=0.0,
        ),
    ]


class Event(BaseModel):
    """
    Action stage: one entry in the event log (saves, swaps, buy taps, shares).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    name: Annotated[
        str,
        Field(
            description="Event name from the tracking plan.",
            max_length=64,
            pattern="^[a-z][a-z0-9_]*$",
        ),
    ]
    occurred_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    session_id: UUID
    user_id: UUID | None = None
    platform: Literal["ios", "android", "web"] | None = None
    app_version: Annotated[str | None, Field(min_length=1)] = None
    space_profile_id: UUID | None = None
    design_id: UUID | None = None
    product_id: UUID | None = None
    position: Annotated[
        int | None,
        Field(description="Position of the tapped item in its list, for click attribution.", ge=0),
    ] = None
    properties: Annotated[
        dict[str, Any], Field(description="Event-specific properties from the tracking plan.")
    ]


class ExistingItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    label: Annotated[str, Field(min_length=1)]
    center: Point2
    width: Dimension
    depth: Dimension
    height: Dimension | None = None
    rotation_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]
    action: Annotated[
        Literal["keep", "replace", "remove"], Field(description="The user's choice for this item.")
    ]


class Fixture(BaseModel):
    """
    A wall fixture that must stay accessible.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    kind: Literal["switchboard", "socket", "ac_unit"]
    wall_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    offset: Dimension
    mount_height: Dimension
    width: Dimension | None = None


class Footprint(BaseModel):
    """
    Where a thing stands on the floor plan: its box seen from above, in the space frame. From the fused geometry, never from a model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    polygon: Annotated[
        list[Point2],
        Field(description="Closed floor polygon; the last point joins the first.", min_length=3),
    ]
    width: Annotated[
        Dimension,
        Field(
            description="The longer side, with its error band: each edge may be off by up to that band."
        ),
    ]
    depth: Annotated[Dimension, Field(description="The shorter side, with its error band.")]
    on_floor: Annotated[
        bool,
        Field(
            description="Whether it takes up floor: false for things on a wall or hanging from the ceiling, whose box does not reach down to the floor."
        ),
    ]


class FreeFloor(BaseModel):
    """
    Floor a redesign can use: the floor polygon minus the footprints of everything kept that stands on the floor (objects marked keep, and built-ins).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    area_m2: Annotated[float, Field(ge=0.0)]
    error_band_m2: Annotated[
        float,
        Field(description="From the walls' and footprints' error bands along their edges.", ge=0.0),
    ]
    floor_area_m2: Annotated[float, Field(ge=0.0)]
    kept_ids: Annotated[
        list[LocalId], Field(description="Objects and built-ins whose footprints were taken out.")
    ]


class OutlineItem(RootModel[list[ImagePoint]]):
    root: Annotated[list[ImagePoint], Field(max_length=128, min_length=3)]


class HeroMask(BaseModel):
    """
    Where a thing is in one hero photo, for taking it out of that photo.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    hero_view_id: Annotated[
        str, Field(description="A hero view in viewing.hero_views.", pattern="^[a-z0-9_-]{1,40}$")
    ]
    mask: Annotated[
        str,
        Field(
            description="PNG, white where the thing is, at the keyframe's resolution. Not dilated.",
            max_length=512,
            min_length=1,
        ),
    ]
    visible_share: Annotated[
        float,
        Field(
            description="Share of the thing's box that is in frame and not hidden behind something nearer.",
            ge=0.0,
            le=1.0,
        ),
    ]
    source: Annotated[
        Literal["detected", "prompted"],
        Field(
            description="detected: the detector's own mask in this keyframe. prompted: segmented from the thing's box projected into the photo."
        ),
    ]
    outline: Annotated[
        list[OutlineItem] | None,
        Field(
            description="The mask's outer edges as closed polygons on the photo, largest first, simplified to within about 0.3% of the photo's width. The app draws the outline when the thing is tapped, without fetching the mask.",
            max_length=8,
            min_length=1,
        ),
    ] = None


class HeroView(BaseModel):
    """
    A view the twin is shown from: the pose of a real keyframe, chosen by code for how much of the room it shows, its sharpness and its framing. Never a pose a model made up.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    keyframe_id: Annotated[
        str,
        Field(
            description="The keyframe whose pose, intrinsics and photo this view uses.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    coverage: Annotated[
        float, Field(description="Share of the scanned room this view shows.", ge=0.0, le=1.0)
    ]
    sharpness: Annotated[
        float,
        Field(description="Variance of the Laplacian of the keyframe; higher is sharper.", ge=0.0),
    ]
    orbit: ViewOrbit


class Inventory(BaseModel):
    """
    The open-vocabulary inventory the objects were found from, and what could not be placed.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    listed_by: Annotated[list[ListedByItem], Field(min_length=1)]
    items_listed: Annotated[int, Field(ge=0)]
    unplaced: list[InventoryItem]


class Keyframe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    image: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    captured_at_ms: Annotated[
        int, Field(description="Milliseconds from the start of the capture.", ge=0)
    ]
    pose: CameraPose
    intrinsics: CameraIntrinsics
    sharpness: Annotated[float | None, Field(ge=0.0)] = None


class LiveDetection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    detector_class: Annotated[str, Field(max_length=60, min_length=1)]
    score: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    at_ms: Annotated[int, Field(ge=0)]
    world: Annotated[
        ArPoint | None, Field(description="Where the detection hit the AR scene, when it did.")
    ] = None


class Material(BaseModel):
    """
    Wall paint or flooring, a first-class part of the design.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(min_length=1)]
    color: Annotated[str, Field(pattern="^#[0-9a-f]{6}$")]
    finish: Annotated[str | None, Field(min_length=1)] = None
    product_id: UUID | None = None


class MoveEdit(BaseModel):
    """
    Move an object: its box centre moves, its measured size does not.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["move"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    object_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    to: Point3


class ObjectModel(BaseModel):
    """
    A 3D model made from the object's own crops. Scaled to the measured box; the model never sets the size.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    generator: Annotated[
        str, Field(description="Model name and pinned version that made it.", min_length=1)
    ]
    scaled_to_box: Literal[True]


class ObjectView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    keyframe_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    mask: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    crop: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]


class Opening(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    kind: Literal["door", "window"]
    wall_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    offset: Annotated[
        Dimension,
        Field(
            description="Distance along the wall from its start to the near edge of the opening."
        ),
    ]
    width: Dimension
    height: Dimension
    sill_height: Dimension | None = None
    swing: Annotated[
        Swing | None, Field(description="Door swing. Its clearance is a hard rule.")
    ] = None


class OrientedBox(BaseModel):
    """
    An object's measured box: centre, turn about the vertical axis and size. Sizes are dimensions with a source and an error band.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    center: Point3
    yaw_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]
    width: Dimension
    depth: Dimension
    height: Dimension


class PhoneSplat(BaseModel):
    """
    A decimated, compressed room splat for on-device viewing.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    format: Literal["sog"]
    tier: Annotated[
        Literal["capable", "budget"],
        Field(
            description="capable: recent phones (500k Gaussians). budget: budget Android (250k)."
        ),
    ]
    gaussians: Annotated[int, Field(ge=1)]
    bytes: Annotated[int, Field(ge=1)]


class PlanOpening(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["door", "window"]
    start: Point2
    end: Point2


class PlanItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    design_item_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    label: Annotated[str, Field(min_length=1)]
    center: Point2
    width_m: Annotated[float, Field(gt=0.0)]
    depth_m: Annotated[float, Field(gt=0.0)]
    rotation_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]


class Clearance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: Annotated[str, Field(min_length=1)]
    distance: Dimension
    minimum_m: Annotated[float, Field(ge=0.0)]
    ok: Annotated[
        bool,
        Field(description="True only when the distance minus its error band meets the minimum."),
    ]


class Plan(BaseModel):
    """
    Spatial view: the dimensioned 2D plan derived from one design and its space profile.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    design_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    verified: Annotated[bool, Field(description="False draws the error band as a soft halo.")]
    outline: Annotated[
        list[Point2],
        Field(description="Closed floor polygon; the last point joins the first.", min_length=3),
    ]
    openings: list[PlanOpening]
    items: list[PlanItem]
    clearances: list[Clearance]


class ProductDimensions(BaseModel):
    """
    Only measured dimensions may sit in tight spots.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Dimension
    depth: Dimension
    height: Dimension


class Product(BaseModel):
    """
    A real, curated catalog item. Dimensions, price and stock come from retailer data and checks, never from a generative model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    source: Annotated[
        str,
        Field(
            description="Catalog source key, as recorded in the catalog sources tracker.",
            min_length=1,
        ),
    ]
    sku: Annotated[str, Field(description="The retailer's identifier.", min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    brand: Annotated[str | None, Field(min_length=1)] = None
    group: Annotated[
        Literal["furniture", "lighting", "decor", "paint", "flooring"],
        Field(description="Top-level grouping used for the cost breakdown."),
    ]
    category: Annotated[
        str, Field(description="Fine category, for example sofa or floor_lamp.", min_length=1)
    ]
    dimensions: Annotated[
        ProductDimensions,
        Field(
            description="Only measured dimensions may sit in tight spots.",
            title="ProductDimensions",
        ),
    ]
    color: Annotated[str | None, Field(min_length=1)] = None
    material: Annotated[str | None, Field(min_length=1)] = None
    style_tags: (
        list[
            Literal[
                "modern_indian",
                "warm_luxe",
                "japandi",
                "warm_maximalist",
                "eclectic_retro",
                "minimal_wabi_sabi",
            ]
        ]
        | None
    ) = None
    price: Money
    in_stock: bool
    checked_at: Annotated[
        AwareDatetime, Field(description="When price, stock and link were last checked.")
    ]
    images: Annotated[list[HttpsUrl], Field(min_length=1)]
    image_use_permitted: Annotated[
        bool,
        Field(
            description="Permission to use the product's images. false only for a development product (catalog_stage development), which development and closed-test builds may show and the store release never does."
        ),
    ]
    catalog_stage: Annotated[
        Literal["live", "development"] | None,
        Field(
            description="live: a permitted source and route. development: hand-curated for building and testing before a source grants permission."
        ),
    ] = None
    routes: Annotated[
        list[ProductRoute],
        Field(description="At least one permitted buy or rent route.", min_length=1),
    ]


class ProductSize(BaseModel):
    """
    A catalog product's size: retailer data, so measured or estimated, never set by a model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Dimension
    depth: Dimension
    height: Dimension


class RenderImage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    storage_key: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    width_px: Annotated[int, Field(ge=1)]
    height_px: Annotated[int, Field(ge=1)]


class RenderChecks(BaseModel):
    """
    Required for guided_photo and composite_lit renders, enforced by the render step: such a render reaches a user only when all four pass; otherwise the plain composite is shown.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    structure: CheckResult
    grounding: CheckResult
    likeness: CheckResult
    aesthetic: CheckResult


class Render(BaseModel):
    """
    Visualisation stage: an image derived from one design. Always labelled illustrative.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    design_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    kind: Annotated[
        Literal["guided_photo", "fallback_3d", "composite", "composite_lit"],
        Field(
            description="guided_photo: a guided edit of the user's own photo. fallback_3d: the clean 3D render shown when checks fail. composite: the photo with the design's removed things taken out and each product's checked 3D asset placed by code where the solver put it (C3); no model draws a product, and it is the fallback that always renders. composite_lit: the composite with a light-only model pass that may change light and shadow but never a product's shape, place or colour (C3L); it carries checks."
        ),
    ]
    quality: Literal["preview_1k", "full_2k"]
    source_media_id: Annotated[
        UUID, Field(description="The capture media this render is seen from.")
    ]
    image: Annotated[RenderImage, Field(title="RenderImage")]
    illustrative: Annotated[
        Literal[True], Field(description="Every render carries the illustrative label.")
    ]
    model: Annotated[
        ModelRef | None,
        Field(description="Pinned model that produced a guided photo render.", title="ModelRef"),
    ] = None
    checks: Annotated[
        RenderChecks | None,
        Field(
            description="Required for guided_photo and composite_lit renders, enforced by the render step: such a render reaches a user only when all four pass; otherwise the plain composite is shown.",
            title="RenderChecks",
        ),
    ] = None


class ReplaceEdit(BaseModel):
    """
    Replace an object with a catalog product of the given size.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["replace"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    object_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    product_id: Annotated[str, Field(min_length=1)]
    product_size: ProductSize


class RoomFailure(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    reason: Annotated[
        Literal[
            "upload_incomplete",
            "photo_too_small",
            "photo_missing",
            "photo_unreadable",
            "no_ar_data",
            "planes_unreadable",
            "floor_not_visible",
            "no_walls",
            "space_not_supported",
            "invalid_request",
            "no_products",
            "no_layout_for_room",
            "nothing_fits",
            "needs_wider_view",
            "render_failed",
            "timed_out",
            "internal",
        ],
        Field(
            description="Why the job stopped. upload_incomplete: a file of the capture is not in storage. photo_too_small: a photo is below the minimum the render needs. needs_wider_view: a photo room where not even a refresh around the existing seating fits in what the photo shows; a photo from the opposite corner may help. timed_out: a stage ran past its limit and its retry. internal: an error on our side; trying again may work."
        ),
    ]
    stage: Annotated[
        Literal["uploaded", "reading", "designing", "rendering"],
        Field(description="The stage that failed."),
    ]
    retryable: Annotated[
        bool,
        Field(
            description="True when asking again (the same room or design request) may succeed; false when the capture itself must change."
        ),
    ]


class RoomStatusItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    design_id: UUID
    item_id: Annotated[
        str,
        Field(description="The design item's id, as in the Design.", pattern="^[a-z0-9_-]{1,40}$"),
    ]
    fit_checked: Annotated[
        bool,
        Field(
            description="True when the verifier checked this item's fit against measured (ar_measured or taped) sizes. False on an estimated room, where items are placed at nominal sizes and no fit is claimed."
        ),
    ]


class ShoppingLine(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    design_item_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    product_id: UUID
    title: Annotated[str, Field(min_length=1)]
    group: Annotated[
        Literal["furniture", "lighting", "decor", "paint", "flooring"],
        Field(description="Top-level grouping used for the cost breakdown."),
    ]
    price: Money
    in_stock: bool
    routes: Annotated[list[ProductRoute], Field(min_length=1)]
    cheaper_alternative_product_id: UUID | None = None


class ShoppingList(BaseModel):
    """
    Commerce stage: the buyable view of one design. Totals come from the same items the render shows.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    design_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    checked_at: Annotated[
        AwareDatetime, Field(description="When budget and stock were last re-checked.")
    ]
    lines: Annotated[list[ShoppingLine], Field(min_length=1)]
    breakdown: list[GroupSubtotal]
    paint_litres: Annotated[
        float | None, Field(description="Estimated from wall area.", ge=0.0)
    ] = None
    total: Money
    within_budget: bool
    all_in_stock: bool


class SplatRef(BaseModel):
    """
    The photoreal room splat trained on the keyframes.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[
        str,
        Field(
            description="Object key in the media store. Never a public URL; clients receive signed URLs.",
            max_length=512,
            min_length=1,
        ),
    ]
    format: Literal["ply", "spz", "ksplat"]


class SurfaceMaterial(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["paint", "tile", "wood", "stone", "wallpaper", "other"]
    color: Annotated[str | None, Field(pattern="^#[0-9a-f]{6}$")] = None
    tile_size: Annotated[
        Dimension | None, Field(description="Side of one tile, when the material is tile.")
    ] = None
    product_id: Annotated[
        str | None,
        Field(description="Catalog product for a restyle (paint or flooring).", min_length=1),
    ] = None


class TasteAttributes(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    palette_warmth: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    saturation: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    boldness: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    clutter_tolerance: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    formality: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]
    trend_vs_timeless: Annotated[
        float, Field(description="0 is trend-led, 1 is timeless.", ge=0.0, le=1.0)
    ]
    material_preferences: list[MaterialPreference]


class StyleWeight(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    style: Annotated[
        Literal[
            "modern_indian",
            "warm_luxe",
            "japandi",
            "warm_maximalist",
            "eclectic_retro",
            "minimal_wabi_sabi",
        ],
        Field(description="The six launch style profiles."),
    ]
    weight: Annotated[float, Field(description="A score from 0 to 1.", ge=0.0, le=1.0)]


class TasteProfile(BaseModel):
    """
    Personalisation stage: a learned taste, as a vector plus readable attributes the user can view, correct and reset.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    user_id: UUID
    updated_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    context: TasteContext
    swipes: list[TasteSwipe] | None = None
    reference_media: list[StorageKey] | None = None
    embedding: Annotated[TasteEmbedding, Field(title="TasteEmbedding")]
    attributes: TasteAttributes
    style_blend: Annotated[
        list[StyleWeight],
        Field(
            description="The taste described as a blend of the launch style profiles.",
            max_length=6,
            min_length=1,
        ),
    ]
    loved_colors: list[HexColor] | None = None
    banned_colors: list[HexColor] | None = None
    summary: Annotated[
        str,
        Field(
            description="The taste in plain words, editable by the user. Never mentions the age band."
        ),
    ]


class TwinObject(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    category: Annotated[
        str,
        Field(
            description="Machine class, for example sofa or almirah.", max_length=60, min_length=1
        ),
    ]
    label: Annotated[
        str,
        Field(
            description="Name shown to the user, for example Grey three-seater sofa.",
            max_length=80,
            min_length=1,
        ),
    ]
    box: OrientedBox
    detection: Detection
    views: Annotated[
        list[ObjectView],
        Field(description="Masks and best crops from the keyframes that see this object."),
    ]
    model: ObjectModel | None = None
    splat_subset: Annotated[
        str | None,
        Field(description="This object's part of the room splat.", max_length=512, min_length=1),
    ] = None
    catalog_matches: list[CatalogMatch]
    state: Annotated[
        Literal["keep", "move", "remove", "replace"],
        Field(
            description="keep in a freshly built twin. Edits change it only in a derived view, never in the stored twin."
        ),
    ]
    object_type: Annotated[
        Literal["furniture", "fixture", "wall_item", "textile", "decor"] | None,
        Field(
            description="What kind of thing it is. Built-ins are not objects: they are in the shell's built_ins."
        ),
    ] = None
    footprint: Footprint | None = None
    redesign: Redesign | None = None
    hero_masks: Annotated[
        list[HeroMask] | None, Field(description="One per hero view this thing is visible in.")
    ] = None


class Viewing(BaseModel):
    """
    Where the twin may be shown from. The room splat only holds up near where the phone stood, so the viewer and the reveal use only the hero views, their orbits, and camera positions inside the safe region.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    hero_views: Annotated[
        list[HeroView],
        Field(
            description="Six to ten views when the capture allows, best first.",
            max_length=10,
            min_length=1,
        ),
    ]
    safe_region: SafeRegion


class Wall(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    start: Point2
    end: Point2
    length: Dimension
    kind: Annotated[
        Literal["wall", "open", "unseen"] | None,
        Field(
            description="What this edge of the floor polygon is. wall (the default when absent): a wall was seen here, from near the floor to near the ceiling. open: no wall stands here, and the photos or scan saw that: a doorway or the way into the next area. Open edges are passable, never a surface to place things against. unseen: no photo or scan showed this edge, so whether a wall stands here is not known; the app never calls it open. Nothing is placed against it and nobody is routed through it; another photo may resolve it."
        ),
    ] = None


class AddEdit(BaseModel):
    """
    Add a catalog product at a pose.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["add"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    product_id: Annotated[str, Field(min_length=1)]
    product_size: ProductSize
    to: Point3
    yaw_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]
    label: Annotated[str, Field(max_length=80, min_length=1)]


class BuiltIn(BaseModel):
    """
    Something built into the room (a fitted wardrobe, a fireplace, a radiator, a kitchen counter). Part of the shell: it stays when the room is redesigned.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    category: Annotated[str, Field(max_length=60, min_length=1)]
    label: Annotated[str, Field(max_length=80, min_length=1)]
    box: OrientedBox
    detection: Detection
    footprint: Footprint | None = None


class CapturePackage(BaseModel):
    """
    Everything the scan recorded for building the twin, uploaded as one package. Works without AR: then there is video and keyframes only, with no poses. AR poses and points are in the AR session's world frame: metres, gravity aligned, y up; the twin converts them to the space frame.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    ar: Ar
    video: Annotated[
        str | None,
        Field(description="The scan video, when recorded.", max_length=512, min_length=1),
    ] = None
    video_start_ms: Annotated[
        int | None,
        Field(
            description="When the scan video's first frame was taken, in milliseconds from the start of the capture, so the video can be lined up with the keyframes and the sensor log.",
            ge=0,
        ),
    ] = None
    keyframes: Annotated[list[CaptureKeyframe], Field(max_length=200, min_length=1)]
    planes: Annotated[
        str | None, Field(description="AR planes as JSON.", max_length=512, min_length=1)
    ] = None
    scene_mesh: Annotated[
        str | None,
        Field(
            description="LiDAR scene mesh with surface classes, when the phone has LiDAR.",
            max_length=512,
            min_length=1,
        ),
    ] = None
    depth: Annotated[
        str | None,
        Field(
            description="Depth images aligned to keyframes, when the phone provides them.",
            max_length=512,
            min_length=1,
        ),
    ] = None
    detections: Annotated[
        list[LiveDetection],
        Field(description="Live detector results during the scan.", max_length=4000),
    ]
    sensor_log: Annotated[
        str,
        Field(
            description="Motion, pose and light readings over time, as JSON lines.",
            max_length=512,
            min_length=1,
        ),
    ]
    review_windows: Annotated[
        list[ReviewWindow] | None,
        Field(
            description="Times when the review was open over the scan, in milliseconds from the start of the capture. The phone was lowered then: frames of the video inside a window are not part of the scan and are dropped on the server.",
            max_length=50,
        ),
    ] = None


class DesignMaterials(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    wall_paint: Material | None = None
    flooring: Material | None = None


class DesignItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    product: Annotated[Product, Field(description="Snapshot of the product at design time.")]
    position: Annotated[
        Point2, Field(description="Center of the item's footprint in the space frame.")
    ]
    rotation_deg: Annotated[
        float, Field(description="Degrees, 0 inclusive to 360 exclusive.", ge=0.0, lt=360.0)
    ]
    placed_by: Annotated[
        Literal["solver", "user"],
        Field(
            description="Positions come from the solver or a user drag, never from a generative model."
        ),
    ]


class RestyleSurfaceEdit(BaseModel):
    """
    Repaint or refloor a surface.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    op: Literal["restyle_surface"]
    by: Annotated[Literal["user", "solver"], Field(description="Who made the edit. Never a model.")]
    surface_id: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]
    material: SurfaceMaterial


class RoomStatus(BaseModel):
    """
    Where a room's job is, as the room status endpoint returns it. The app shows only what this says: one stage, a machine-readable reason when it failed, how the room was measured, and for each design item whether a fit check ran.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    capture_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    stage: Annotated[
        Literal["uploaded", "reading", "designing", "rendering", "ready", "failed"],
        Field(
            description="uploaded: the capture is registered and the job is queued. reading: measuring the room and listing what is in it. designing: choosing products and placing them. rendering: drawing the designs on the photos. ready: three designs with their pictures. failed: see failure."
        ),
    ]
    failure: RoomFailure | None = None
    confidence_level: Annotated[
        Literal["estimated", "ar_measured", "taped"] | None,
        Field(
            description="The room twin's confidence level, once the room is read. estimated: sizes say measure to confirm and no item carries a fit claim."
        ),
    ] = None
    design_request_id: Annotated[
        UUID | None, Field(description="The latest design request for the room, once one is made.")
    ] = None
    awaiting_brief: Annotated[
        bool | None,
        Field(
            description="True when the room is read and no design request has been made yet: designing starts as soon as the app sends one."
        ),
    ] = None
    items: Annotated[
        list[RoomStatusItem],
        Field(description="Every item of every design, once designs exist; empty before."),
    ]
    status: Annotated[
        Literal["working", "ready", "failed"],
        Field(
            description="The room job alone (reading), for builds made before `stage`. Read `stage`."
        ),
    ]
    stages: Annotated[
        list[StageRow],
        Field(
            description="The pipeline rows behind `stage`, room rows first, then the latest design request's."
        ),
    ]


class ShellSurface(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str, Field(description="A wall's id, or floor or ceiling.", pattern="^[a-z0-9_-]{1,40}$")
    ]
    kind: Literal["wall", "floor", "ceiling"]
    texture: Annotated[
        str | None,
        Field(
            description="Photo texture projected from the keyframes with objects masked out.",
            max_length=512,
            min_length=1,
        ),
    ] = None
    material: SurfaceMaterial | None = None


class SpaceProfile(BaseModel):
    """
    Understanding stage: the scanned space as a scene graph. It may be a whole room or only part of one. Geometry models estimate, tape verifies; every dimension carries a value, a source and an error band.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    capture_id: UUID
    space_type: Annotated[
        Literal["living_room", "bedroom", "balcony", "other"],
        Field(
            description="What the scanned space is. Detected from the scan, never picked up front; the user can change it."
        ),
    ]
    space_type_source: Annotated[
        Literal["detected", "user"],
        Field(
            description="detected: worked out from the scan. user: changed or confirmed by the user."
        ),
    ]
    extent: Annotated[
        Literal["whole_room", "part"],
        Field(
            description="How much was scanned: a whole room, or part of one such as a corner or one wall."
        ),
    ]
    extent_source: Annotated[
        Literal["detected", "user"],
        Field(
            description="detected: worked out from the scan. user: changed or confirmed by the user."
        ),
    ]
    redo: RedoArea
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    verification: Annotated[
        Literal["estimated", "verified"],
        Field(description="verified only when tape values cover the space's key dimensions."),
    ]
    floor_polygon: Annotated[
        list[Point2],
        Field(
            description="The scanned floor area. For a partial scan this is only the part that was covered.",
            min_length=3,
        ),
    ]
    walls: Annotated[
        list[Wall],
        Field(
            description="Walls seen in the scan. A partial scan may have one or two.", min_length=1
        ),
    ]
    ceiling_height: Dimension
    openings: list[Opening]
    fixtures: list[Fixture]
    existing_items: list[ExistingItem]
    light: SpaceLight | None = None
    direction: Annotated[
        SpaceDirection | None,
        Field(
            description="Absent when the twin it comes from has no direction; Vastu stays off until the person confirms one."
        ),
    ] = None
    scale: ScaleEvidence


class TwinReference(BaseModel):
    """
    Which twin a design builds on, and the ordered edits it makes to it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    twin_id: UUID
    twin_version: Annotated[int, Field(ge=1)]
    edits: list[MoveEdit | RotateEdit | RemoveEdit | ReplaceEdit | AddEdit | RestyleSurfaceEdit]


class Capture(BaseModel):
    """
    Input stage: the photos or video of any space, at any extent (a whole room, a corner, a balcony), plus optional tape values. The space type is detected later, not picked here.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    user_id: Annotated[UUID, Field(description="Owner. Guest sessions have a user id too.")]
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    media: Annotated[list[CaptureMedia], Field(max_length=40, min_length=1)]
    device: CaptureDevice
    compass: CompassReading | None = None
    tape_measurements: list[TapeMeasurement] | None = None
    package: CapturePackage | None = None


class Design(BaseModel):
    """
    One proposed transformation. The render, the plan and the shopping list are views of this object and must never disagree with it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    space_profile_id: UUID
    brief_id: UUID
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    slot: Annotated[
        Literal["best_value", "best_match", "bold"],
        Field(description="Which of the three intents this design fills."),
    ]
    archetype: Annotated[str, Field(description="Layout archetype key.", min_length=1)]
    layout_rung: Annotated[
        Literal["standard", "floating_sofa", "side_wall_sofa", "smaller_seating", "refresh"] | None,
        Field(
            description="On a photo room, which rung of the fallback ladder made this design: standard (the archetype's own layout), floating_sofa (a sofa facing the kept TV, backed onto an open or unseen side), side_wall_sofa (a sofa on a side wall at a right angle to the TV), smaller_seating (a two seater or armchairs), refresh (the existing seating kept; rug, lighting, side table, art and plants added)."
        ),
    ] = None
    items: Annotated[list[DesignItem], Field(min_length=1)]
    materials: Annotated[DesignMaterials, Field(title="DesignMaterials")]
    lighting: Annotated[LightingScheme, Field(title="LightingScheme")]
    total_cost: Annotated[
        Money,
        Field(
            description="Sum of the item prices, computed by code from the same items the render shows."
        ),
    ]
    relaxations: Annotated[
        list[
            Literal[
                "drop_optional_items",
                "smaller_products",
                "switch_archetype",
                "reduce_walkway",
                "reduce_program",
            ]
        ],
        Field(description="Every relaxation used, in the order applied. Shown on the design."),
    ]
    check_report: CheckReport
    explanations: Annotated[
        list[Explanation],
        Field(description="Why this works, generated from the solver's own scores."),
    ]
    twin: Annotated[
        TwinReference | None,
        Field(
            description="The twin this design builds on and its edits. The render, plan, 3D view and shopping list read the same twin plus edits."
        ),
    ] = None
    measurement_level: Annotated[
        Literal["taped", "ar_measured", "estimated"] | None,
        Field(
            description="How the room was measured when the design was placed, from the twin's confidence. estimated: the design is illustrative; the plan, the render and the list say measure to confirm, and no item carries a fit or a gap. taped and ar_measured: fit and gaps may be shown."
        ),
    ] = None


class Shell(BaseModel):
    """
    The room itself: floor, walls, ceiling, doors, windows and wall fixtures.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    floor_polygon: Annotated[
        list[Point2],
        Field(description="Closed floor polygon; the last point joins the first.", min_length=3),
    ]
    walls: Annotated[list[Wall], Field(min_length=1)]
    ceiling_height: Dimension
    openings: list[Opening]
    fixtures: list[Fixture]
    surfaces: Annotated[
        list[ShellSurface], Field(description="Appearance of each wall, the floor and the ceiling.")
    ]
    built_ins: Annotated[
        list[BuiltIn] | None, Field(description="Built-in items, kept with the shell.")
    ] = None


class SpaceTwin(BaseModel):
    """
    The 3D digital twin of a scanned space: the room shell and every object as its own editable item. Built from one immutable capture; a new reconstruction is a new version, and edits are deltas kept outside the twin. Every dimension carries a value, a source and an error band; generated 3D models never set an object's size, the measured box does. The space frame is metric: x and y on the floor (as in SpaceProfile), z up from the floor.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[
        str,
        Field(
            description="Contract version of the object. Minor versions only add optional fields.",
            pattern="^1\\.[0-9]+$",
        ),
    ]
    id: UUID
    capture_id: Annotated[
        UUID, Field(description="The capture this twin was built from. The capture never changes.")
    ]
    version: Annotated[
        int,
        Field(
            description="Reconstruction version for this capture. Designs reference a twin id and version.",
            ge=1,
        ),
    ]
    created_at: Annotated[AwareDatetime, Field(description="UTC instant, RFC 3339.")]
    space_type: Annotated[
        Literal["living_room", "bedroom", "balcony", "other"],
        Field(
            description="What the scanned space is. Detected from the scan, never picked up front; the user can change it."
        ),
    ]
    space_type_source: Annotated[
        Literal["detected", "user"],
        Field(
            description="detected: worked out from the scan. user: changed or confirmed by the user."
        ),
    ]
    extent: Literal["whole_room", "part"]
    extent_source: Annotated[
        Literal["detected", "user"],
        Field(
            description="detected: worked out from the scan. user: changed or confirmed by the user."
        ),
    ]
    shell: Shell
    objects: Annotated[
        list[TwinObject], Field(description="Every object found in the space, each its own item.")
    ]
    keyframes: Annotated[
        list[Keyframe],
        Field(
            description="Sharp frames with camera poses and intrinsics, in the space frame.",
            min_length=1,
        ),
    ]
    scale: ScaleEvidence
    direction: Annotated[
        SpaceDirection | None,
        Field(
            description="Compass bearing of the space and how sure it is. Absent when no compass reading was taken (photos imported from the gallery); Vastu stays off until the person confirms a direction."
        ),
    ] = None
    splat: SplatRef | None = None
    phone_splats: Annotated[
        list[PhoneSplat] | None,
        Field(
            description="Compressed room splats for viewing on the phone, one per device tier. Colour only; built from the room splat.",
            max_length=4,
        ),
    ] = None
    viewing: Viewing | None = None
    inventory: Inventory | None = None
    free_floor: FreeFloor | None = None
    confidence: Annotated[
        MeasurementConfidence | None,
        Field(
            description="How far the room's measurements can be trusted. Fit claims only at taped or ar_measured."
        ),
    ] = None
    areas: Annotated[
        list[Area] | None,
        Field(
            description="The spaces the capture passed through, split where the floor narrows to a doorway. One area when the capture is one space (an open-plan L included). The app shows each area's photo and asks which to redesign.",
            min_length=1,
        ),
    ] = None
