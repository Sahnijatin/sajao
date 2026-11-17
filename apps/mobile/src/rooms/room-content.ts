// What a room holds once it has been through the pipeline: hero views of the
// room as it is, and three looks, each a view of one `Design`. This is the
// interface the twin and the design engine fill. Until they do, every room
// gets the same sample content, marked as a sample wherever it shows.
import type { Design } from "@sajao/schemas";
import type { RoomStill } from "./rooms";
import { SAMPLE_DESIGNS } from "./sample-designs";

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
  /** The room as scanned, best view first. */
  heroViews: readonly HeroView[];
  /** Best value, best match, bold. */
  looks: readonly RoomLook[];
}

const SAMPLE: RoomContent = {
  sample: true,
  heroViews: ([0, 1, 2] as const).map((view) => ({
    id: `view-${view}`,
    still: { kind: "placeholder", look: "before", view },
  })),
  looks: SAMPLE_DESIGNS.map((design, index) => ({
    design,
    still: { kind: "placeholder", look: "after", view: index as 0 | 1 | 2 },
  })),
};

/** The content for a room. Today: the sample, for every room. */
export function roomContent(_roomId: string): RoomContent {
  return SAMPLE;
}
