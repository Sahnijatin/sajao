// Runtime validation against the bundled JSON Schema. Use at every boundary
// where data enters TypeScript code from outside (network, storage, files).
import { Ajv2020, type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import bundle from "../generated/v1.schema.json" with { type: "json" };
import type * as v1 from "./generated/v1";
import type { ObjectName } from "./index";

export interface ObjectTypes {
  Capture: v1.Capture;
  RoomProfile: v1.RoomProfile;
  TasteProfile: v1.TasteProfile;
  Brief: v1.Brief;
  Product: v1.Product;
  Design: v1.Design;
  Render: v1.Render;
  Plan: v1.Plan;
  ShoppingList: v1.ShoppingList;
  Event: v1.Event;
}

export type ValidationResult<T> = { ok: true; value: T } | { ok: false; errors: string[] };

const ajv = new Ajv2020({ allErrors: true, strict: true, strictRequired: false });
ajv.addKeyword("x-top-level");
addFormats.default(ajv);
ajv.addSchema(bundle);

function describe(error: ErrorObject): string {
  return `${error.instancePath || "/"} ${error.message ?? "is invalid"}`;
}

export function validate<N extends ObjectName>(
  name: N,
  data: unknown,
): ValidationResult<ObjectTypes[N]> {
  const check = ajv.getSchema(`${bundle.$id}#/$defs/${name}`);
  if (!check) throw new Error(`No schema for ${name}`);
  if (check(data)) return { ok: true, value: data as ObjectTypes[N] };
  return { ok: false, errors: (check.errors ?? []).map(describe) };
}
