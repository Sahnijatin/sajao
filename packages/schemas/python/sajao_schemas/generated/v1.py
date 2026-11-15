# Generated from schemas/v1 by scripts/generate.mjs. Do not edit.

from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel
from uuid import UUID


class SajaoContract(RootModel[Any]):
    root: Annotated[
        Any, Field(description="Generated from schemas/v1. Do not edit.", title="SajaoContract")
    ]


class MustHave(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class CaptureDevice(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    platform: Literal["ios", "android"]
    tier: Annotated[
        Literal["standard", "low"], Field(description="Device tier detected at launch.")
    ]
    has_ar: bool


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


class LocalId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Identifier that is unique inside its parent object, for example a wall or a design item.",
            pattern="^[a-z0-9_-]{1,40}$",
        ),
    ]


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


class Budget(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Money
    flexibility: Annotated[
        Literal["strict", "stretch_10"],
        Field(description="strict is never relaxed; stretch_10 allows up to 10% over."),
    ]


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
        Literal[True],
        Field(description="A product enters the contract only with permission to use its images."),
    ]
    routes: Annotated[
        list[ProductRoute],
        Field(description="At least one permitted buy or rent route.", min_length=1),
    ]


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
    Required for guided_photo renders, enforced by the render step: a guided photo reaches a user only when all four pass.
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
        Literal["guided_photo", "fallback_3d"],
        Field(
            description="guided_photo is a guided edit of the user's own photo; fallback_3d is the clean 3D render shown when checks fail."
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
            description="Required for guided_photo renders, enforced by the render step: a guided photo reaches a user only when all four pass.",
            title="RenderChecks",
        ),
    ] = None


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
    direction: SpaceDirection
    scale: ScaleEvidence


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
