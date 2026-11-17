// What a room holds once it has been through the pipeline: hero views of the
// room as it is, and three looks, each a view of one `Design`. This is the
// interface the room and design API fills. Until it does, a room gets sample
// content, marked as a sample wherever it shows, in development and preview
// builds only. A store or closed-test build gets nothing until the real
// content exists, and the screens say the room is being prepared.
import type { Design, SpaceDirection, SpaceTwin, SpaceType } from "@sajao/schemas";
import sampleTwin from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import type { PlanShell } from "./design-plan";
import { measuresFromTwin, type RoomMeasures } from "./measures";
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
  heroViews: ([0, 1, 2] as const).map((view) => ({
    id: `view-${view}`,
    still: { kind: "placeholder", look: "before", view },
  })),
  looks: SAMPLE_DESIGNS.map((design, index) => ({
    design,
    still: { kind: "placeholder", look: "after", view: index as 0 | 1 | 2 },
  })),
};

/** The stand-in content, where this build may show one; null in a store or closed-test build. */
export function sampleContent(): RoomContent | null {
  return samplesAllowed() ? SAMPLE : null;
}

/**
 * The content for a room, or null while there is none to show: what the
 * server has sent for it, else the sample where samples are allowed.
 */
export function roomContent(roomId: string): RoomContent | null {
  return useRoomData.getState().content[roomId] ?? sampleContent();
}

/** The same, kept up to date as the room's content arrives. */
export function useRoomContent(roomId: string): RoomContent | null {
  const real = useRoomData((state) => state.content[roomId]);
  return real ?? sampleContent();
}
