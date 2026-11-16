/* Generated from schemas/v1 by scripts/generate.mjs. Do not edit. */

/**
 * Identifier that is unique inside its parent object, for example a wall or a design item.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "LocalId".
 */
export type LocalId = string
/**
 * measured: tape or verified retailer data. estimated: from geometry models or unverified listings. user_confirmed: accepted by the user without a tape value.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "DimensionSource".
 */
export type DimensionSource = ("measured" | "estimated" | "user_confirmed")
/**
 * Degrees, 0 inclusive to 360 exclusive.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "AngleDeg".
 */
export type AngleDeg = number
/**
 * Contract version of the object. Minor versions only add optional fields.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SchemaVersion".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Uuid".
 */
export type Uuid = string
/**
 * UTC instant, RFC 3339.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Timestamp".
 */
export type Timestamp = string
/**
 * Object key in the media store. Never a public URL; clients receive signed URLs.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "StorageKey".
 */
export type StorageKey = string
/**
 * A score from 0 to 1.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "UnitScore".
 */
export type UnitScore = number
/**
 * Top-level grouping used for the cost breakdown.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ProductGroup".
 */
export type ProductGroup = ("furniture" | "lighting" | "decor" | "paint" | "flooring")
/**
 * The six launch style profiles.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "StyleProfile".
 */
export type StyleProfile = ("modern_indian" | "warm_luxe" | "japandi" | "warm_maximalist" | "eclectic_retro" | "minimal_wabi_sabi")
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "HttpsUrl".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "HexColor".
 */
export type HexColor = string
/**
 * One change to a twin, kept outside it. Made by the user or the solver, never by a model. Undo is dropping the edit.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TwinEdit".
 */
export type TwinEdit = (MoveEdit | RotateEdit | RemoveEdit | ReplaceEdit | AddEdit | RestyleSurfaceEdit)
/**
 * detected: worked out from the scan. user: changed or confirmed by the user.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "DetectionSource".
 */
export type DetectionSource = ("detected" | "user")
/**
 * Closed floor polygon; the last point joins the first.
 * 
 * @minItems 3
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Polygon".
 */
export type Polygon = [Point2, Point2, Point2, ...(Point2)[]]
/**
 * What the scanned space is. Detected from the scan, never picked up front; the user can change it.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SpaceType".
 */
export type SpaceType = ("living_room" | "bedroom" | "balcony" | "other")

/**
 * Generated from schemas/v1. Do not edit.
 */
export interface SajaoContract {
[k: string]: unknown
}
/**
 * Add a catalog product at a pose.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "AddEdit".
 */
export interface AddEdit {
id: LocalId
op: "add"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
product_id: string
product_size: ProductSize
to: Point3
yaw_deg: AngleDeg
label: string
}
/**
 * A catalog product's size: retailer data, so measured or estimated, never set by a model.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ProductSize".
 */
export interface ProductSize {
width: Dimension
depth: Dimension
height: Dimension
}
/**
 * A length that is honest about where it came from. Every dimension carries a value, a source and an error band.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Dimension".
 */
export interface Dimension {
/**
 * Best value in metres.
 */
value_m: number
source: DimensionSource
/**
 * Half-width of the error band in metres: the true value is expected within value_m plus or minus error_band_m. The solver adds it as margin.
 */
error_band_m: number
}
/**
 * A point in the space frame, in metres. z is height above the floor.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Point3".
 */
export interface Point3 {
x_m: number
y_m: number
z_m: number
}
/**
 * A point in the AR session's world frame, in metres, y up.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ArPoint".
 */
export interface ArPoint {
x_m: number
y_m: number
z_m: number
}
/**
 * Camera pose from AR tracking: position and a unit quaternion (x, y, z, w).
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ArPose".
 */
export interface ArPose {
position: ArPoint
/**
 * @minItems 4
 * @maxItems 4
 */
rotation: [number, number, number, number]
}
/**
 * Per-room choices on top of the taste profile. With the space profile and the catalog, the only input the design engine reads.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Brief".
 */
