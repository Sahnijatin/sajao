// The contract between app, API and workers. Types only: importing this
// entry adds nothing to an app bundle. Runtime validation lives in ./validate.
export type * from "./generated/v1";

/** The journey objects, one per stage. Each has a schema in schemas/v1. */
export const OBJECT_NAMES = [
  "Capture",
  "SpaceProfile",
  "SpaceTwin",
  "TasteProfile",
  "Brief",
  "Product",
  "Design",
  "Render",
  "Plan",
  "ShoppingList",
  "Event",
  "RoomStatus",
] as const;

export type ObjectName = (typeof OBJECT_NAMES)[number];

export const SCHEMA_VERSION = "1.0";
