// What a room holds once it has been through the pipeline: hero views of the
// room as it is, and three looks, each a view of one `Design`. This is the
// interface the room and design API fills. A person's room only ever shows
// what the server sent for it: until then the screens say plainly that the
// room is not ready yet. Sample content exists for the preview screens of
// development and preview builds, never as someone's room.
import type { Design, SpaceDirection, SpaceTwin, SpaceType } from "@sajao/schemas";
import sampleTwin from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import type { PlanShell } from "./design-plan";
import { measuresFromTwin, type RoomMeasures } from "./measures";
import type { ConfidenceLevel } from "./room-shape";
import type { RoomStill } from "./rooms";
import { SAMPLE_DESIGNS } from "./sample-designs";
import { samplesAllowed } from "./samples";
import { useRoomData } from "@/state/room-data";

export interface HeroView {
  id: string;
  still: RoomStill;
}

export interface RoomLook {
  /** The design this look renders. Price, items and fit all come from it. */
  design: Design;
  still: RoomStill;
  /**
   * True when the still is the room as it is today, not this look: the API
   * serves no rendered picture yet, so the look is shown beside your photo.
   */
  stillIsToday?: boolean;
}

/**
 * One area of a scan that went through more than one space (a living room
 * and the dining area beyond a doorway). The server splits a scan into areas
 * at doorway-width gaps; an open-plan room stays one area.
 */
export interface RoomArea {
  id: string;
  spaceType: SpaceType | null;
  /** A photo of this area to recognise it by, from this phone; null when it has none. */
  photo: RoomStill | null;
  heroViews: readonly HeroView[];
  measures: RoomMeasures | null;
  shell: PlanShell | null;
  confidence: ConfidenceLevel | null;
}

export interface RoomContent {
  /** True while this is stand-in content, not made from this room's scan. */
  sample: boolean;
  /** What kind of space this is, as detected or corrected; null until known. */
  spaceType: SpaceType | null;
  /** The room as scanned, best view first. */
  heroViews: readonly HeroView[];
  /** Best value, best match, bold. */
  looks: readonly RoomLook[];
  /**
   * The room's measured facts, read from its twin: walls, ceiling, doors and
   * windows, big items. Each value has its source and error band. null until
   * the twin exists.
   */
  measures: RoomMeasures | null;
  /** The room's measured outline, walls and openings, for the plan; null until the twin exists. */
  shell: PlanShell | null;
  /** Which way the room faces; null until the scan has a compass reading. */
  direction: SpaceDirection | null;
  /** How the room's numbers were got: taped, measured by the scan, or estimated. null until known. */
  confidence: ConfidenceLevel | null;
  /**
   * The areas of a scan that covers more than one. Empty for a scan of one
   * area, which is most scans. One area is redesigned; the others keep
   * their photos and measurements.
   */
  areas: readonly RoomArea[];
  /**
   * The items whose fit the verifier checked against measured sizes, as
   * "design:item". Only these can be said to fit. Unset when the server does
   * not say, as an older one does not.
   */
  fitChecked?: readonly string[] | null;
}

/** True when the scan covers more than one area, so one must be chosen to redesign. */
export function hasAreas(content: RoomContent): boolean {
  return content.areas.length > 1;
}

/** The area to redesign: the one chosen, if it is still there. */
export function redesignArea(content: RoomContent, chosenId: string | null): RoomArea | null {
  if (!hasAreas(content)) return null;
  return content.areas.find((area) => area.id === chosenId) ?? null;
}

/**
 * The room as one of its areas: that area's photos, measurements, outline
 * and kind of space. The looks belong to the area being redesigned, so any
 * other area has none.
 */
export function contentForArea(
  content: RoomContent,
  area: RoomArea,
  redesigned: boolean,
): RoomContent {
  return {
    ...content,
    spaceType: area.spaceType,
    heroViews: area.heroViews,
    measures: area.measures,
    shell: area.shell,
    confidence: area.confidence,
    looks: redesigned ? content.looks : [],
  };
}

/** Vastu needs to know which way the room faces, from a calibrated compass. */
export function compassCalibrated(content: RoomContent): boolean {
  return content.direction !== null && content.direction.sources.includes("compass");
}

/** At launch, designs are made for living rooms and bedrooms. Any space can be scanned. */
export const DESIGNED_SPACES: readonly SpaceType[] = ["living_room", "bedroom"];

/**
 * Whether this kind of space gets designs. A space whose kind is not known
 * yet is not ruled out: only a known other kind is.
 */
export function designsOffered(spaceType: SpaceType | null): boolean {
  return spaceType === null || DESIGNED_SPACES.includes(spaceType);
}

const twin = sampleTwin as unknown as SpaceTwin;

const SAMPLE: RoomContent = {
  sample: true,
  spaceType: twin.space_type,
  measures: measuresFromTwin(twin),
  shell: twin.shell,
  // No compass reading in the sample, so the Vastu view stays off.
  direction: null,
  confidence: "measured",
  areas: [],
  heroViews: ([0, 1, 2] as const).map((view) => ({
    id: `view-${view}`,
    still: { kind: "placeholder", look: "before", view },
  })),
  looks: SAMPLE_DESIGNS.map((design, index) => ({
    design,
    still: { kind: "placeholder", look: "after", view: index as 0 | 1 | 2 },
  })),
};

/** Stand-in content for the preview screens; null in a store or closed-test build. Never a person's room. */
export function sampleContent(): RoomContent | null {
  return samplesAllowed() ? SAMPLE : null;
}

/** What the server has sent for a room, or null while it has sent nothing. */
export function roomContent(roomId: string): RoomContent | null {
  return useRoomData.getState().content[roomId] ?? null;
}

/** The same, kept up to date as the room's content arrives. */
export function useRoomContent(roomId: string): RoomContent | null {
  return useRoomData((state) => state.content[roomId]) ?? null;
}