export interface Brief {
schema_version: SchemaVersion
id: Uuid
space_profile_id: Uuid
taste_profile_id: Uuid
created_at: Timestamp
intent: ("refresh" | "full_makeover" | "rearrange_only")
budget: Budget
/**
 * Product categories that must appear.
 */
must_haves: string[]
/**
 * Existing items in the space profile to keep.
 */
keep_item_ids: LocalId[]
consider_vastu: boolean
}
export interface Budget {
limit: Money
/**
 * strict is never relaxed; stretch_10 allows up to 10% over.
 */
flexibility: ("strict" | "stretch_10")
}
/**
 * A price. Set only from retailer data, never by a generative model.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Money".
 */
export interface Money {
currency: "INR"
/**
 * Amount in paise.
 */
amount_minor: number
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CameraIntrinsics".
 */
export interface CameraIntrinsics {
fx: number
fy: number
cx: number
cy: number
width_px: number
height_px: number
}
/**
 * Camera position and orientation in the space frame. Rotation is a unit quaternion (x, y, z, w).
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CameraPose".
 */
export interface CameraPose {
position: Point3
/**
 * @minItems 4
 * @maxItems 4
 */
rotation: [number, number, number, number]
}
/**
 * Input stage: the photos or video of any space, at any extent (a whole room, a corner, a balcony), plus optional tape values. The space type is detected later, not picked here.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Capture".
 */
export interface Capture {
schema_version: SchemaVersion
id: Uuid
user_id: Uuid
created_at: Timestamp
/**
 * @minItems 1
 * @maxItems 40
 */
media: [CaptureMedia, ...(CaptureMedia)[]]
device: CaptureDevice
compass?: CompassReading
tape_measurements?: TapeMeasurement[]
package?: CapturePackage
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CaptureMedia".
 */
export interface CaptureMedia {
id: Uuid
kind: ("photo" | "video")
origin: ("camera" | "gallery")
storage_key: StorageKey
width_px: number
height_px: number
/**
 * Video only.
 */
duration_s?: number
sharpness?: UnitScore
/**
 * True when an ARKit or ARCore pose is attached. Never required.
 */
has_ar_pose: boolean
compass_heading_deg?: AngleDeg
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CaptureDevice".
 */
export interface CaptureDevice {
platform: ("ios" | "android")
/**
 * Device tier detected at launch.
 */
tier: ("standard" | "low")
has_ar: boolean
}
/**
 * Compass headings averaged across the capture, used for Vastu direction.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CompassReading".
 */
export interface CompassReading {
mean_heading_deg: AngleDeg
sample_count: number
}
/**
 * An optional value read from a tape by the user.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TapeMeasurement".
 */
export interface TapeMeasurement {
target: ("wall_length" | "ceiling_height" | "door_height" | "door_width" | "window_width" | "other")
value_m: number
note?: string
}
/**
 * Everything the scan recorded for building the twin, uploaded as one package. Works without AR: then there is video and keyframes only, with no poses. AR poses and points are in the AR session's world frame: metres, gravity aligned, y up; the twin converts them to the space frame.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CapturePackage".
 */
export interface CapturePackage {
ar: {
tracking: ("arkit" | "arcore" | "none")
lidar: boolean
/**
 * Depth images are in the package.
 */
depth: boolean
}
video?: StorageKey
/**
 * @minItems 1
 * @maxItems 120
 */
keyframes: [CaptureKeyframe, ...(CaptureKeyframe)[]]
planes?: StorageKey
scene_mesh?: StorageKey
depth?: StorageKey
/**
 * Live detector results during the scan.
 * 
 * @maxItems 4000
 */
detections: LiveDetection[]
sensor_log: StorageKey
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CaptureKeyframe".
 */
export interface CaptureKeyframe {
id: LocalId
image: StorageKey
/**
 * Milliseconds from the start of the scan.
 */
captured_at_ms: number
sharpness: number
pose?: ArPose
intrinsics?: CameraIntrinsics
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "LiveDetection".
 */
export interface LiveDetection {
detector_class: string
score: UnitScore
at_ms: number
world?: ArPoint
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CatalogMatch".
 */
export interface CatalogMatch {
product_id: string
similarity: UnitScore
/**
 * The product's catalog size fits this object's box, with the error band as margin.
 */
fits_box: boolean
}
/**
 * The verifier's independent re-check.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CheckReport".
 */
export interface CheckReport {
/**
 * True only when every hard rule, the budget and the stock check pass.
 */
passed: boolean
checked_at: Timestamp
rules: RuleResult[]
budget_ok: boolean
stock_ok: boolean
}
export interface RuleResult {
rule: string
kind: ("hard" | "soft")
passed: boolean
score?: UnitScore
detail?: string
}
/**
 * Outcome of one automated check.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "CheckResult".
 */
export interface CheckResult {
passed: boolean
score?: UnitScore
detail?: string
}
/**
 * One proposed transformation. The render, the plan and the shopping list are views of this object and must never disagree with it.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Design".
 */
export interface Design {
schema_version: SchemaVersion
id: Uuid
space_profile_id: Uuid
brief_id: Uuid
created_at: Timestamp
/**
 * Which of the three intents this design fills.
 */
slot: ("best_value" | "best_match" | "bold")
/**
 * Layout archetype key.
 */
archetype: string
/**
 * @minItems 1
 */
items: [DesignItem, ...(DesignItem)[]]
materials: DesignMaterials
lighting: LightingScheme
total_cost: Money
/**
 * Every relaxation used, in the order applied. Shown on the design.
 */
relaxations: ("drop_optional_items" | "smaller_products" | "switch_archetype" | "reduce_walkway" | "reduce_program")[]
check_report: CheckReport
/**
 * Why this works, generated from the solver's own scores.
 */
explanations: string[]
twin?: TwinReference
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "DesignItem".
 */
export interface DesignItem {
id: LocalId
product: Product
position: Point2
rotation_deg: AngleDeg
/**
 * Positions come from the solver or a user drag, never from a generative model.
 */
placed_by: ("solver" | "user")
}
/**
 * A real, curated catalog item. Dimensions, price and stock come from retailer data and checks, never from a generative model.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Product".
 */
export interface Product {
schema_version: SchemaVersion
id: Uuid
/**
 * Catalog source key, as recorded in the catalog sources tracker.
 */
source: string
/**
 * The retailer's identifier.
 */
sku: string
title: string
brand?: string
group: ProductGroup
/**
 * Fine category, for example sofa or floor_lamp.
 */
category: string
dimensions: ProductDimensions
color?: string
material?: string
style_tags?: StyleProfile[]
price: Money
in_stock: boolean
checked_at: Timestamp
/**
 * @minItems 1
 */
images: [HttpsUrl, ...(HttpsUrl)[]]
/**
 * A product enters the contract only with permission to use its images.
 */
image_use_permitted: true
/**
 * At least one permitted buy or rent route.
 * 
 * @minItems 1
 */
routes: [ProductRoute, ...(ProductRoute)[]]
}
/**
 * Only measured dimensions may sit in tight spots.
 */
export interface ProductDimensions {
width: Dimension
depth: Dimension
height: Dimension
}
/**
 * A permitted affiliate or rental route to a product.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ProductRoute".
 */
export interface ProductRoute {
kind: ("buy" | "rent")
retailer: string
url: HttpsUrl
price: Money
coupon_code?: string
}
/**
 * A point on the floor in the space frame, in metres.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Point2".
 */
export interface Point2 {
x_m: number
y_m: number
}
export interface DesignMaterials {
wall_paint?: Material
flooring?: Material
}
/**
 * Wall paint or flooring, a first-class part of the design.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Material".
 */
export interface Material {
name: string
color: HexColor
finish?: string
product_id?: Uuid
}
export interface LightingScheme {
/**
 * @minItems 1
 */
layers: [("ambient" | "task" | "accent"), ...(("ambient" | "task" | "accent"))[]]
}
/**
 * Which twin a design builds on, and the ordered edits it makes to it.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TwinReference".
 */
export interface TwinReference {
twin_id: Uuid
twin_version: number
edits: TwinEdit[]
}
/**
 * Move an object: its box centre moves, its measured size does not.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "MoveEdit".
 */
export interface MoveEdit {
id: LocalId
op: "move"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
object_id: LocalId
to: Point3
}
/**
 * Turn an object about the vertical axis.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "RotateEdit".
 */
export interface RotateEdit {
id: LocalId
op: "rotate"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
object_id: LocalId
yaw_deg: AngleDeg
}
/**
 * Remove an object; the fill behind it is a render concern.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "RemoveEdit".
 */
export interface RemoveEdit {
id: LocalId
op: "remove"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
object_id: LocalId
}
/**
 * Replace an object with a catalog product of the given size.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ReplaceEdit".
 */
export interface ReplaceEdit {
id: LocalId
op: "replace"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
object_id: LocalId
product_id: string
product_size: ProductSize
}
/**
 * Repaint or refloor a surface.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "RestyleSurfaceEdit".
 */
export interface RestyleSurfaceEdit {
id: LocalId
op: "restyle_surface"
/**
 * Who made the edit. Never a model.
 */
by: ("user" | "solver")
surface_id: LocalId
material: SurfaceMaterial
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SurfaceMaterial".
 */
export interface SurfaceMaterial {
kind: ("paint" | "tile" | "wood" | "stone" | "wallpaper" | "other")
color?: HexColor
tile_size?: Dimension
/**
 * Catalog product for a restyle (paint or flooring).
 */
product_id?: string
}
/**
 * Action stage: one entry in the event log (saves, swaps, buy taps, shares).
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Event".
 */
export interface Event {
schema_version: SchemaVersion
id: Uuid
/**
 * Event name from the tracking plan.
 */
name: string
occurred_at: Timestamp
session_id: Uuid
user_id?: Uuid
platform?: ("ios" | "android" | "web")
app_version?: string
space_profile_id?: Uuid
design_id?: Uuid
product_id?: Uuid
/**
 * Position of the tapped item in its list, for click attribution.
 */
position?: number
/**
 * Event-specific properties from the tracking plan.
 */
properties: {
[k: string]: unknown
}
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ExistingItem".
 */
export interface ExistingItem {
id: LocalId
label: string
center: Point2
width: Dimension
depth: Dimension
height?: Dimension
rotation_deg: AngleDeg
/**
 * The user's choice for this item.
 */
action: ("keep" | "replace" | "remove")
}
/**
 * A wall fixture that must stay accessible.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Fixture".
 */
export interface Fixture {
id: LocalId
kind: ("switchboard" | "socket" | "ac_unit")
wall_id: LocalId
offset: Dimension
mount_height: Dimension
width?: Dimension
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Keyframe".
 */
export interface Keyframe {
id: LocalId
image: StorageKey
/**
 * Milliseconds from the start of the capture.
 */
captured_at_ms: number
pose: CameraPose
intrinsics: CameraIntrinsics
sharpness?: number
}
/**
 * A 3D model made from the object's own crops. Scaled to the measured box; the model never sets the size.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ObjectModel".
 */
export interface ObjectModel {
key: StorageKey
/**
 * Model name and pinned version that made it.
 */
generator: string
scaled_to_box: true
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ObjectView".
 */
export interface ObjectView {
keyframe_id: LocalId
mask: StorageKey
crop: StorageKey
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Opening".
 */
export interface Opening {
id: LocalId
kind: ("door" | "window")
wall_id: LocalId
offset: Dimension
width: Dimension
height: Dimension
sill_height?: Dimension
/**
 * Door swing. Its clearance is a hard rule.
 */
swing?: {
hinge: ("start" | "end")
opens: ("inward" | "outward")
}
}
/**
 * An object's measured box: centre, turn about the vertical axis and size. Sizes are dimensions with a source and an error band.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "OrientedBox".
 */
export interface OrientedBox {
center: Point3
yaw_deg: AngleDeg
width: Dimension
depth: Dimension
height: Dimension
}
/**
 * A decimated, compressed room splat for on-device viewing.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "PhoneSplat".
 */
export interface PhoneSplat {
key: StorageKey
format: "sog"
/**
 * capable: recent phones (500k Gaussians). budget: budget Android (250k).
 */
tier: ("capable" | "budget")
gaussians: number
bytes: number
}
/**
 * Spatial view: the dimensioned 2D plan derived from one design and its space profile.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Plan".
 */
export interface Plan {
schema_version: SchemaVersion
id: Uuid
design_id: Uuid
created_at: Timestamp
/**
 * False draws the error band as a soft halo.
 */
verified: boolean
outline: Polygon
openings: PlanOpening[]
items: PlanItem[]
clearances: Clearance[]
}
export interface PlanOpening {
kind: ("door" | "window")
start: Point2
end: Point2
}
export interface PlanItem {
design_item_id: LocalId
label: string
center: Point2
width_m: number
depth_m: number
rotation_deg: AngleDeg
}
export interface Clearance {
label: string
distance: Dimension
minimum_m: number
/**
 * True only when the distance minus its error band meets the minimum.
 */
ok: boolean
}
/**
 * What the user wants redone: all of the scanned space, or just a part they drew around.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "RedoArea".
 */
export interface RedoArea {
scope: ("all" | "part")
polygon?: Polygon
}
/**
 * Visualisation stage: an image derived from one design. Always labelled illustrative.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Render".
 */
export interface Render {
schema_version: SchemaVersion
id: Uuid
design_id: Uuid
created_at: Timestamp
/**
 * guided_photo is a guided edit of the user's own photo; fallback_3d is the clean 3D render shown when checks fail.
 */
kind: ("guided_photo" | "fallback_3d")
quality: ("preview_1k" | "full_2k")
source_media_id: Uuid
image: RenderImage
/**
 * Every render carries the illustrative label.
 */
illustrative: true
model?: ModelRef
checks?: RenderChecks
}
export interface RenderImage {
storage_key: StorageKey
width_px: number
height_px: number
}
/**
 * Pinned model that produced a guided photo render.
 */
export interface ModelRef {
provider: string
name: string
version: string
}
/**
 * Required for guided_photo renders, enforced by the render step: a guided photo reaches a user only when all four pass.
 */
export interface RenderChecks {
structure: CheckResult
grounding: CheckResult
likeness: CheckResult
aesthetic: CheckResult
}
/**
 * Independent scale anchors and whether they agree.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ScaleEvidence".
 */
export interface ScaleEvidence {
/**
 * @minItems 1
 */
anchors: [ScaleAnchor, ...(ScaleAnchor)[]]
/**
 * Agreement tightens error bands; disagreement widens them.
 */
anchors_agree: boolean
/**
 * True when the app should ask for one tape value.
 */
needs_tape_value: boolean
}
export interface ScaleAnchor {
kind: ("geometry_model" | "door_height" | "switchboard_height" | "ceiling_prior" | "tile_grid" | "tape")
/**
 * Scale factor this anchor implies for the reconstruction.
 */
implied_scale: number
}
/**
 * The room itself: floor, walls, ceiling, doors, windows and wall fixtures.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Shell".
 */
export interface Shell {
floor_polygon: Polygon
/**
 * @minItems 1
 */
walls: [Wall, ...(Wall)[]]
ceiling_height: Dimension
openings: Opening[]
fixtures: Fixture[]
/**
 * Appearance of each wall, the floor and the ceiling.
 */
surfaces: ShellSurface[]
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "Wall".
 */
export interface Wall {
id: LocalId
start: Point2
end: Point2
length: Dimension
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ShellSurface".
 */
export interface ShellSurface {
id: LocalId
kind: ("wall" | "floor" | "ceiling")
texture?: StorageKey
material?: SurfaceMaterial
}
/**
 * Commerce stage: the buyable view of one design. Totals come from the same items the render shows.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "ShoppingList".
 */
export interface ShoppingList {
schema_version: SchemaVersion
id: Uuid
design_id: Uuid
created_at: Timestamp
checked_at: Timestamp
/**
 * @minItems 1
 */
lines: [ShoppingLine, ...(ShoppingLine)[]]
breakdown: GroupSubtotal[]
/**
 * Estimated from wall area.
 */
paint_litres?: number
total: Money
within_budget: boolean
all_in_stock: boolean
}
export interface ShoppingLine {
design_item_id: LocalId
product_id: Uuid
title: string
group: ProductGroup
price: Money
in_stock: boolean
/**
 * @minItems 1
 */
routes: [ProductRoute, ...(ProductRoute)[]]
cheaper_alternative_product_id?: Uuid
}
export interface GroupSubtotal {
group: ProductGroup
subtotal: Money
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SpaceDirection".
 */
export interface SpaceDirection {
north_deg: AngleDeg
/**
 * confirmed only when more than the compass agrees. Strict Vastu needs confirmed.
 */
confidence: ("approximate" | "confirmed")
/**
 * @minItems 1
 */
sources: [("compass" | "main_door_confirmation"), ...(("compass" | "main_door_confirmation"))[]]
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SpaceLight".
 */
export interface SpaceLight {
natural_light: ("low" | "medium" | "high")
main_direction_deg?: AngleDeg
}
/**
 * Understanding stage: the scanned space as a scene graph. It may be a whole room or only part of one. Geometry models estimate, tape verifies; every dimension carries a value, a source and an error band.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SpaceProfile".
 */
export interface SpaceProfile {
schema_version: SchemaVersion
id: Uuid
capture_id: Uuid
space_type: SpaceType
space_type_source: DetectionSource
/**
 * How much was scanned: a whole room, or part of one such as a corner or one wall.
 */
extent: ("whole_room" | "part")
extent_source: DetectionSource
redo: RedoArea
created_at: Timestamp
/**
 * verified only when tape values cover the space's key dimensions.
 */
verification: ("estimated" | "verified")
floor_polygon: Polygon
/**
 * Walls seen in the scan. A partial scan may have one or two.
 * 
 * @minItems 1
 */
walls: [Wall, ...(Wall)[]]
ceiling_height: Dimension
openings: Opening[]
fixtures: Fixture[]
existing_items: ExistingItem[]
light?: SpaceLight
direction: SpaceDirection
scale: ScaleEvidence
}
/**
 * The 3D digital twin of a scanned space: the room shell and every object as its own editable item. Built from one immutable capture; a new reconstruction is a new version, and edits are deltas kept outside the twin. Every dimension carries a value, a source and an error band; generated 3D models never set an object's size, the measured box does. The space frame is metric: x and y on the floor (as in SpaceProfile), z up from the floor.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SpaceTwin".
 */
export interface SpaceTwin {
schema_version: SchemaVersion
id: Uuid
capture_id: Uuid
/**
 * Reconstruction version for this capture. Designs reference a twin id and version.
 */
version: number
created_at: Timestamp
space_type: SpaceType
space_type_source: DetectionSource
extent: ("whole_room" | "part")
extent_source: DetectionSource
shell: Shell
/**
 * Every object found in the space, each its own item.
 */
objects: TwinObject[]
/**
 * Sharp frames with camera poses and intrinsics, in the space frame.
 * 
 * @minItems 1
 */
keyframes: [Keyframe, ...(Keyframe)[]]
scale: ScaleEvidence
direction: SpaceDirection
splat?: SplatRef
/**
 * Compressed room splats for viewing on the phone, one per device tier. Colour only; built from the room splat.
 * 
 * @maxItems 4
 */
phone_splats?: []|[PhoneSplat]|[PhoneSplat, PhoneSplat]|[PhoneSplat, PhoneSplat, PhoneSplat]|[PhoneSplat, PhoneSplat, PhoneSplat, PhoneSplat]
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TwinObject".
 */
export interface TwinObject {
id: LocalId
/**
 * Machine class, for example sofa or almirah.
 */
category: string
/**
 * Name shown to the user, for example Grey three-seater sofa.
 */
label: string
box: OrientedBox
detection: {
source: ("live_scan" | "server_segmentation" | "user")
confidence: UnitScore
}
/**
 * Masks and best crops from the keyframes that see this object.
 */
views: ObjectView[]
model?: ObjectModel
splat_subset?: StorageKey
catalog_matches: CatalogMatch[]
/**
 * keep in a freshly built twin. Edits change it only in a derived view, never in the stored twin.
 */
state: ("keep" | "move" | "remove" | "replace")
}
/**
 * The photoreal room splat trained on the keyframes.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "SplatRef".
 */
export interface SplatRef {
key: StorageKey
format: ("ply" | "spz" | "ksplat")
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TasteAttributes".
 */
export interface TasteAttributes {
palette_warmth: UnitScore
saturation: UnitScore
boldness: UnitScore
clutter_tolerance: UnitScore
formality: UnitScore
trend_vs_timeless: UnitScore
material_preferences: string[]
}
/**
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TasteContext".
 */
export interface TasteContext {
/**
 * A weak prior for the first guess only. Never filters products and is never shown back as a label.
 */
age_band: ("18_24" | "25_34" | "35_44" | "45_54" | "55_plus")
/**
 * @minItems 1
 */
household: [("alone" | "couple" | "family_with_kids" | "parents" | "pets"), ...(("alone" | "couple" | "family_with_kids" | "parents" | "pets"))[]]
tenure: ("owned" | "rented")
}
/**
 * Personalisation stage: a learned taste, as a vector plus readable attributes the user can view, correct and reset.
 * 
 * This interface was referenced by `SajaoContract`'s JSON-Schema
 * via the `definition` "TasteProfile".
 */
export interface TasteProfile {
schema_version: SchemaVersion
id: Uuid
user_id: Uuid
updated_at: Timestamp
context: TasteContext
swipes?: TasteSwipe[]
reference_media?: StorageKey[]
embedding: TasteEmbedding
attributes: TasteAttributes
/**
 * The taste described as a blend of the launch style profiles.
 * 
 * @minItems 1
 * @maxItems 6
 */
style_blend: [StyleWeight]|[StyleWeight, StyleWeight]|[StyleWeight, StyleWeight, StyleWeight]|[StyleWeight, StyleWeight, StyleWeight, StyleWeight]|[StyleWeight, StyleWeight, StyleWeight, StyleWeight, StyleWeight]|[StyleWeight, StyleWeight, StyleWeight, StyleWeight, StyleWeight, StyleWeight]
loved_colors?: HexColor[]
banned_colors?: HexColor[]
/**
 * The taste in plain words, editable by the user. Never mentions the age band.
 */
summary: string
}
export interface TasteSwipe {
card_id: string
liked: boolean
}
export interface TasteEmbedding {
/**
 * Pinned embedding model identifier.
 */
model: string
/**
 * @minItems 1
 */
vector: [number, ...(number)[]]
}
export interface StyleWeight {
style: StyleProfile
weight: UnitScore
}
