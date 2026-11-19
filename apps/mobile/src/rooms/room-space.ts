// The space profile of a room: what was found, for the person to confirm
// between the review and the stages. It will come from the room API once
// the scan has been understood. Until that endpoint exists a room has none:
// the schema's fixture is shown only on the preview screen, never as
// someone's room.
import type { SpaceProfile } from "@sajao/schemas";

/** The profile to confirm for a room, or null when there is none to show. */
export function roomSpaceProfile(_roomId: string): SpaceProfile | null {
  return null;
}
