// The space profile of a room: what was found, for the person to confirm
// between the review and the stages. It will come from the room API once
// the scan has been understood. Until that endpoint exists the schema's own
// fixture stands in, in development and preview builds only.
import type { SpaceProfile } from "@sajao/schemas";
import fixture from "../../../../packages/schemas/fixtures/v1/valid/space-profile.json";
import { samplesAllowed } from "./samples";

/** The profile to confirm for a room, or null when there is none to show. */
export function roomSpaceProfile(_roomId: string): SpaceProfile | null {
  return samplesAllowed() ? (fixture as unknown as SpaceProfile) : null;
}
